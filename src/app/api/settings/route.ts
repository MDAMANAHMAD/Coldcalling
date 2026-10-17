import { NextRequest, NextResponse } from 'next/server';
import { getDb, saveDb } from '@/lib/db';
import { getRoomServiceClient } from '@/lib/livekit';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET() {
  try {
    return NextResponse.json({
      success: true,
      settings: {
        voiceSpeed: 1.0,
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message, settings: { voiceSpeed: 1.0 } },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const speed = 1.0;

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
