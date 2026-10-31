import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb } from '@/lib/sarvamDb';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const db = getSarvamDb();
    const campaign = db.campaigns[0] || null;
    return NextResponse.json({ campaign });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
