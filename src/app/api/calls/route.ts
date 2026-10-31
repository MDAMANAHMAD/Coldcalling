import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb, filterCallsByPeriod, computeAnalytics } from '@/lib/sarvamDb';
import { SarvamCallRecord, TimeFilterPeriod } from '@/lib/sarvamTypes';

export const dynamic = 'force-dynamic';

const API_KEY = process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI';
const AGENT_ID = process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f';
const ORG_ID = process.env.SARVAM_ORG_ID || '01a16c8c-0d2f-7ded-b3cb-6dedfbcc168e';
const WORKSPACE_ID = process.env.SARVAM_WORKSPACE_ID || '01a16c8c-0d68-778c-b5f4-fcd65dd809e6';
const FROM_NUMBER = process.env.SARVAM_FROM_NUMBER || '+918071580297';

/**
 * Fetches real, live calls and metrics directly from Sarvam API.
 * Retains high-intent calls (Site Visit & Interested) with full unmasked phone numbers.
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const period = (searchParams.get('period') as TimeFilterPeriod) || 'all';
    const category = searchParams.get('category'); // 'Interested' | 'Site Visit'

    const db = getSarvamDb();

    // 1. Sync live interactions directly from Sarvam AI Analytics API
    try {
      const now = new Date();
      const thirtyDaysAgo = new Date(now.getTime() - 45 * 86400000).toISOString();
      const endNow = now.toISOString();

      const sarvamUrl = `https://apps.sarvam.ai/api/analytics/v1/${ORG_ID}/${WORKSPACE_ID}/${AGENT_ID}/interactions?start_datetime=${thirtyDaysAgo}&end_datetime=${endNow}&limit=100`;

      const sarvamRes = await fetch(sarvamUrl, {
        headers: {
          'X-API-Key': API_KEY,
          'Content-Type': 'application/json'
        },
        next: { revalidate: 10 }
      });

      if (sarvamRes.ok) {
        const data = await sarvamRes.json();
        const items = data.items || [];

        for (const item of items) {
          const interactionId = item.interaction_id;
          const userContact = item.user_contact || item.user_contact_masked || '';
          
          // Ignore internal test email callers
          if (!userContact || userContact.includes('@')) continue;

          // Strictly unmasked full phone number e.g. +919920764663
          const cleanDigits = userContact.replace(/\D/g, '');
          const fullPhone = cleanDigits.length === 10 ? `+91${cleanDigits}` : userContact.startsWith('+') ? userContact : `+${cleanDigits}`;

          const durationSeconds = Math.round(item.duration_in_seconds || 0);
          const callSummary = item.agent_variables?.call_summary || '';
          const lowerSummary = callSummary.toLowerCase();

          // Classify Intent & Site Visits from verified summary
          let outcome: SarvamCallRecord['outcome'] = 'Other';
          let bhkPref: SarvamCallRecord['bhkPreference'] = undefined;
          let siteVisitDay: string | undefined = undefined;

          if (lowerSummary.includes('2 bhk') || lowerSummary.includes('2bhk')) {
            bhkPref = '2 BHK';
          } else if (lowerSummary.includes('1 bhk') || lowerSummary.includes('1bhk')) {
            bhkPref = '1 BHK';
          }

          if (
            lowerSummary.includes('scheduled a site visit') ||
            lowerSummary.includes('site visit') ||
            lowerSummary.includes('sunday') ||
            lowerSummary.includes('saturday') ||
            lowerSummary.includes('visit')
          ) {
            outcome = 'Site Visit';
            if (lowerSummary.includes('sunday')) siteVisitDay = 'Sunday';
            else if (lowerSummary.includes('saturday')) siteVisitDay = 'Saturday';
            else siteVisitDay = 'Weekend';
          } else if (
            lowerSummary.includes('inquired') ||
            lowerSummary.includes('interested') ||
            lowerSummary.includes('pricing') ||
            lowerSummary.includes('amenities') ||
            lowerSummary.includes('connectivity') ||
            lowerSummary.includes('whatsapp') ||
            durationSeconds > 40
          ) {
            outcome = 'Interested';
          } else if (lowerSummary.includes('not interested') || lowerSummary.includes('declined')) {
            outcome = 'Not Interested';
          }

          // RETAIN ONLY INTERESTED & SITE VISITS
          if (outcome === 'Interested' || outcome === 'Site Visit') {
            const existingIdx = db.calls.findIndex(c => c.id === interactionId || c.interactionId === interactionId);
            const callRecord: SarvamCallRecord = {
              id: interactionId,
              interactionId,
              customerName: item.agent_variables?.user_name && item.agent_variables.user_name !== 'Gayatari' ? item.agent_variables.user_name : 'Valued Client',
              customerPhone: fullPhone, // Always FULL unmasked phone
              callDate: item.start_datetime ? new Date(item.start_datetime).toISOString() : new Date().toISOString(),
              durationSeconds,
              status: 'completed',
              outcome,
              bhkPreference: bhkPref,
              siteVisitDay,
              transcript: callSummary ? `[AI Conversation Summary]: ${callSummary}` : 'Call completed on Sarvam AI network.',
              recordingUrl: item.audio_url || '',
              summary: callSummary || `Call completed with duration ${durationSeconds}s.`,
              agentId: AGENT_ID,
              fromNumber: FROM_NUMBER
            };

            if (existingIdx >= 0) {
              db.calls[existingIdx] = { ...db.calls[existingIdx], ...callRecord };
            } else {
              db.calls.push(callRecord);
            }
          }
        }

        saveSarvamDb(db);
      } else {
        console.warn('Sarvam API returned status:', sarvamRes.status);
      }
    } catch (apiErr) {
      console.error('Error syncing live Sarvam interactions:', apiErr);
    }

    // 2. Filter calls based on user selected time period
    let calls = filterCallsByPeriod(db.calls, period);

    if (category === 'Interested') {
      calls = calls.filter(c => c.outcome === 'Interested');
    } else if (category === 'Site Visit') {
      calls = calls.filter(c => c.outcome === 'Site Visit');
    }

    // Compute metrics
    const analytics = computeAnalytics(db.calls);
    const liveCampaign = db.campaigns[0] || null;

    return NextResponse.json({
      calls,
      analytics,
      liveCampaign,
      config: {
        agentId: AGENT_ID,
        fromNumber: FROM_NUMBER
      }
    });
  } catch (err: any) {
    console.error('Error in /api/calls route:', err);
    return NextResponse.json({ error: err.message || 'Internal error' }, { status: 500 });
  }
}
