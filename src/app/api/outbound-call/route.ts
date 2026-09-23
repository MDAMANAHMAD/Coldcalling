import { NextRequest, NextResponse } from 'next/server';
import { SipClient, RoomServiceClient } from 'livekit-server-sdk';
import { getDb, saveDb } from '@/lib/db';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const VERIFIED_HOST = 'https://cold-calling-j7qhnkas.livekit.cloud';
const VERIFIED_KEY = 'APIAkEXqBNfS2LP';
const VERIFIED_SECRET = 'dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT';
const VERIFIED_TRUNK = 'ST_TEGVYguUkfe9';

// ── Concurrency guard: max 4 simultaneous outbound calls (~1.2-1.4 GB RAM each on 8 GB VPS) ──
let activeOutboundCalls = 0;
const MAX_CONCURRENT_CALLS = 4;

function getCleanLiveKitUrl(): string {
  const raw = (process.env.LIVEKIT_URL || VERIFIED_HOST)
    .replace(/['\"]/g, '')
    .trim();
  try {
    const parsed = new URL(raw.includes('://') ? raw : `https://${raw}`);
    return `https://${parsed.host}`;
  } catch {
    return VERIFIED_HOST;
  }
}

export async function POST(req: NextRequest) {
  // ── Concurrency check ──
  if (activeOutboundCalls >= MAX_CONCURRENT_CALLS) {
    return NextResponse.json(
      {
        success: false,
        message: `Server is busy: ${activeOutboundCalls}/${MAX_CONCURRENT_CALLS} calls are already active. Please wait for a call to complete before dialing more.`,
        activeCount: activeOutboundCalls
      },
      { status: 429 }
    );
  }

  activeOutboundCalls++;
  console.log(`[CONCURRENCY] Slot acquired. Active outbound calls: ${activeOutboundCalls}/${MAX_CONCURRENT_CALLS}`);

  try {
    const body = await req.json();
    const phoneNumber = body.phoneNumber || '+918693081506';
    const customerName = body.customerName || 'Aman';
    const userEmail = (body.userEmail || 'test@gmail.com').trim().toLowerCase();

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Date.now()}`;

    const host = getCleanLiveKitUrl();
    const apiKey = (process.env.LIVEKIT_API_KEY || VERIFIED_KEY).replace(/['\"]/g, '').trim();
    const apiSecret = (process.env.LIVEKIT_API_SECRET || VERIFIED_SECRET).replace(/['\"]/g, '').trim();
    const trunkId = (process.env.SIP_OUTBOUND_TRUNK_ID || VERIFIED_TRUNK).replace(/['\"]/g, '').trim();

    console.log(`[API OUTBOUND CALL] Dialing ${safePhone} to room ${uniqueRoom} on ${host} for user: ${userEmail}`);

    const sipClient = new SipClient(host, apiKey, apiSecret);

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone: safePhone,
      phone_number: safePhone,
      user_email: userEmail,
      initiated_from: 'web_dashboard'
    });

    const participant = await sipClient.createSipParticipant(
      trunkId,
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        participantMetadata: metadata,
        playRingtone: true,
        waitUntilAnswered: false, // Non-blocking dispatch
      }
    );

    console.log(`[API OUTBOUND CALL SUCCESS] Created participant:`, participant);

    // Release the concurrency slot after 5 minutes (covers max ring time + typical call duration)
    setTimeout(() => {
      activeOutboundCalls = Math.max(0, activeOutboundCalls - 1);
      console.log(`[CONCURRENCY] Slot released (5-min timeout). Active: ${activeOutboundCalls}/${MAX_CONCURRENT_CALLS}`);
    }, 300000);

    // Record call log in db.json immediately
    try {
      const db = getDb();
      const callLogId = `call-${Date.now()}`;
      if (!db.callLogs) db.callLogs = [];
      db.callLogs.unshift({
        id: callLogId,
        leadId: `lead-${cleanId}`,
        callSid: uniqueRoom,
        userEmail: userEmail,
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
      if (!db.leads) db.leads = [];
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

      // Sync newly placed call to LiveKit Cloud 'gayatri-persistent-storage' room metadata
      // so it shows up IMMEDIATELY across all connected devices (mobile, laptop, tablet)
      try {
        const roomClient = new RoomServiceClient(host, apiKey, apiSecret);
        const rooms = await roomClient.listRooms(['gayatri-persistent-storage']);
        let cloudMeta: any = {};
        if (rooms.length > 0 && rooms[0].metadata) {
          try { cloudMeta = JSON.parse(rooms[0].metadata); } catch {}
        } else {
          await roomClient.createRoom({
            name: 'gayatri-persistent-storage',
            emptyTimeout: 86400 * 30,
          });
        }
        if (!cloudMeta.callLogs) cloudMeta.callLogs = [];
        const newLiveLog = {
          id: callLogId,
          leadId: `lead-${cleanId}`,
          callSid: uniqueRoom,
          userEmail: userEmail,
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
        };
        cloudMeta.callLogs = [newLiveLog, ...cloudMeta.callLogs.filter((l: any) => l.callSid !== uniqueRoom && l.callSid !== 'gayatri-persistent-storage')].slice(0, 30);
        await roomClient.updateRoomMetadata('gayatri-persistent-storage', JSON.stringify(cloudMeta));
        console.log(`[API OUTBOUND CALL] Synced call ${uniqueRoom} to gayatri-persistent-storage across all devices.`);
      } catch (cloudErr) {
        console.warn('[API Outbound LiveKit Cloud Sync Warning]:', cloudErr);
      }
    } catch (dbErr) {
      console.warn('[DB Log Warning]:', dbErr);
    }

    return NextResponse.json({
      success: true,
      message: `Outbound call successfully ringing ${safePhone}!`,
      participantId: participant.participantId,
      roomName: uniqueRoom,
      activeCount: activeOutboundCalls
    });
  } catch (error: any) {
    // Release slot on failure
    activeOutboundCalls = Math.max(0, activeOutboundCalls - 1);
    console.log(`[CONCURRENCY] Slot released (error). Active: ${activeOutboundCalls}/${MAX_CONCURRENT_CALLS}`);
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
