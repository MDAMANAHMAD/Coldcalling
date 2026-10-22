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

// --- In-memory cache for LiveKit Cloud & disk transcripts ---
let cachedCloudLogs: any[] = [];
let lastCloudFetchTime = 0;
const CLOUD_CACHE_TTL = 10000; // 10 seconds

let cachedJsonlRecords: any[] = [];
let lastTranscriptsMtime = 0;
// --- GAYATRI CALL LOGS & INTELLIGENCE ACTIONS ---

export async function getCallLogsWithLeads(): Promise<(CallLog & { leadName: string; leadPhone?: string })[]> {
  const db = getDb();
  const dbLogs = db.callLogs || [];

  // Fast cached reading of bookings/call_transcripts.jsonl based on file mtime
  try {
    const transcriptsPath = path.join(process.cwd(), 'bookings', 'call_transcripts.jsonl');
    if (fs.existsSync(transcriptsPath)) {
      const stat = fs.statSync(transcriptsPath);
      if (stat.mtimeMs !== lastTranscriptsMtime) {
        lastTranscriptsMtime = stat.mtimeMs;
        const content = fs.readFileSync(transcriptsPath, 'utf-8');
        const lines = content.split('\n').filter(l => l.trim().length > 0);
        cachedJsonlRecords = [];
        for (const line of lines) {
          try {
            cachedJsonlRecords.push(JSON.parse(line));
          } catch {}
        }
      }

      for (const rec of cachedJsonlRecords) {
        const callId = rec.call_id || rec.room_name || `call-${rec.timestamp || Math.random()}`;
        const transcriptText = rec.full_transcript || (rec.dialogue ? rec.dialogue.map((d: any) => `${d.role}: ${d.text}`).join('\n') : '');
        const existingIdx = dbLogs.findIndex(log => log.callSid === callId || log.id === callId || log.calledAt === rec.timestamp);

        if (existingIdx >= 0) {
          if (transcriptText && transcriptText.length > (dbLogs[existingIdx].transcript || '').length) {
            dbLogs[existingIdx].transcript = transcriptText;
          }
          if (rec.duration_seconds && rec.duration_seconds > (dbLogs[existingIdx].durationSeconds || 0)) {
            dbLogs[existingIdx].durationSeconds = Math.round(rec.duration_seconds);
          }
          if (rec.recording_url && !dbLogs[existingIdx].recordingUrl) {
            dbLogs[existingIdx].recordingUrl = rec.recording_url;
          }
          if (rec.outcome && (!dbLogs[existingIdx].outcome || dbLogs[existingIdx].outcome.includes('Calling'))) {
            dbLogs[existingIdx].outcome = rec.outcome;
          }
          if (rec.ai_summary && (!dbLogs[existingIdx].aiSummary || dbLogs[existingIdx].aiSummary.includes('ringing'))) {
            dbLogs[existingIdx].aiSummary = rec.ai_summary;
          }
        } else {
          dbLogs.push({
            id: callId,
            leadId: `lead-${rec.customer_name?.toLowerCase().replace(/\s+/g, '') || 'client'}`,
            userEmail: rec.user_email || 'test@gmail.com',
            callSid: callId,
            durationSeconds: Math.round(rec.duration_seconds || 0),
            recordingUrl: rec.recording_url || '',
            transcript: transcriptText,
            aiSummary: rec.ai_summary || `Call with ${rec.customer_name}. Outcome: ${rec.outcome}. Questions: ${rec.detected_questions?.join(', ') || 'General'}.`,
            sentiment: rec.sentiment || (rec.outcome?.includes('Site Visit') ? 'positive' : (rec.outcome?.includes('Not Interested') ? 'negative' : (rec.outcome?.includes('Interested') ? 'positive' : 'neutral'))),
            calledAt: rec.timestamp || new Date().toISOString(),
            outcome: rec.outcome || 'Inquiry Completed',
            customerName: rec.customer_name || 'Client',
            customerPhone: rec.customer_phone || '+918693081506',
            detectedQuestions: rec.detected_questions || []
          });
        }
      }
    }
  } catch (err) {
    console.warn('Error augmenting call logs from disk:', err);
  }

  // Cached query of LiveKit Cloud room metadata gayatri-persistent-storage (10s TTL)
  try {
    const now = Date.now();
    if (now - lastCloudFetchTime > CLOUD_CACHE_TTL) {
      const roomClient = getRoomServiceClient(5);
      const lkPromise = roomClient.listRooms(['gayatri-persistent-storage']);
      const timeoutPromise = new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error('LiveKit Cloud read timeout')), 2500)
      );
      const rooms: any = await Promise.race([lkPromise, timeoutPromise]);
      if (rooms.length > 0 && rooms[0].metadata) {
        const parsed = JSON.parse(rooms[0].metadata);
        if (Array.isArray(parsed.callLogs)) {
          cachedCloudLogs = parsed.callLogs;
          lastCloudFetchTime = now;
        }
      }
    }
    for (const cloudLog of cachedCloudLogs) {
      if (cloudLog.callSid === 'gayatri-persistent-storage') continue;
      const key = cloudLog.callSid || cloudLog.id;
      const exIdx = dbLogs.findIndex(l => (l.callSid || l.id) === key);
      if (exIdx >= 0) {
        dbLogs[exIdx] = { ...dbLogs[exIdx], ...cloudLog };
      } else {
        dbLogs.push(cloudLog);
      }
    }
  } catch (lkErr) {
    console.warn('Error reading from LiveKit Cloud persistent metadata (using cache):', lkErr);
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
  let changed = false;

  // 1. Delete from local db.json
  if (db.callLogs) {
    const initialLength = db.callLogs.length;
    db.callLogs = db.callLogs.filter(c => c.id !== id && c.callSid !== id);
    if (db.callLogs.length < initialLength) {
      saveDb(db);
      changed = true;
    }
  }

  // 2. Also delete from LiveKit Cloud metadata (gayatri-persistent-storage)
  try {
    const { getRoomServiceClient } = await import('@/lib/livekit');
    const roomClient = getRoomServiceClient(30);
    const rooms = await roomClient.listRooms(['gayatri-persistent-storage']);
    if (rooms.length > 0 && rooms[0].metadata) {
      const parsed = JSON.parse(rooms[0].metadata);
      if (Array.isArray(parsed.callLogs)) {
        const origLen = parsed.callLogs.length;
        parsed.callLogs = parsed.callLogs.filter((c: any) => c.id !== id && c.callSid !== id);
        if (parsed.callLogs.length < origLen) {
          await roomClient.updateRoomMetadata('gayatri-persistent-storage', JSON.stringify(parsed));
          changed = true;
        }
      }
    }
  } catch (lkErr) {
    console.warn('[deleteCallLog LiveKit Cloud Sync Warning]:', lkErr);
  }

  try {
    revalidatePath('/');
  } catch {}
  return true;
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
      phone: safePhone,
      voice_speed: 1.05
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
