import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb } from '@/lib/sarvamDb';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const db = getSarvamDb();
    const campaign = db.campaigns[0] || null;
    if (campaign?.settings) {
      if (!campaign.settings.agentVersion || Number(campaign.settings.agentVersion) < 26) {
        campaign.settings.agentVersion = 27;
      }
    }
    return NextResponse.json({ campaign, config: db.config });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
