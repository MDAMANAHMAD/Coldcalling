import { NextRequest, NextResponse } from 'next/server';
import { SipClient } from 'livekit-server-sdk';
import { getDb, saveDb } from '@/lib/db';

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

    const host = process.env.LIVEKIT_URL 
      ? `https://${process.env.LIVEKIT_URL.replace(/^[a-zA-Z]+:\/\//, '').replace(/\/+$/, '').trim()}`
      : VERIFIED_HOST;
    const apiKey = (process.env.LIVEKIT_API_KEY || VERIFIED_KEY).trim();
    const apiSecret = (process.env.LIVEKIT_API_SECRET || VERIFIED_SECRET).trim();
    const trunkId = (process.env.SIP_OUTBOUND_TRUNK_ID || VERIFIED_TRUNK).trim();

    console.log(`[API OUTBOUND CALL] Dialing ${safePhone} to room ${uniqueRoom} on ${host}`);

    const sipClient = new SipClient(host, apiKey, apiSecret);

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone: safePhone,
      phone_number: safePhone,
      initiated_from: 'web_dashboard'
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
        waitUntilAnswered: false, // Non-blocking dispatch: connects in ~100ms without twirp timeout
      }
    );

    console.log(`[API OUTBOUND CALL SUCCESS] Created participant:`, participant);

    // Record call log in db.json immediately
    try {
      const db = getDb();
      const callLogId = `call-${Date.now()}`;
      db.callLogs.unshift({
        id: callLogId,
        leadId: `lead-${cleanId}`,
        callSid: uniqueRoom,
        durationSeconds: 0,
        recordingUrl: '',
        transcript: `[Call initiated from Web Dashboard]\nAgent: Gayatri connecting to ${customerName} (${safePhone})...`,
        aiSummary: `Outbound AI call initiated to ${customerName} (${safePhone}). Phone ringing.`,
        sentiment: 'neutral',
        calledAt: new Date().toISOString(),
        outcome: 'Calling...',
        customerName: customerName,
        customerPhone: safePhone,
        detectedQuestions: ['Outbound Initiation']
      });

      // Also ensure lead exists in db
      const existingLead = db.leads.find(l => l.phone.replace(/\D/g, '') === safePhone.replace(/\D/g, ''));
      if (existingLead) {
        existingLead.status = 'calling';
        existingLead.lastCallAt = new Date().toISOString();
      } else {
        db.leads.unshift({
          id: `lead-${cleanId}`,
          name: customerName,
          phone: safePhone,
          status: 'calling',
          createdAt: new Date().toISOString(),
          lastCallAt: new Date().toISOString(),
          notes: 'Dialed from Web Dashboard'
        });
      }

      saveDb(db);
    } catch (dbErr) {
      console.warn('[DB Log Warning]:', dbErr);
    }

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
