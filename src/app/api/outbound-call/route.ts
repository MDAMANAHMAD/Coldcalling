import { NextRequest, NextResponse } from 'next/server';
import { SipClient } from 'livekit-server-sdk';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const VERIFIED_HOST = 'https://cold-calling-j7qhnkas.livekit.cloud';
const VERIFIED_KEY = 'APIAkEXqBNfS2LP';
const VERIFIED_SECRET = 'dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT';
const VERIFIED_TRUNK = 'ST_TEGVYguUkfe9';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const phoneNumber = body.phoneNumber || '+918693081506';
    const customerName = body.customerName || 'Aman';

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Date.now()}`;

    const host = VERIFIED_HOST;
    const apiKey = (process.env.LIVEKIT_API_KEY || VERIFIED_KEY).trim();
    const apiSecret = (process.env.LIVEKIT_API_SECRET || VERIFIED_SECRET).trim();
    const trunkId = (process.env.SIP_OUTBOUND_TRUNK_ID || VERIFIED_TRUNK).trim();

    console.log(`[API OUTBOUND CALL] Waiting 10 seconds before dialing ${safePhone} to allow background systems to pre-warm...`);
    await new Promise((resolve) => setTimeout(resolve, 10000));

    console.log(`[API OUTBOUND CALL] Dialing ${safePhone} to room ${uniqueRoom} on ${host}`);

    const sipClient = new SipClient(host, apiKey, apiSecret);

    const participant = await sipClient.createSipParticipant(
      trunkId.trim(),
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        playRingtone: true,
        waitUntilAnswered: true,
      }
    );

    console.log(`[API OUTBOUND CALL SUCCESS] Created participant:`, participant);

    return NextResponse.json({
      success: true,
      message: `Outbound call successfully ringing ${safePhone}!`,
      participantId: participant.participantId,
      roomName: uniqueRoom
    });
  } catch (error: any) {
    console.error(`[API OUTBOUND CALL ERROR]:`, error);
    return NextResponse.json(
      {
        success: false,
        message: error?.message || 'Failed to dispatch outbound SIP call',
        error: String(error)
      },
      { status: 500 }
    );
  }
}
