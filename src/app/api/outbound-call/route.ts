import { NextRequest, NextResponse } from 'next/server';
import { getRoomServiceClient, getSipClient } from '@/lib/livekit';
import { getDb, saveDb } from '@/lib/db';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const phoneNumber = body.phoneNumber || '+918693081506';
    const customerName = body.customerName || 'Aman';
    const userEmail = (body.userEmail || 'test@gmail.com').trim().toLowerCase();
    const voiceSpeed = Number(body.voiceSpeed ?? body.voice_speed) || 1.05;

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Date.now()}`;

    const { client: sipClient, trunkId } = getSipClient();

    console.log(`[API OUTBOUND CALL] Instant dial ${safePhone} -> room ${uniqueRoom} (trunk: ${trunkId}, user: ${userEmail})`);

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone: safePhone,
      phone_number: safePhone,
      user_email: userEmail,
      initiated_from: 'web_dashboard',
      voice_speed: voiceSpeed,
    });

    // ── Instant Non-Blocking Outbound SIP Dispatch (<80ms) ──
    const participant = await sipClient.createSipParticipant(
      trunkId,
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        participantMetadata: metadata,
        playRingtone: true,
        waitUntilAnswered: false, // Instant dispatch
      }
    );

    console.log(`[API OUTBOUND CALL SUCCESS] Created participant:`, participant);

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

      // Non-blocking fire-and-forget sync to LiveKit Cloud 'gayatri-persistent-storage'
      (async () => {
        try {
          const roomClient = getRoomServiceClient(10);
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
          console.log(`[API OUTBOUND CALL] Background synced call ${uniqueRoom} to gayatri-persistent-storage.`);
        } catch (cloudErr) {
          console.warn('[API Outbound LiveKit Cloud Sync Warning]:', cloudErr);
        }
      })().catch(err => console.warn('[API Outbound Background Sync Error]:', err));
    } catch (dbErr) {
      console.warn('[DB Log Warning]:', dbErr);
    }

    return NextResponse.json(
      {
        success: true,
        message: `Outbound call successfully ringing ${safePhone}!`,
        participantId: participant.participantId,
        roomName: uniqueRoom,
      },
      {
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
          'Pragma': 'no-cache',
          'Expires': '0'
        }
      }
    );
  } catch (error: any) {
    console.error(`[API OUTBOUND CALL ERROR]:`, error);
    return NextResponse.json(
      {
        success: false,
        message: error?.message || 'Failed to dispatch outbound SIP call',
        error: String(error)
      },
      {
        status: 500,
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate',
        }
      }
    );
  }
}
