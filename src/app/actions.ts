'use server';

import { getDb, saveDb } from '@/lib/db';
import { Lead, CallLog } from '@/lib/types';
import { revalidatePath } from 'next/cache';
import { getRoomServiceClient, getSipClient } from '@/lib/livekit';
import { getCallTimestampMs, getCallPickedInfo } from '@/lib/callUtils';
import fs from 'fs';
import path from 'path';

// --- LEADS ACTIONS ---
export async function getLeads(): Promise<Lead[]> {
  const db = getDb();
  return (db.leads || []).sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function saveLead(lead: Lead): Promise<Lead> {
  const db = getDb();
  if (!db.leads) db.leads = [];
  const index = db.leads.findIndex(l => l.id === lead.id);
  
  if (index >= 0) {
    db.leads[index] = lead;
  } else {
    db.leads.unshift(lead);
  }
  
  saveDb(db);
  revalidatePath('/');
  return lead;
}

export async function deleteLead(id: string): Promise<boolean> {
  const db = getDb();
  if (!db.leads) return false;
  const initialLength = db.leads.length;
  db.leads = db.leads.filter(l => l.id !== id);
  
  if (db.leads.length < initialLength) {
    saveDb(db);
    revalidatePath('/');
    return true;
  }
  return false;
}

// --- GAYATRI CALL LOGS & INTELLIGENCE ACTIONS ---

export async function getCallLogsWithLeads(): Promise<(CallLog & { leadName: string; leadPhone?: string })[]> {
  const db = getDb();
  const dbLogs = db.callLogs || [];

  // Also check if bookings/call_transcripts.jsonl or property_visits.jsonl has records
  try {
    const transcriptsPath = path.join(process.cwd(), 'bookings', 'call_transcripts.jsonl');
    if (fs.existsSync(transcriptsPath)) {
      const content = fs.readFileSync(transcriptsPath, 'utf-8');
      const lines = content.split('\n').filter(l => l.trim().length > 0);
      for (const line of lines) {
        try {
          const rec = JSON.parse(line);
          const callId = rec.call_id || `call-${rec.timestamp || Math.random()}`;
          if (!dbLogs.some(log => log.callSid === callId || log.calledAt === rec.timestamp)) {
            dbLogs.push({
              id: callId,
              leadId: `lead-${rec.customer_name?.toLowerCase().replace(/\s+/g, '') || 'client'}`,
              userEmail: rec.user_email || 'test@gmail.com',
              callSid: callId,
              durationSeconds: Math.round(rec.duration_seconds || 0),
              recordingUrl: rec.recording_url || '',
              transcript: rec.full_transcript || (rec.dialogue ? rec.dialogue.map((d: any) => `${d.role}: ${d.text}`).join('\n') : ''),
              aiSummary: rec.ai_summary || `Call with ${rec.customer_name}. Outcome: ${rec.outcome}. Questions: ${rec.detected_questions?.join(', ') || 'General'}.`,
              sentiment: rec.sentiment || (rec.outcome?.includes('Site Visit') ? 'positive' : (rec.outcome?.includes('Not Interested') ? 'negative' : (rec.outcome?.includes('Interested') ? 'positive' : 'neutral'))),
              calledAt: rec.timestamp || new Date().toISOString(),
              outcome: rec.outcome || 'Inquiry Completed',
              customerName: rec.customer_name || 'Client',
              customerPhone: rec.customer_phone || '+918693081506',
              detectedQuestions: rec.detected_questions || []
            });
          }
        } catch {
          // ignore malformed line
        }
      }
    }
  } catch (err) {
    console.warn('Error augmenting call logs from disk:', err);
  }

  // Also query LiveKit Cloud room metadata gayatri-persistent-storage
  try {
    const roomClient = getRoomServiceClient(30);
    const rooms = await roomClient.listRooms(['gayatri-persistent-storage']);
    if (rooms.length > 0 && rooms[0].metadata) {
      const parsed = JSON.parse(rooms[0].metadata);
      if (Array.isArray(parsed.callLogs)) {
        for (const cloudLog of parsed.callLogs) {
          if (cloudLog.callSid === 'gayatri-persistent-storage') continue;
          const key = cloudLog.callSid || cloudLog.id;
          const exIdx = dbLogs.findIndex(l => (l.callSid || l.id) === key);
          if (exIdx >= 0) {
            dbLogs[exIdx] = { ...dbLogs[exIdx], ...cloudLog };
          } else {
            dbLogs.push(cloudLog);
          }
        }
      }
    }
  } catch (lkErr) {
    console.warn('Error reading from LiveKit Cloud persistent metadata:', lkErr);
  }

  return dbLogs.map(log => {
    const lead = (db.leads || []).find(l => l.id === log.leadId);
    const pickedInfo = getCallPickedInfo(log);
    let outcome = log.outcome || 'Inquiry Completed';
    if (pickedInfo.status === 'not_picked' && (outcome === 'Calling...' || outcome === 'Ringing / Calling')) {
      outcome = 'Not Picked Up';
    }
    return {
      ...log,
      outcome,
      callPicked: pickedInfo.isPicked,
      callPickedStatus: pickedInfo.status,
      userEmail: log.userEmail || 'test@gmail.com',
      leadName: log.customerName || (lead ? lead.name : 'Valued Customer'),
      leadPhone: log.customerPhone || lead?.phone || '',
    };
  }).sort((a, b) => getCallTimestampMs(b) - getCallTimestampMs(a));
}

export async function deleteCallLog(id: string): Promise<boolean> {
  const db = getDb();
  if (!db.callLogs) return false;
  const initialLength = db.callLogs.length;
  db.callLogs = db.callLogs.filter(c => c.id !== id);
  if (db.callLogs.length < initialLength) {
    saveDb(db);
    revalidatePath('/');
    return true;
  }
  return false;
}

export async function getColdCallingStats() {
  const db = getDb();
  const callLogs = db.callLogs || [];
  const totalCalls = callLogs.length;

  const siteVisits = callLogs.filter(c => 
    (c.outcome && c.outcome.toLowerCase().includes('site visit')) ||
    (c.aiSummary && c.aiSummary.toLowerCase().includes('site visit'))
  ).length;

  const interested = callLogs.filter(c => 
    (c.outcome && c.outcome.toLowerCase().includes('interested') && !c.outcome.toLowerCase().includes('not interested')) ||
    c.sentiment === 'positive'
  ).length;

  const notInterested = callLogs.filter(c => 
    (c.outcome && c.outcome.toLowerCase().includes('not interested')) ||
    c.sentiment === 'negative'
  ).length;

  return {
    totalCalls,
    siteVisits,
    interested,
    notInterested
  };
}

const VERIFIED_HOST = 'https://cold-calling-j7qhnkas.livekit.cloud';
// --- DIRECT OUTBOUND CALL ACTION (NON-BLOCKING) ---
export async function triggerLiveKitOutboundCall(phoneNumber: string, customerName: string): Promise<{ success: boolean; message: string; roomName?: string; error?: string }> {
  try {
    const { client: sipClient, trunkId } = getSipClient();

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Date.now()}`;

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone_number: safePhone,
      phone: safePhone
    });

    console.log(`[LIVEKIT OUTBOUND CALL]: Dialing ${safePhone} in room ${uniqueRoom} with Trunk ${trunkId}`);

    await sipClient.createSipParticipant(
      trunkId,
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        participantMetadata: metadata,
        playRingtone: true,
        hidePhoneNumber: false,
        waitUntilAnswered: false, // Non-blocking dispatch
      }
    );

    // Save instant call record to DB
    const db = getDb();
    if (!db.callLogs) db.callLogs = [];
    db.callLogs.unshift({
      id: `call-${Date.now()}`,
      leadId: `lead-${cleanId}`,
      callSid: uniqueRoom,
      durationSeconds: 0,
      transcript: `Agent (Gayatri): Connecting to ${customerName} (${safePhone})...`,
      aiSummary: `Outbound AI call placed to ${customerName} (${safePhone}). Gayatri is dialing now.`,
      sentiment: 'neutral',
      calledAt: new Date().toISOString(),
      outcome: 'Calling...',
      customerName,
      customerPhone: safePhone,
      detectedQuestions: ['Outbound Call']
    });
    saveDb(db);
    revalidatePath('/');

    return {
      success: true,
      message: `Call dispatched to ${safePhone}! Phone is ringing now.`,
      roomName: uniqueRoom
    };
  } catch (error: any) {
    console.error(`[LIVEKIT OUTBOUND ERROR]:`, error);
    return {
      success: false,
      message: error?.message || 'Failed to dispatch outbound SIP call via LiveKit.',
      error: String(error)
    };
  }
}
