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
    const company = body.company || 'Client';

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Math.random().toString(36).substring(2, 10)}`;

    const host = process.env.LIVEKIT_URL ? 
      (process.env.LIVEKIT_URL.startsWith('http') ? process.env.LIVEKIT_URL : `https://${process.env.LIVEKIT_URL.replace(/^[a-zA-Z]+:\/\//, '')}`)
      : VERIFIED_HOST;

    const apiKey = process.env.LIVEKIT_API_KEY || VERIFIED_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET || VERIFIED_SECRET;
    const trunkId = process.env.SIP_OUTBOUND_TRUNK_ID || VERIFIED_TRUNK;

    console.log(`[API OUTBOUND CALL] Dialing ${safePhone} to room ${uniqueRoom} on ${host}`);

    const sipClient = new SipClient(host.trim(), apiKey.trim(), apiSecret.trim());

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone_number: safePhone,
      company: company
    });

    const participant = await sipClient.createSipParticipant(
      trunkId.trim(),
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        participantMetadata: metadata,
        playRingtone: true,
        hidePhoneNumber: false,
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
