import { NextRequest, NextResponse } from 'next/server';
import { RoomServiceClient } from 'livekit-server-sdk';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const VERIFIED_HOST = 'https://cold-calling-j7qhnkas.livekit.cloud';
const VERIFIED_KEY = 'APIAkEXqBNfS2LP';
const VERIFIED_SECRET = 'dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT';

function getCleanLiveKitUrl(): string {
  const raw = (process.env.LIVEKIT_URL || VERIFIED_HOST)
    .replace(/['"]/g, '')
    .trim();
  try {
    const parsed = new URL(raw.includes('://') ? raw : `https://${raw}`);
    return `https://${parsed.host}`;
  } catch {
    return VERIFIED_HOST;
  }
}

export async function POST(req: NextRequest) {
  try {
    const host = getCleanLiveKitUrl();
    const apiKey = (process.env.LIVEKIT_API_KEY || VERIFIED_KEY).replace(/['"]/g, '').trim();
    const apiSecret = (process.env.LIVEKIT_API_SECRET || VERIFIED_SECRET).replace(/['"]/g, '').trim();

    console.log(`[API TERMINATE ALL CALLS] Connecting to LiveKit at ${host}...`);
    const roomService = new RoomServiceClient(host, apiKey, apiSecret);

    const rooms = await roomService.listRooms();
    console.log(`[API TERMINATE ALL CALLS] Found ${rooms.length} active room(s).`);

    let terminatedCount = 0;
    const terminatedRooms: string[] = [];

    for (const room of rooms) {
      try {
        console.log(`[API TERMINATE ALL CALLS] Deleting room: ${room.name}...`);
        await roomService.deleteRoom(room.name);
        terminatedCount++;
        terminatedRooms.push(room.name);
      } catch (err) {
        console.error(`[API TERMINATE ALL CALLS] Error deleting room ${room.name}:`, err);
      }
    }

    // Clean up active call lock if on same machine
    try {
      const lockPath = path.join(process.cwd(), 'bookings', 'active_call.lock');
      if (fs.existsSync(lockPath)) {
        fs.unlinkSync(lockPath);
        console.log(`[API TERMINATE ALL CALLS] Removed active_call.lock`);
      }
    } catch (lockErr) {
      console.warn(`[API TERMINATE ALL CALLS] Could not clean lock:`, lockErr);
    }

    return NextResponse.json({
      success: true,
      count: terminatedCount,
      rooms: terminatedRooms,
      message: terminatedCount > 0 
        ? `Successfully terminated ${terminatedCount} active call(s).`
        : 'No active calls currently in progress.'
    });
  } catch (error: any) {
    console.error('[API TERMINATE ALL CALLS ERROR]:', error);
    return NextResponse.json({
      success: false,
      error: error.message || 'Failed to terminate active calls'
    }, { status: 500 });
  }
}
