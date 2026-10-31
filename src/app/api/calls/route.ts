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
 * Retains high-intent calls (Site Visit & Interested) with full unmasked phone numbers,
 * while also tracking and displaying all campaign calls.
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const period = (searchParams.get('period') as TimeFilterPeriod) || 'all';
    const category = searchParams.get('category'); // 'Interested' | 'Site Visit' | 'Connected' | 'all'

    const db = getSarvamDb();

    // 1. Sync live interactions directly from Sarvam AI Analytics API
    try {
      const now = new Date();
      // Look back to start of month to capture all campaigns
      const startDate = '2026-10-01T00:00:00Z';
      const endDate = '2026-11-05T23:59:59Z';

      const sarvamUrl = `https://apps.sarvam.ai/api/analytics/v1/${ORG_ID}/${WORKSPACE_ID}/${AGENT_ID}/interactions?start_datetime=${startDate}&end_datetime=${endDate}&limit=250`;

      const sarvamRes = await fetch(sarvamUrl, {
        headers: {
          'X-API-Key': API_KEY,
          'Content-Type': 'application/json'
        },
        next: { revalidate: 15 }
      });

      if (sarvamRes.ok) {
        const data = await sarvamRes.json();
        const items = data.items || [];

        for (const item of items) {
          const interactionId = item.interaction_id;
          const userContact = item.user_contact || item.user_contact_masked || '';
          
          // Format phone number cleanly (always full unmasked if available)
          let fullPhone = userContact;
          if (userContact && !userContact.includes('@')) {
            const cleanDigits = userContact.replace(/\D/g, '');
            fullPhone = cleanDigits.length === 10 ? `+91${cleanDigits}` : userContact.startsWith('+') ? userContact : `+${cleanDigits}`;
          } else if (userContact.includes('@')) {
            fullPhone = `Web Tester (${userContact.split('@')[0]})`;
          }

          const durationSeconds = Math.round((item.duration_in_seconds || 0) * 10) / 10;
          const callSummary = item.agent_variables?.call_summary || '';
          const lowerSummary = callSummary.toLowerCase();

          // Classify Intent & Site Visits from verified summary
          let outcome: SarvamCallRecord['outcome'] = 'Connected';
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
            durationSeconds > 35
          ) {
            outcome = 'Interested';
          } else if (lowerSummary.includes('not interested') || lowerSummary.includes('declined') || lowerSummary.includes('hung up')) {
            outcome = 'Not Interested';
          } else if (durationSeconds === 0) {
            outcome = 'No Answer';
          } else {
            outcome = 'Connected';
          }

          const existingIdx = db.calls.findIndex(c => c.id === interactionId || c.interactionId === interactionId);
          const callRecord: SarvamCallRecord = {
            id: interactionId,
            interactionId,
            customerName: item.agent_variables?.user_name && item.agent_variables.user_name !== 'Gayatari' 
              ? item.agent_variables.user_name 
              : fullPhone.startsWith('+') ? `Prospect ${fullPhone.slice(-4)}` : 'Valued Client',
            customerPhone: fullPhone, // Always FULL unmasked phone
            callDate: item.start_datetime ? new Date(item.start_datetime).toISOString() : new Date().toISOString(),
            durationSeconds,
            status: 'completed',
            outcome,
            bhkPreference: bhkPref,
            siteVisitDay,
            transcript: callSummary ? `[AI Conversation Summary]: ${callSummary}` : 'Outbound conversation completed on voice network.',
            recordingUrl: item.audio_url || '',
            summary: callSummary || `Call completed with duration ${durationSeconds}s.`,
            agentId: AGENT_ID,
            fromNumber: FROM_NUMBER,
            language: item.language_name || 'Hindi',
            numMessages: item.num_messages || 1
          };

          if (existingIdx >= 0) {
            db.calls[existingIdx] = { ...db.calls[existingIdx], ...callRecord };
          } else {
            db.calls.push(callRecord);
          }
        }

        // Sort descending by call date (newest calls first)
        db.calls.sort((a, b) => new Date(b.callDate).getTime() - new Date(a.callDate).getTime());
      }
    } catch (apiErr) {
      console.error('Error syncing live Sarvam interactions:', apiErr);
    }

    // 2. Sync active campaign from Sarvam Scheduling API
    try {
      const campUrl = `https://apps.sarvam.ai/api/scheduling/v1/orgs/${ORG_ID}/workspaces/${WORKSPACE_ID}/campaigns?limit=5`;
      const campRes = await fetch(campUrl, {
        headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
        next: { revalidate: 30 }
      });
      if (campRes.ok) {
        const campData = await campRes.json();
        const activeCamp = (campData.items || []).find((c: any) => c.status === 'active') || campData.items?.[0];
        if (activeCamp) {
          if (!db.campaigns || db.campaigns.length === 0) {
            db.campaigns = [{} as any];
          }
          db.campaigns[0] = {
            ...db.campaigns[0],
            campaignId: activeCamp.campaign_id,
            campaignName: activeCamp.name || 'Sai Garden Calling Campaign',
            status: activeCamp.status === 'active' ? 'running' : (activeCamp.status as any),
            startedAt: activeCamp.start_timestamp || new Date().toISOString(),
            updatedAt: activeCamp.updated_at || new Date().toISOString(),
            totalContacts: activeCamp.stats?.total_users || db.campaigns[0]?.totalContacts || db.calls.length,
            completedCalls: db.calls.length,
            remainingCalls: Math.max(0, (activeCamp.stats?.total_users || db.calls.length) - db.calls.length)
          };
        }
      }
    } catch (cErr) {
      console.error('Error syncing active campaigns:', cErr);
    }

    // Save synced database
    saveSarvamDb(db);

    // 3. Filter calls based on user selected time period
    let filteredCalls = filterCallsByPeriod(db.calls, period);

    // 4. Compute analytics summary based on period
    const analytics = computeAnalytics(filteredCalls);

    // 5. Apply category filter if requested
    if (category === 'Interested') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Interested');
    } else if (category === 'Site Visit') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Site Visit');
    } else if (category === 'Connected') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Connected');
    }

    const liveCampaign = db.campaigns[0] || null;

    return NextResponse.json({
      calls: filteredCalls,
      analytics,
      liveCampaign,
      totalCallsCount: db.calls.length,
      config: {
        agentId: AGENT_ID,
        fromNumber: FROM_NUMBER,
        orgId: ORG_ID
      }
    });
  } catch (err: any) {
    console.error('API Error /api/calls:', err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
