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
  };
}

const DEFAULT_CONFIG = {
  apiKey: process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI',
  agentId: process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f',
  fromNumber: process.env.SARVAM_FROM_NUMBER || '+918071580297'
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
 * Time filter helper: filters call records based on user selected time window
 */
export function filterCallsByPeriod(calls: SarvamCallRecord[], period: TimeFilterPeriod): SarvamCallRecord[] {
  if (period === 'all') return calls;

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const start7DaysAgo = now.getTime() - 7 * 86400000;
  const start30DaysAgo = now.getTime() - 30 * 86400000;

  return calls.filter(c => {
    const callTime = new Date(c.callDate).getTime();
    switch (period) {
      case 'today':
        return callTime >= startOfToday;
      case 'yesterday':
        return callTime >= startOfYesterday && callTime < startOfToday;
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
  const completedCalls = calls.filter(c => c.status === 'completed');
  const totalDuration = completedCalls.reduce((acc, c) => acc + (c.durationSeconds || 0), 0);
  const avgDuration = completedCalls.length > 0 ? Math.round(totalDuration / completedCalls.length) : 0;
  const connectionRate = totalCalls > 0 ? Math.round((completedCalls.length / totalCalls) * 100) : 0;

  const interestedCalls = calls.filter(c => c.outcome === 'Interested');
  const siteVisitCalls = calls.filter(c => c.outcome === 'Site Visit');
  const notInterestedCalls = calls.filter(c => c.outcome === 'Not Interested');

  const oneBhkCount = calls.filter(c => c.bhkPreference === '1 BHK').length;
  const twoBhkCount = calls.filter(c => c.bhkPreference === '2 BHK').length;

  const trendMap: Record<string, { calls: number; interested: number; siteVisits: number }> = {};
  for (const c of calls) {
    const dateStr = c.callDate ? c.callDate.slice(0, 10) : 'Unknown';
    if (!trendMap[dateStr]) {
      trendMap[dateStr] = { calls: 0, interested: 0, siteVisits: 0 };
    }
    trendMap[dateStr].calls++;
    if (c.outcome === 'Interested') trendMap[dateStr].interested++;
    if (c.outcome === 'Site Visit') trendMap[dateStr].siteVisits++;
  }

  const dailyTrends = Object.entries(trendMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, counts]) => ({ date, ...counts }));

  return {
    totalCalls,
    totalDurationSeconds: totalDuration,
    avgDurationSeconds: avgDuration,
    connectionRate,
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
