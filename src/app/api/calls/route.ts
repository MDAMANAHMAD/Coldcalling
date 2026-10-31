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
 * Calculates a realistic future scheduled appointment date from the day string or summary
 */
function calculateScheduledDate(callDateStr: string, dayStr: string, timeStr?: string): string {
  const callDate = new Date(callDateStr);
  const now = new Date();
  
  // Parse hour & min from timeStr e.g. "03:00 PM" or "11:00 AM"
  let hour = 11;
  let minute = 0;
  if (timeStr) {
    const match = timeStr.match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/i);
    if (match) {
      let h = parseInt(match[1], 10);
      const m = match[2] ? parseInt(match[2], 10) : 0;
      const ampm = match[3]?.toUpperCase();
      if (ampm === 'PM' && h < 12) h += 12;
      if (ampm === 'AM' && h === 12) h = 0;
      hour = h;
      minute = m;
    }
  }

  // Calculate upcoming target day
  const targetDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hour, minute, 0);
  const currentDayOfWeek = targetDate.getDay(); // 0 is Sunday, 6 is Saturday

  if (dayStr === 'Sunday') {
    const daysUntilSunday = (7 - currentDayOfWeek) % 7 || 7;
    targetDate.setDate(targetDate.getDate() + daysUntilSunday);
  } else if (dayStr === 'Saturday') {
    const daysUntilSaturday = (6 - currentDayOfWeek + 7) % 7 || 7;
    targetDate.setDate(targetDate.getDate() + daysUntilSaturday);
  } else if (dayStr.includes('Monday')) {
    const daysUntilMonday = (1 - currentDayOfWeek + 7) % 7 || 7;
    targetDate.setDate(targetDate.getDate() + daysUntilMonday);
  } else {
    // Default to upcoming Saturday
    const daysUntilWeekend = (6 - currentDayOfWeek + 7) % 7 || 7;
    targetDate.setDate(targetDate.getDate() + daysUntilWeekend);
  }

  return targetDate.toISOString();
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const period = (searchParams.get('period') as TimeFilterPeriod) || 'all';
    const category = searchParams.get('category'); // 'Interested' | 'Site Visit' | 'high_intent' | 'Connected'
    const futurePeriod = searchParams.get('futurePeriod'); // 'all_upcoming' | 'this_weekend' | 'next_7_days' | 'next_30_days' | 'all'

    const db = getSarvamDb();

    // 1. Sync live interactions directly from Sarvam AI Analytics API
    try {
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
          let siteVisitTime: string | undefined = undefined;
          let scheduledVisitDate: string | undefined = undefined;

          if (lowerSummary.includes('2 bhk') || lowerSummary.includes('2bhk')) {
            bhkPref = '2 BHK';
          } else if (lowerSummary.includes('1 bhk') || lowerSummary.includes('1bhk')) {
            bhkPref = '1 BHK';
          }

          const isDeclinedVisit = ['declined to schedule', 'unable to schedule', 'refused', 'not interested in visit', 'not interested in scheduling', 'did not agree', 'evasive', 'will inform later'].some(d => lowerSummary.includes(d));
          const isConfirmedVisit = ['scheduled a site visit', 'agreed to a site visit', 'confirmed a site visit', 'booked a site visit'].some(c => lowerSummary.includes(c));

          if (isConfirmedVisit && !isDeclinedVisit) {
            outcome = 'Site Visit';
            if (lowerSummary.includes('sunday')) siteVisitDay = 'Sunday';
            else if (lowerSummary.includes('saturday')) siteVisitDay = 'Saturday';
            else if (lowerSummary.includes('monday')) siteVisitDay = 'Monday';
            else siteVisitDay = 'Upcoming Weekend';

            // Extract time
            const timeMatch = lowerSummary.match(/(\d{1,2}(?::\d{2})?\s*(?:am|pm))/);
            if (timeMatch) {
              siteVisitTime = timeMatch[1].toUpperCase();
            } else if (lowerSummary.includes('evening')) {
              siteVisitTime = '05:00 PM';
            } else if (lowerSummary.includes('morning')) {
              siteVisitTime = '11:00 AM';
            } else {
              siteVisitTime = '02:00 PM';
            }

            scheduledVisitDate = calculateScheduledDate(item.start_datetime || new Date().toISOString(), siteVisitDay, siteVisitTime);
          } else if (
            lowerSummary.includes('inquired') ||
            lowerSummary.includes('interested') ||
            lowerSummary.includes('pricing') ||
            lowerSummary.includes('amenities') ||
            lowerSummary.includes('connectivity') ||
            lowerSummary.includes('whatsapp') ||
            (isDeclinedVisit && durationSeconds > 30) ||
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

          // Use our direct proxy endpoint for authenticated audio streaming
          const recordingUrl = `/api/recording?id=${encodeURIComponent(interactionId)}`;

          const existingIdx = db.calls.findIndex(c => c.id === interactionId || c.interactionId === interactionId);
          const callRecord: SarvamCallRecord = {
            id: interactionId,
            interactionId,
            customerName: item.agent_variables?.user_name && item.agent_variables.user_name !== 'Gayatari' 
              ? item.agent_variables.user_name 
              : fullPhone.startsWith('+') ? `Buyer ${fullPhone.slice(-4)}` : 'Valued Client',
            customerPhone: fullPhone, // Always FULL unmasked phone
            callDate: item.start_datetime ? new Date(item.start_datetime).toISOString() : new Date().toISOString(),
            durationSeconds,
            status: 'completed',
            outcome,
            bhkPreference: bhkPref,
            siteVisitDay,
            siteVisitTime,
            scheduledVisitDate,
            transcript: callSummary ? `[AI Conversation Summary]: ${callSummary}` : 'Outbound conversation completed on voice network.',
            recordingUrl,
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

        db.calls.sort((a, b) => new Date(b.callDate).getTime() - new Date(a.callDate).getTime());
      }
    } catch (apiErr) {
      console.error('Error syncing live Sarvam interactions:', apiErr);
    }

    // 2. Sync active campaign status without overwriting sheet pacing
    try {
      const campUrl = `https://apps.sarvam.ai/api/scheduling/v1/orgs/${ORG_ID}/workspaces/${WORKSPACE_ID}/campaigns?limit=5`;
      const campRes = await fetch(campUrl, {
        headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
        next: { revalidate: 30 }
      });
      if (campRes.ok) {
        const campData = await campRes.json();
        const activeCamp = (campData.items || []).find((c: any) => c.status === 'active');
        if (activeCamp) {
          if (!db.campaigns || db.campaigns.length === 0) {
            db.campaigns = [{} as any];
          }
          // Only update if an external campaign is actively running
          if (db.campaigns[0].status === 'running') {
            db.campaigns[0].campaignName = activeCamp.name || db.campaigns[0].campaignName;
          }
        } else {
          // No active campaign is running on voice platform: reset to 0 idle state
          if (db.campaigns && db.campaigns.length > 0) {
            if (db.campaigns[0].status === 'completed' || db.campaigns[0].status === 'idle') {
              db.campaigns[0].totalContacts = 0;
              db.campaigns[0].completedCalls = 0;
              db.campaigns[0].remainingCalls = 0;
              db.campaigns[0].ongoingCalls = 0;
              db.campaigns[0].interestedCount = 0;
              db.campaigns[0].siteVisitCount = 0;
              db.campaigns[0].status = 'idle';
              db.campaigns[0].currentBatchFile = '';
            }
          }
        }
      }
    } catch (cErr) {
      console.error('Error syncing active campaigns:', cErr);
    }

    saveSarvamDb(db);

    // Compute overall analytics summary
    const analytics = computeAnalytics(db.calls);

    let filteredCalls = db.calls;

    // Handle Category Filter
    if (category === 'Site Visit') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Site Visit');
      
      // Future filter for site visits (since site visits happen in future dates)
      if (futurePeriod && futurePeriod !== 'all') {
        const now = new Date();
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
        const in7Days = startOfToday + 7 * 86400000;
        const in30Days = startOfToday + 30 * 86400000;

        filteredCalls = filteredCalls.filter(c => {
          if (!c.scheduledVisitDate) return true;
          const visitTime = new Date(c.scheduledVisitDate).getTime();

          if (futurePeriod === 'all_upcoming') {
            return visitTime >= startOfToday;
          } else if (futurePeriod === 'this_weekend') {
            return c.siteVisitDay === 'Saturday' || c.siteVisitDay === 'Sunday' || c.siteVisitDay === 'Upcoming Weekend';
          } else if (futurePeriod === 'next_7_days') {
            return visitTime >= startOfToday && visitTime <= in7Days;
          } else if (futurePeriod === 'next_30_days') {
            return visitTime >= startOfToday && visitTime <= in30Days;
          }
          return true;
        });
      }
    } else if (category === 'Interested') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Interested');
      filteredCalls = filterCallsByPeriod(filteredCalls, period);
    } else if (category === 'high_intent') {
      // ONLY Site Visits and Interested Leads (for Home Page)
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Site Visit' || c.outcome === 'Interested');
      filteredCalls = filterCallsByPeriod(filteredCalls, period);
    } else if (category === 'Connected') {
      filteredCalls = filteredCalls.filter(c => c.outcome === 'Connected');
      filteredCalls = filterCallsByPeriod(filteredCalls, period);
    } else {
      // Default to period filtering
      filteredCalls = filterCallsByPeriod(filteredCalls, period);
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
