import fs from 'fs';
import path from 'path';
import { SarvamCallRecord, LiveCampaignProgress, SarvamAnalyticsSummary, TimeFilterPeriod } from './sarvamTypes';

const DB_PATH = path.join(process.cwd(), 'sarvam_dashboard', 'sarvam_db.json');

export interface SarvamDbSchema {
  calls: SarvamCallRecord[];
  campaigns: LiveCampaignProgress[];
  lastSyncedAt?: string;
  config: {
    apiKey: string;
    agentId: string;
    fromNumber: string;
    agentVersion?: number;
  };
}

const DEFAULT_CONFIG = {
  apiKey: process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI',
  agentId: process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f',
  fromNumber: process.env.SARVAM_FROM_NUMBER || '+918071580297',
  agentVersion: Number(process.env.SARVAM_AGENT_VERSION || 27)
};

/**
 * Initializes or loads the database with ZERO mock data.
 * Real data is populated exclusively through uploaded cohorts and live verified webhooks.
 */
export function getSarvamDb(): SarvamDbSchema {
  try {
    if (!fs.existsSync(DB_PATH)) {
      const initialDb: SarvamDbSchema = {
        calls: [],
        campaigns: [
          {
            campaignId: 'camp-sai-garden-live',
            campaignName: 'Sai Garden 1 & 2 BHK Calling Sheet',
            totalContacts: 0,
            completedCalls: 0,
            remainingCalls: 0,
            ongoingCalls: 0,
            successfulCalls: 0,
            failedCalls: 0,
            interestedCount: 0,
            siteVisitCount: 0,
            startedAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            status: 'idle',
            currentBatchFile: ''
          }
        ],
        config: DEFAULT_CONFIG
      };

      const dir = path.dirname(DB_PATH);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(DB_PATH, JSON.stringify(initialDb, null, 2), 'utf-8');
      return initialDb;
    }

    const content = fs.readFileSync(DB_PATH, 'utf-8');
    const parsed = JSON.parse(content);

    // Self-healing migration: Any legacy version (< 26) must be automatically upgraded to v27 (Latest Gayatri with Ishita voice)
    let needsSave = false;
    if (!parsed.config) {
      parsed.config = { ...DEFAULT_CONFIG };
      needsSave = true;
    } else if (!parsed.config.agentVersion || Number(parsed.config.agentVersion) < 26) {
      parsed.config.agentVersion = 27;
      needsSave = true;
    }

    if (Array.isArray(parsed.campaigns)) {
      for (const camp of parsed.campaigns) {
        if (camp.settings) {
          if (!camp.settings.agentVersion || Number(camp.settings.agentVersion) < 26) {
            camp.settings.agentVersion = 27;
            needsSave = true;
          }
        }
      }
    }

    if (needsSave) {
      try {
        fs.writeFileSync(DB_PATH, JSON.stringify(parsed, null, 2), 'utf-8');
      } catch (saveErr) {
        console.error('Failed to auto-heal sarvam_db.json on disk:', saveErr);
      }
    }

    return parsed;
  } catch (err) {
    console.error('Error reading sarvam_db.json:', err);
    return {
      calls: [],
      campaigns: [],
      config: DEFAULT_CONFIG
    };
  }
}

/**
 * Persists database to disk safely
 */
export function saveSarvamDb(db: SarvamDbSchema): void {
  try {
    const dir = path.dirname(DB_PATH);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf-8');
  } catch (err) {
    console.error('Error saving sarvam_db.json:', err);
  }
}

/**
 * Returns Indian Standard Time (IST) date string: "YYYY-MM-DD"
 */
export function getIstDateString(isoDateStr?: string | Date): string {
  try {
    const d = isoDateStr ? new Date(isoDateStr) : new Date();
    if (isNaN(d.getTime())) return new Date().toISOString().slice(0, 10);
    return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  } catch {
    return (typeof isoDateStr === 'string' ? isoDateStr : new Date().toISOString()).slice(0, 10);
  }
}

