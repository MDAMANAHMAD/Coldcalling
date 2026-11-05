import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb, filterCallsByPeriod, computeAnalytics, getIstDateString } from '@/lib/sarvamDb';
import { SarvamCallRecord, TimeFilterPeriod } from '@/lib/sarvamTypes';

export const dynamic = 'force-dynamic';

const API_KEY = process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI';
const AGENT_ID = process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f';
const ORG_ID = process.env.SARVAM_ORG_ID || '01a16c8c-0d2f-7ded-b3cb-6dedfbcc168e';
const WORKSPACE_ID = process.env.SARVAM_WORKSPACE_ID || '01a16c8c-0d68-778c-b5f4-fcd65dd809e6';
const FROM_NUMBER = process.env.SARVAM_FROM_NUMBER || '+918071580297';

/**
 * Calculates a realistic scheduled appointment date from the call date and summary/day string.
 * Strictly anchored to callDateStr (the timestamp the call was made).
 */
export function calculateScheduledDate(callDateStr: string, dayStr?: string, timeStr?: string, summaryText?: string): string {
  const callDate = new Date(callDateStr);
  const baseDate = isNaN(callDate.getTime()) ? new Date() : callDate;
  
  // Parse hour & min from timeStr e.g. "03:00 PM" or "11:00 AM"
  let hour = 14; // Default to 2:00 PM
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

  const combinedText = `${dayStr || ''} ${summaryText || ''}`.toLowerCase();

  // 1. Check for explicit date in the text e.g. "28th October", "2nd November", "Nov 5"
  const monthNames: Record<string, number> = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11
  };
  const expMatch1 = combinedText.match(/(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*/i);
  const expMatch2 = combinedText.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?/i);

  if (expMatch1) {
    const day = parseInt(expMatch1[1], 10);
    const month = monthNames[expMatch1[2].toLowerCase().slice(0, 3)];
    let year = baseDate.getFullYear();
    if (month < baseDate.getMonth() - 2) year += 1;
    return new Date(year, month, day, hour, minute, 0).toISOString();
  } else if (expMatch2) {
    const month = monthNames[expMatch2[1].toLowerCase().slice(0, 3)];
    const day = parseInt(expMatch2[2], 10);
    let year = baseDate.getFullYear();
    if (month < baseDate.getMonth() - 2) year += 1;
    return new Date(year, month, day, hour, minute, 0).toISOString();
  }

  // 2. Relative calculation anchored strictly to baseDate (callDate)
  const callDay = baseDate.getDay(); // 0 = Sun, 1 = Mon, ..., 6 = Sat
  const isNextWeekend = combinedText.includes('next weekend') || combinedText.includes('अगले वीकेंड') || combinedText.includes('following weekend') || combinedText.includes('next sat') || combinedText.includes('next sun');
  const isTomorrow = combinedText.includes('tomorrow') || combinedText.includes('कल');

  let daysToAdd = 0;

  if (isTomorrow) {
    daysToAdd = 1;
  } else if (combinedText.includes('sunday') || combinedText.includes('रविवार')) {
    const daysUntilSun = (7 - callDay) % 7 || 7;
    daysToAdd = daysUntilSun + (isNextWeekend ? 7 : 0);
  } else if (combinedText.includes('saturday') || combinedText.includes('शनिवार')) {
    const daysUntilSat = (6 - callDay + 7) % 7 || 7;
    daysToAdd = daysUntilSat + (isNextWeekend ? 7 : 0);
  } else if (combinedText.includes('monday') || combinedText.includes('सोमवार')) {
    daysToAdd = (1 - callDay + 7) % 7 || 7;
  } else {
    // Default: Weekend (Saturday)
    if (callDay === 6) {
      daysToAdd = isNextWeekend ? 7 : 0;
    } else if (callDay === 0) {
      daysToAdd = isNextWeekend ? 6 : 0;
    } else {
      const daysUntilSat = 6 - callDay;
      daysToAdd = daysUntilSat + (isNextWeekend ? 7 : 0);
    }
  }

  const target = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate() + daysToAdd, hour, minute, 0);
  return target.toISOString();
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
      const endDate = new Date(Date.now() + 86400000).toISOString();
      const sarvamUrl = `https://apps.sarvam.ai/api/analytics/v1/${ORG_ID}/${WORKSPACE_ID}/${AGENT_ID}/interactions?start_datetime=${startDate}&end_datetime=${endDate}&limit=1000`;

      const sarvamRes = await fetch(sarvamUrl, {
        headers: {
          'X-API-Key': API_KEY,
          'Content-Type': 'application/json'
        },
        cache: 'no-store'
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

          if (lowerSummary.includes('1 bhk') && lowerSummary.includes('2 bhk')) {
            // If both mentioned, prioritize the last preference mentioned in conversation
            const idx1 = lowerSummary.lastIndexOf('1 bhk');
            const idx2 = lowerSummary.lastIndexOf('2 bhk');
            bhkPref = idx1 > idx2 ? '1 BHK' : '2 BHK';
          } else if (lowerSummary.includes('2 bhk') || lowerSummary.includes('2bhk')) {
            bhkPref = '2 BHK';
          } else if (lowerSummary.includes('1 bhk') || lowerSummary.includes('1bhk')) {
            bhkPref = '1 BHK';
          }

          const isDeclinedVisit = ['declined to schedule', 'unable to schedule', 'refused', 'not interested in visit', 'not interested in scheduling', 'did not agree', 'evasive', 'will inform later'].some(d => lowerSummary.includes(d));
          const isConfirmedVisit = ['scheduled a site visit', 'agreed to a site visit', 'confirmed a site visit', 'booked a site visit'].some(c => lowerSummary.includes(c));

          if (isConfirmedVisit && !isDeclinedVisit) {
            outcome = 'Site Visit';
            if (lowerSummary.includes('next weekend') || lowerSummary.includes('अगले वीकेंड')) siteVisitDay = 'Next Weekend';
            else if (lowerSummary.includes('sunday')) siteVisitDay = 'Sunday';
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

            scheduledVisitDate = calculateScheduledDate(item.start_datetime || new Date().toISOString(), siteVisitDay, siteVisitTime, callSummary);
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

          const isConnected = durationSeconds > 0 && outcome !== 'No Answer';
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
            status: isConnected ? 'completed' : 'no-answer',
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

    // Ensure all stored site visit records have their scheduledVisitDate properly anchored to their callDate
    for (const c of db.calls) {
      if (c.outcome === 'Site Visit') {
        c.scheduledVisitDate = calculateScheduledDate(c.callDate, c.siteVisitDay, c.siteVisitTime, c.summary || c.transcript);
      }
    }

    saveSarvamDb(db);

    // 1. Strictly filter calls for the user-selected period (Today, Yesterday, Last 7 Days, Last 30 Days, All Time)
    const periodCalls = filterCallsByPeriod(db.calls, period);

    // 2. Compute analytics dynamically matching the selected time window!
    const analytics = computeAnalytics(periodCalls);

    let filteredCalls = periodCalls;

    // Use IST today for appointment and date bound calculations
    const todayIst = getIstDateString();
    const startOfToday = new Date(`${todayIst}T00:00:00+05:30`).getTime();
    const nowIst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const currentDay = nowIst.getDay(); // 0 is Sunday, 6 is Saturday

    // Handle Category Filter
    if (category === 'Site Visit') {
      // Upcoming site visits are drawn from db.calls (or periodCalls if specific period requested)
      const baseSiteVisitCalls = period === 'all' ? db.calls : periodCalls;
      filteredCalls = baseSiteVisitCalls.filter(c => c.outcome === 'Site Visit');

      // Calculate this weekend bounds (upcoming Sat/Sun relative to today in IST)
      let thisWeekendStart: number;
      let thisWeekendEnd: number;
      if (currentDay === 0) {
        // Today is Sunday of this weekend
        thisWeekendStart = startOfToday;
        thisWeekendEnd = startOfToday + 86400000 - 1;
      } else if (currentDay === 6) {
        // Today is Saturday of this weekend
        thisWeekendStart = startOfToday;
        thisWeekendEnd = startOfToday + 2 * 86400000 - 1;
      } else {
        // Monday to Friday
        const daysToSat = 6 - currentDay;
        thisWeekendStart = startOfToday + daysToSat * 86400000;
        thisWeekendEnd = thisWeekendStart + 2 * 86400000 - 1;
      }

      // Calculate next weekend bounds (following week's Sat/Sun)
      let nextWeekendStart: number;
      let nextWeekendEnd: number;
      if (currentDay === 0) {
        nextWeekendStart = startOfToday + 6 * 86400000;
        nextWeekendEnd = nextWeekendStart + 2 * 86400000 - 1;
      } else if (currentDay === 6) {
        nextWeekendStart = startOfToday + 7 * 86400000;
        nextWeekendEnd = nextWeekendStart + 2 * 86400000 - 1;
      } else {
        const daysToNextSat = (6 - currentDay) + 7;
        nextWeekendStart = startOfToday + daysToNextSat * 86400000;
        nextWeekendEnd = nextWeekendStart + 2 * 86400000 - 1;
      }

      const in7Days = startOfToday + 7 * 86400000;
      const in30Days = startOfToday + 30 * 86400000;

      // Filter site visits: strictly exclude visits whose appointment date has already passed!
      filteredCalls = filteredCalls.filter(c => {
        const visitDateStr = c.scheduledVisitDate || calculateScheduledDate(c.callDate, c.siteVisitDay, c.siteVisitTime, c.summary);
        if (!visitDateStr) return false;
        const visitTime = new Date(visitDateStr).getTime();

        // STRICT RULE: "and the data whose site visit date is already passed then its data should be not visible"
        if (visitTime < startOfToday) {
          return false;
        }

        if (futurePeriod === 'this_weekend') {
          return visitTime >= thisWeekendStart && visitTime <= thisWeekendEnd;
        } else if (futurePeriod === 'next_weekend') {
          return visitTime >= nextWeekendStart && visitTime <= nextWeekendEnd;
        } else if (futurePeriod === 'next_7_days') {
          return visitTime >= startOfToday && visitTime <= in7Days;
        } else if (futurePeriod === 'next_30_days') {
          return visitTime >= startOfToday && visitTime <= in30Days;
        }

        // Default ('all_upcoming' or 'all'): all future visits whose date is not passed
        return visitTime >= startOfToday;
      });

      // Sort upcoming visits so the closest upcoming date is shown first
      filteredCalls.sort((a, b) => {
        const tA = a.scheduledVisitDate ? new Date(a.scheduledVisitDate).getTime() : 0;
        const tB = b.scheduledVisitDate ? new Date(b.scheduledVisitDate).getTime() : 0;
        return tA - tB;
      });
    } else if (category === 'Interested') {
      filteredCalls = periodCalls.filter(c => c.outcome === 'Interested');
    } else if (category === 'high_intent') {
      // ONLY Site Visits and Interested Leads (for Home Page)
      // Exclude site visits whose appointment date has already passed
      filteredCalls = periodCalls.filter(c => {
        if (c.outcome === 'Interested') return true;
        if (c.outcome === 'Site Visit') {
          const visitDateStr = c.scheduledVisitDate || calculateScheduledDate(c.callDate, c.siteVisitDay, c.siteVisitTime, c.summary);
          if (!visitDateStr) return false;
          const visitTime = new Date(visitDateStr).getTime();
          return visitTime >= startOfToday;
        }
        return false;
      });
    } else if (category === 'Connected') {
      filteredCalls = periodCalls.filter(c => c.outcome === 'Connected');
    } else {
      // Default to all period calls
      filteredCalls = periodCalls;
    }

    const liveCampaign = db.campaigns[0] || null;

    return NextResponse.json({
      calls: filteredCalls,
      analytics,
      allTimeAnalytics: computeAnalytics(db.calls),
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
