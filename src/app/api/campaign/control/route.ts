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
      campaign.status = 'running';
      if (settings?.campaignName) {
        campaign.campaignName = settings.campaignName;
      }
      if (settings) {
        campaign.settings = settings;
      }
      if (totalContacts !== undefined && totalContacts > 0) {
        campaign.totalContacts = totalContacts;
        campaign.remainingCalls = totalContacts - campaign.completedCalls;
      }
      if (batchFileName) {
        campaign.currentBatchFile = batchFileName;
      }
      campaign.ongoingCalls = 1;
      campaign.updatedAt = new Date().toISOString();

      // If contact numbers were passed from the verified CSV upload, trigger pacing dispatch
      if (Array.isArray(contacts) && contacts.length > 0) {
        const cps = settings?.attemptsPerSecond || 0.5;
        const delayBetweenCallsMs = Math.max(500, Math.round(1000 / cps));
        console.log(`🚀 [Campaign Trigger]: Triggering live outbound calls for ${contacts.length} numbers at ${cps} CPS (${delayBetweenCallsMs}ms delay)...`);
        
        (async () => {
          for (const c of contacts) {
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

            // Pacing delay based on attempts_per_second configuration
            await new Promise(r => setTimeout(r, delayBetweenCallsMs));
          }
        })().catch(err => console.error('Background batch dialer error:', err));
      }
    } else if (action === 'pause') {
      campaign.status = 'paused';
      campaign.ongoingCalls = 0;
      campaign.updatedAt = new Date().toISOString();
      console.log(`⏸️ [Campaign Action]: Paused calling sheet.`);
    } else if (action === 'stop') {
      campaign.status = 'completed';
      campaign.ongoingCalls = 0;
      campaign.updatedAt = new Date().toISOString();
      console.log(`⏹️ [Campaign Action]: Stopped calling sheet.`);
    }

    saveSarvamDb(db);
    return NextResponse.json({ success: true, campaign });
  } catch (err: any) {
    console.error('Error controlling campaign:', err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