/**
 * Time filter helper: filters call records based on user selected time window in Indian Standard Time (IST)
 */
export function filterCallsByPeriod(calls: SarvamCallRecord[], period: TimeFilterPeriod): SarvamCallRecord[] {
  if (period === 'all') return calls;

  // Compute midnight IST for precise Indian timezone filtering
  const todayIst = getIstDateString(); // e.g. "2026-11-05"
  const startOfToday = new Date(`${todayIst}T00:00:00+05:30`).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const endOfYesterday = startOfToday;
  const start7DaysAgo = startOfToday - 6 * 86400000; // Past 7 full calendar days
  const start30DaysAgo = startOfToday - 29 * 86400000; // Past 30 full calendar days

  return calls.filter(c => {
    const callTime = new Date(c.callDate).getTime();
    switch (period) {
      case 'today':
        return callTime >= startOfToday;
      case 'yesterday':
        return callTime >= startOfYesterday && callTime < endOfYesterday;
      case 'last_7_days':
        return callTime >= start7DaysAgo;
      case 'last_30_days':
        return callTime >= start30DaysAgo;
      default:
        return true;
    }
  });
}

/**
 * Computes deep analytics summaries strictly from real recorded data
 */
export function computeAnalytics(calls: SarvamCallRecord[]): SarvamAnalyticsSummary {
  const totalCalls = calls.length;
  // A call is considered connected if durationSeconds > 0 and not marked No Answer
  const connectedCalls = calls.filter(c => (c.durationSeconds && c.durationSeconds > 0) && c.outcome !== 'No Answer');
  const totalDuration = connectedCalls.reduce((acc, c) => acc + (c.durationSeconds || 0), 0);
  const avgDuration = connectedCalls.length > 0 ? Math.round(totalDuration / connectedCalls.length) : 0;
  const connectionRate = totalCalls > 0 ? Math.round((connectedCalls.length / totalCalls) * 100) : 0;

  const interestedCalls = calls.filter(c => c.outcome === 'Interested');
  const siteVisitCalls = calls.filter(c => c.outcome === 'Site Visit');
  const notInterestedCalls = calls.filter(c => c.outcome === 'Not Interested');

  const oneBhkCount = calls.filter(c => c.bhkPreference === '1 BHK').length;
  const twoBhkCount = calls.filter(c => c.bhkPreference === '2 BHK').length;

  const trendMap: Record<string, { calls: number; interested: number; siteVisits: number }> = {};
  for (const c of calls) {
    const dateStr = getIstDateString(c.callDate);
    if (!trendMap[dateStr]) {
      trendMap[dateStr] = { calls: 0, interested: 0, siteVisits: 0 };
    }
    trendMap[dateStr].calls++;
    if (c.outcome === 'Interested') trendMap[dateStr].interested++;
    if (c.outcome === 'Site Visit') trendMap[dateStr].siteVisits++;
  }

  // Sort daily trends DESCENDING so the most recent dates (Today / Yesterday) appear at the top!
  const dailyTrends = Object.entries(trendMap)
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, counts]) => ({ date, ...counts }));

  return {
    totalCalls,
    totalDurationSeconds: Math.round(totalDuration),
    avgDurationSeconds: avgDuration,
    connectionRate,
    connectedCallsCount: connectedCalls.length,
    interestedCount: interestedCalls.length,
    interestedRate: totalCalls > 0 ? Math.round((interestedCalls.length / totalCalls) * 100) : 0,
    siteVisitCount: siteVisitCalls.length,
    siteVisitRate: totalCalls > 0 ? Math.round((siteVisitCalls.length / totalCalls) * 100) : 0,
    notInterestedCount: notInterestedCalls.length,
    oneBhkCount,
    twoBhkCount,
    dailyTrends,
    hourlyDistribution: []
  };
}
