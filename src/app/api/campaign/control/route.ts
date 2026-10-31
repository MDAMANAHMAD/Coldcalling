import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb } from '@/lib/sarvamDb';
import { CampaignSettings } from '@/lib/sarvamTypes';

export const dynamic = 'force-dynamic';

const API_KEY = process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI';
const AGENT_ID = process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f';
const ORG_ID = process.env.SARVAM_ORG_ID || '01a16c8c-0d2f-7ded-b3cb-6dedfbcc168e';
const WORKSPACE_ID = process.env.SARVAM_WORKSPACE_ID || '01a16c8c-0d68-778c-b5f4-fcd65dd809e6';
const CONNECTION_ID = 'Vobiz-MD-s--9a5a5823-1853';
const FROM_NUMBER = '+918071580297';

export async function POST(req: NextRequest) {
  try {
    const { action, batchFileName, totalContacts, contacts, settings, testPhoneNumber } = await req.json();
    const db = getSarvamDb();

    // Handle instant test dial
    if (action === 'test-dial') {
      if (!testPhoneNumber) {
        return NextResponse.json({ error: 'testPhoneNumber is required for test dial' }, { status: 400 });
      }

      const cleanDigits = testPhoneNumber.replace(/\D/g, '');
      const fullPhone = cleanDigits.length === 10 ? `+91${cleanDigits}` : testPhoneNumber.startsWith('+') ? testPhoneNumber : `+${cleanDigits}`;

      const outboundUrl = `https://apps.sarvam.ai/api/outbounds/v1/orgs/${ORG_ID}/workspaces/${WORKSPACE_ID}/outbounds`;
      const payload = {
        app_config: {
          app_id: settings?.agentId || AGENT_ID,
          app_version: settings?.agentVersion || 2,
          connection_config: {
            connection_id: settings?.connectionId || CONNECTION_ID,
            agent_phone_number: settings?.fromNumber || FROM_NUMBER
          }
        },
        user_config: {
          user_phone_number: fullPhone
        }
      };

      const res = await fetch(outboundUrl, {
        method: 'POST',
        headers: {
          'X-API-Key': API_KEY,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errText = await res.text();
        return NextResponse.json({ error: `Test dial failed (${res.status}): ${errText}` }, { status: res.status });
      }

      const resData = await res.json();
      return NextResponse.json({ success: true, message: `Test dial initiated to ${fullPhone}`, attempt_id: resData.attempt_id });
    }

    if (!db.campaigns || db.campaigns.length === 0) {
      db.campaigns = [{
        campaignId: `camp-${Date.now()}`,
        campaignName: settings?.campaignName || 'Sai Garden 1 & 2 BHK Calling Sheet',
        totalContacts: totalContacts || 0,
        completedCalls: 0,
        remainingCalls: totalContacts || 0,
        ongoingCalls: 0,
        successfulCalls: 0,
        failedCalls: 0,
        interestedCount: 0,
        siteVisitCount: 0,
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        status: 'idle',
        currentBatchFile: batchFileName || '',
        settings
      }];
    }

    const campaign = db.campaigns[0];

    if (action === 'start') {
      const contactCount = (Array.isArray(contacts) ? contacts.length : totalContacts) || 0;
      campaign.status = 'running';
      campaign.totalContacts = contactCount;
      campaign.completedCalls = 0;
      campaign.remainingCalls = contactCount;
      campaign.ongoingCalls = contactCount > 0 ? 1 : 0;
      campaign.interestedCount = 0;
      campaign.siteVisitCount = 0;
      if (settings?.campaignName) {
        campaign.campaignName = settings.campaignName;
      }
      if (settings) {
        campaign.settings = settings;
      }
      if (batchFileName) {
        campaign.currentBatchFile = batchFileName;
      }
      campaign.updatedAt = new Date().toISOString();
      saveSarvamDb(db);

      // Trigger pacing dispatch for contacts in this specific sheet
      if (Array.isArray(contacts) && contacts.length > 0) {
        const cps = settings?.attemptsPerSecond || 0.5;
        const delayBetweenCallsMs = Math.max(500, Math.round(1000 / cps));
        console.log(`🚀 [Campaign Trigger]: Triggering live outbound calls for ${contacts.length} numbers at ${cps} CPS (${delayBetweenCallsMs}ms delay)...`);
        
        (async () => {
          let dialedCount = 0;
          for (const c of contacts) {
            // Check if campaign was paused or stopped mid-way
            const currentDb = getSarvamDb();
            if (currentDb.campaigns?.[0]?.status !== 'running') {
              console.log(`⏸️ Campaign was paused or stopped. Halting dialer loop.`);
              break;
            }

            const rawPhone = c.phone_number || c.phone || '';
            const cleanDigits = rawPhone.replace(/\D/g, '');
            if (cleanDigits.length < 10) continue;
            const fullPhone = cleanDigits.length === 10 ? `+91${cleanDigits}` : rawPhone.startsWith('+') ? rawPhone : `+${cleanDigits}`;

            try {
              const outboundUrl = `https://apps.sarvam.ai/api/outbounds/v1/orgs/${ORG_ID}/workspaces/${WORKSPACE_ID}/outbounds`;
              const payload = {
                app_config: {
                  app_id: settings?.agentId || AGENT_ID,
                  app_version: settings?.agentVersion || 2,
                  connection_config: {
                    connection_id: settings?.connectionId || CONNECTION_ID,
                    agent_phone_number: settings?.fromNumber || FROM_NUMBER
                  }
                },
                user_config: {
                  user_phone_number: fullPhone
                }
              };

              const res = await fetch(outboundUrl, {
                method: 'POST',
                headers: {
                  'X-API-Key': API_KEY,
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
              });

              if (res.ok) {
                const resData = await res.json();
                console.log(`✅ [Outbound Call Placed]: ${fullPhone} (attempt_id: ${resData.attempt_id})`);
              } else {
                const errText = await res.text();
                console.warn(`⚠️ [Outbound Call Warning]: ${fullPhone} status: ${res.status} - ${errText}`);
              }
            } catch (dialErr) {
              console.error(`❌ [Outbound Call Failed]: ${fullPhone}`, dialErr);
            }

            dialedCount++;
            const liveDb = getSarvamDb();
            if (liveDb.campaigns?.[0]) {
              liveDb.campaigns[0].completedCalls = dialedCount;
              liveDb.campaigns[0].remainingCalls = Math.max(0, contactCount - dialedCount);
              liveDb.campaigns[0].updatedAt = new Date().toISOString();
              saveSarvamDb(liveDb);
            }

            // Pacing delay based on attempts_per_second configuration
            await new Promise(r => setTimeout(r, delayBetweenCallsMs));
          }

          // When sheet dialing finishes completely, reset live dialer numbers to 0 as requested
          const finalDb = getSarvamDb();
          if (finalDb.campaigns?.[0]) {
            finalDb.campaigns[0].status = 'idle';
            finalDb.campaigns[0].completedCalls = 0;
            finalDb.campaigns[0].remainingCalls = 0;
            finalDb.campaigns[0].totalContacts = 0;
            finalDb.campaigns[0].ongoingCalls = 0;
            finalDb.campaigns[0].currentBatchFile = '';
            finalDb.campaigns[0].updatedAt = new Date().toISOString();
            saveSarvamDb(finalDb);
            console.log(`🏁 [Campaign Finished]: All numbers in sheet dialed. Live controller reset to 0.`);
          }
        })().catch(err => console.error('Background batch dialer error:', err));
      }
    } else if (action === 'pause') {
      campaign.status = 'paused';
      campaign.ongoingCalls = 0;
      campaign.updatedAt = new Date().toISOString();
      console.log(`⏸️ [Campaign Action]: Paused calling sheet.`);
    } else if (action === 'stop' || action === 'reset') {
      // Reset live data to 0 as requested
      campaign.status = 'idle';
      campaign.ongoingCalls = 0;
      campaign.completedCalls = 0;
      campaign.remainingCalls = 0;
      campaign.totalContacts = 0;
      campaign.interestedCount = 0;
      campaign.siteVisitCount = 0;
      campaign.currentBatchFile = '';
      campaign.updatedAt = new Date().toISOString();
      console.log(`⏹️ [Campaign Action]: Stopped and reset live dialer to 0.`);
    }

    saveSarvamDb(db);
    return NextResponse.json({ success: true, campaign });
  } catch (err: any) {
    console.error('Error controlling campaign:', err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
