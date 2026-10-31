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
 * Initializes or loads the dedicated Sarvam database
 */
export function getSarvamDb(): SarvamDbSchema {
  try {
    if (!fs.existsSync(DB_PATH)) {
      const initialDb: SarvamDbSchema = {
        calls: [],
        campaigns: [
          {
            campaignId: 'camp-sai-garden-initial',
            campaignName: 'Sai Garden 1 & 2 BHK Outreach',
            totalContacts: 100,
            completedCalls: 64,
            remainingCalls: 36,
            ongoingCalls: 2,
            successfulCalls: 58,
            failedCalls: 6,
            interestedCount: 14,
            siteVisitCount: 6,
            startedAt: new Date(Date.now() - 3600000 * 4).toISOString(),
            updatedAt: new Date().toISOString(),
            status: 'running',
            currentBatchFile: 'cohort_100_contacts.csv'
          }
        ],
        config: DEFAULT_CONFIG
      };

      // Seed initial high-quality records representing Gayatri Voice Agent calls
      initialDb.calls = [
        {
          id: 'sarvam-call-101',
          customerName: 'Prafull Bhosale',
          customerPhone: '+919821361686',
          callDate: new Date(Date.now() - 3600000 * 2).toISOString(),
          durationSeconds: 142,
          status: 'completed',
          outcome: 'Site Visit',
          bhkPreference: '2 BHK',
          siteVisitDay: 'Sunday',
          siteVisitTime: '4:00 PM',
          budget: '₹45 Lakh to ₹50 Lakh',
          transcript: `[0.2s] Gayatri: नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?
[3.5s] Prafull: नमस्ते। मुझे 2 BHK के बारे में जानना है।
[6.1s] Gayatri: बहुत बढ़िया! हमारा 2 BHK 45 लाख से शुरू है। G+22 मंजिला टॉवर और 35 से ज्यादा लग्जरी सुविधाएं हैं।
[15.4s] Prafull: डाउन पेमेंट कितना देना पड़ेगा?
[18.0s] Gayatri: 2 BHK के लिए 4.5 से 7 लाख के बीच डाउन पेमेंट रहेगा और बाकी 90% तक बैंक लोन SBI और HDFC से हो जाएगा।
[26.2s] Prafull: ठीक है, संडे को शाम 4 बजे आ सकता हूँ क्या?
[29.1s] Gayatri: बिल्कुल! आपकी साईट विजिट रविवार शाम 4:00 बजे के लिए कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। धन्यवाद!`,
          recordingUrl: '/api/recordings/call-raj-1789311501507.wav',
          summary: 'Client interested in 2 BHK flat at Sai Garden. Confirmed site visit appointment for Sunday at 4:00 PM.',
          agentId: DEFAULT_CONFIG.agentId,
          fromNumber: DEFAULT_CONFIG.fromNumber
        },
        {
          id: 'sarvam-call-102',
          customerName: 'Tanmay mandal',
          customerPhone: '+918879300743',
          callDate: new Date(Date.now() - 3600000 * 3.5).toISOString(),
          durationSeconds: 118,
          status: 'completed',
          outcome: 'Interested',
          bhkPreference: '1 BHK',
          budget: '₹30 Lakh to ₹35 Lakh',
          transcript: `[0.3s] Gayatri: नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?
[4.1s] Tanmay: मुझे 1 BHK का प्राइस जानना था।
[7.0s] Gayatri: 1 BHK सिर्फ 30 लाख से शुरू है और डाउन पेमेंट केवल 3 से 5 लाख तक आता है।
[14.2s] Tanmay: वाशी स्टेशन से कितनी दूरी पर है?
[17.3s] Gayatri: वाशी स्टेशन से लगभग 22 से 25 किलोमीटर की दूरी है, ऐरोली-काटई टनल से 35 से 40 मिनट लगते हैं।
[25.0s] Tanmay: बहुत अच्छा। मुझे ब्रोशर और फ्लोर प्लान व्हाट्सऐप पर भेजिए, मैं देखकर बताता हूँ।
[28.5s] Gayatri: ज़रूर! मैं तुरंत आपको साई गार्डन का पूरा ब्रोशर व्हाट्सऐप पर भेज रही हूँ।`,
          recordingUrl: '/api/recordings/call-raj-1789311501507.wav',
          summary: 'Client inquiring about 1 BHK pricing and Vashi connectivity. Requested brochure & floor plan on WhatsApp.',
          agentId: DEFAULT_CONFIG.agentId,
          fromNumber: DEFAULT_CONFIG.fromNumber
        },
        {
          id: 'sarvam-call-103',
          customerName: 'Maruti Nimbulkar',
          customerPhone: '+918652125570',
          callDate: new Date(Date.now() - 3600000 * 5).toISOString(),
          durationSeconds: 165,
          status: 'completed',
          outcome: 'Site Visit',
          bhkPreference: '2 BHK',
          siteVisitDay: 'Saturday',
          siteVisitTime: '11:00 AM',
          budget: '₹48 Lakh',
          transcript: `[0.2s] Gayatri: नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?
[3.8s] Maruti: 2 BHK चाहिए, पास में कोई अच्छे स्कूल या हॉस्पिटल हैं क्या?
[7.5s] Gayatri: जी बिल्कुल! लोढ़ा वर्ल्ड स्कूल सिर्फ 1.5 किलोमीटर, पवार पब्लिक स्कूल 2 किलोमीटर और नेप्च्यून सुपर स्पेशलिटी हॉस्पिटल 3 किलोमीटर पर है।
[19.2s] Maruti: बहुत बढ़िया, शनिवार को सुबह 11 बजे साईट देखने आऊंगा।
[22.8s] Gayatri: बिल्कुल! आपकी साईट विजिट शनिवार सुबह 11:00 बजे के लिए कन्फर्म कर दी है। धन्यवाद!`,
          recordingUrl: '/api/recordings/call-raj-1789311501507.wav',
          summary: 'Inquired about schools/hospitals nearby. Confirmed site visit for Saturday 11:00 AM for 2 BHK.',
          agentId: DEFAULT_CONFIG.agentId,
          fromNumber: DEFAULT_CONFIG.fromNumber
        },
        {
          id: 'sarvam-call-104',
          customerName: 'Rohit Pal',
          customerPhone: '+918108165388',
          callDate: new Date(Date.now() - 3600000 * 26).toISOString(),
          durationSeconds: 95,
          status: 'completed',
          outcome: 'Interested',
          bhkPreference: '2 BHK',
          budget: '₹45 Lakh',
          transcript: `[0.2s] Gayatri: नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से। आपको 1 BHK चाहिए या 2 BHK?
[3.4s] Rohit: 2 BHK। पजेशन कब तक मिलेगा?
[6.2s] Gayatri: हमारा काम तेज़ी से चालू है, स्टेज-वाइज कंस्ट्रक्शन लिंक्ड प्लान है।
[12.1s] Rohit: ठीक है, डिटेल्स व्हाट्सऐप पर भेजिए।`,
          recordingUrl: '/api/recordings/call-raj-1789311501507.wav',
          summary: 'Client interested in 2 BHK possession timeline and requested WhatsApp details.',
          agentId: DEFAULT_CONFIG.agentId,
          fromNumber: DEFAULT_CONFIG.fromNumber
        }
      ];

      fs.writeFileSync(DB_PATH, JSON.stringify(initialDb, null, 2), 'utf-8');
      return initialDb;
    }

    const content = fs.readFileSync(DB_PATH, 'utf-8');
    return JSON.parse(content);
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
 * Persists Sarvam database to disk safely
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
 * Computes deep analytics summaries
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

  // Daily trends map
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
