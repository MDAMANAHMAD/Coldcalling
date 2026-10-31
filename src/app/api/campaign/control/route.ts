import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb } from '@/lib/sarvamDb';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const { action, batchFileName, totalContacts } = await req.json();
    const db = getSarvamDb();

    if (!db.campaigns || db.campaigns.length === 0) {
      db.campaigns = [{
        campaignId: `camp-${Date.now()}`,
        campaignName: 'Sai Garden 1 & 2 BHK Calling Sheet',
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
        currentBatchFile: batchFileName || ''
      }];
    }

    const campaign = db.campaigns[0];

    if (action === 'start') {
      campaign.status = 'running';
      if (totalContacts !== undefined && totalContacts > 0) {
        campaign.totalContacts = totalContacts;
        campaign.remainingCalls = totalContacts - campaign.completedCalls;
      }
      if (batchFileName) {
        campaign.currentBatchFile = batchFileName;
      }
      campaign.ongoingCalls = 1;
      campaign.updatedAt = new Date().toISOString();
      console.log(`▶️ [Campaign Action]: Started calling sheet '${campaign.currentBatchFile}' (${campaign.totalContacts} contacts)`);
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
    } else if (action === 'reset') {
      campaign.status = 'idle';
      campaign.completedCalls = 0;
      campaign.remainingCalls = campaign.totalContacts;
      campaign.ongoingCalls = 0;
      campaign.interestedCount = 0;
      campaign.siteVisitCount = 0;
      campaign.updatedAt = new Date().toISOString();
      console.log(`🔄 [Campaign Action]: Reset calling sheet.`);
    }

    saveSarvamDb(db);
    return NextResponse.json({ success: true, campaign });
  } catch (err: any) {
    console.error('Error controlling campaign:', err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
