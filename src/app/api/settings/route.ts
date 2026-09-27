import { NextRequest, NextResponse } from 'next/server';
import { getDb, saveDb } from '@/lib/db';
import { getRoomServiceClient } from '@/lib/livekit';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET() {
  try {
    const db = getDb();
    const voiceSpeed = (db as any).settings?.voiceSpeed ?? 0.94;
    return NextResponse.json({
      success: true,
      settings: {
        voiceSpeed: Number(voiceSpeed),
      },
    });
  } catch (err: any) {
    console.error('Error fetching settings:', err);
    return NextResponse.json(
      { success: false, error: err.message, settings: { voiceSpeed: 0.94 } },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    let speed = Number(body.voiceSpeed ?? body.voice_speed);

    if (isNaN(speed) || speed < 0.6 || speed > 1.6) {
      speed = 0.94;
    }
    speed = Math.round(speed * 100) / 100;

    // 1. Save to db.json
    const db = getDb();
    if (!(db as any).settings) {
      (db as any).settings = {};
    }
    (db as any).settings.voiceSpeed = speed;
    saveDb(db);

    // 2. Best-effort sync to LiveKit Cloud shared metadata
    try {
      const roomClient = getRoomServiceClient(10);
      const rooms = await roomClient.listRooms(['gayatri-persistent-storage']);
      let cloudMeta: any = {};
      if (rooms.length > 0 && rooms[0].metadata) {
        try {
          cloudMeta = JSON.parse(rooms[0].metadata);
        } catch {}
      }
      if (!cloudMeta.settings) cloudMeta.settings = {};
      cloudMeta.settings.voiceSpeed = speed;

      await roomClient.updateRoomMetadata(
        'gayatri-persistent-storage',
        JSON.stringify(cloudMeta)
      );
    } catch (lkErr) {
      console.warn('Could not sync settings to LiveKit Cloud metadata:', lkErr);
    }

    return NextResponse.json({
      success: true,
      settings: {
        voiceSpeed: speed,
      },
      message: `Gayatri voice speed set to ${speed}x`,
    });
  } catch (err: any) {
    console.error('Error saving settings:', err);
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}
