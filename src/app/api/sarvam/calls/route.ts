import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb, filterCallsByPeriod, computeAnalytics } from '@/lib/sarvamDb';
import { TimeFilterPeriod } from '@/lib/sarvamTypes';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const period = (searchParams.get('period') as TimeFilterPeriod) || 'all';
    const category = searchParams.get('category'); // 'Interested' | 'Site Visit' | undefined

    const db = getSarvamDb();
    let calls = filterCallsByPeriod(db.calls, period);

    // If caller requests only retained high-intent calls
    if (category === 'Interested') {
      calls = calls.filter(c => c.outcome === 'Interested');
    } else if (category === 'Site Visit') {
      calls = calls.filter(c => c.outcome === 'Site Visit');
    }

    const analytics = computeAnalytics(db.calls);
    const liveCampaign = db.campaigns[0] || null;

    return NextResponse.json({
      calls,
      analytics,
      liveCampaign,
      config: {
        agentId: db.config.agentId,
        fromNumber: db.config.fromNumber
      }
    });
  } catch (err: any) {
    console.error('Error fetching Sarvam calls:', err);
    return NextResponse.json({ error: err.message || 'Internal server error' }, { status: 500 });
  }
}
