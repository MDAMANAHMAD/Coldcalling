import { NextRequest, NextResponse } from 'next/server';
import { getDb, saveDb } from '@/lib/db';
import { Lead, CallLog, Meeting } from '@/lib/types';
import { revalidatePath } from 'next/cache';

// Helper to sanitize phone numbers for lookup
function cleanPhone(num: string): string {
  return num.replace(/\D/g, '');
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    console.log('[Webhook Received Payload]:', JSON.stringify(body, null, 2));

    // Normalize variables from Vapi/Retell format OR direct Simulator format
    let phone = '';
    let customerName = 'Valued Customer';
    let callSid = `call_sid_${Math.random().toString(36).substr(2, 9)}`;
    let durationSeconds = 0;
    let recordingUrl = '';
    let transcript = '';
    let aiSummary = '';
    let sentiment: 'positive' | 'neutral' | 'negative' = 'neutral';
    let isMeetingScheduled = false;
    let outcome = 'Inquiry Completed';
    let detectedQuestions: string[] = [];

    // 1. Detect Native LiveKit Gayatri Voice Agent Format
    if (body.customerPhone || body.customerName || body.transcript || body.room_name) {
      phone = body.customerPhone || body.phone || '+918693081506';
      customerName = body.customerName || 'Valued Customer';
      callSid = body.callSid || body.room_name || `call-${Date.now()}`;
      durationSeconds = body.durationSeconds || body.duration_seconds || 0;
      transcript = body.transcript || '';
      aiSummary = body.aiSummary || body.ai_summary || `Voice call with ${customerName}.`;
      sentiment = body.sentiment || 'neutral';
      outcome = body.outcome || 'Inquiry Completed';
      detectedQuestions = body.detectedQuestions || body.detected_questions || [];
      isMeetingScheduled = outcome.toLowerCase().includes('site visit') || body.status === 'meeting_scheduled';
    }
    // 2. Detect Vapi.ai Structure
    else if (body.message?.type === 'end-of-call-report' || body.message?.call) {
      const callData = body.message.call;
      phone = callData.customer?.number || '';
      customerName = callData.customer?.name || customerName;
      callSid = callData.id || callSid;
      durationSeconds = Math.round(callData.duration || 0);
      recordingUrl = callData.recordingUrl || '';
      transcript = callData.transcript || '';
      aiSummary = callData.summary || '';
      
      const analysis = callData.analysis || {};
      const sentimentVal = (analysis.sentiment || '').toLowerCase();
      if (sentimentVal.includes('positive') || sentimentVal.includes('interested')) {
        sentiment = 'positive';
        outcome = 'Interested';
      } else if (sentimentVal.includes('negative') || sentimentVal.includes('not interested')) {
        sentiment = 'negative';
        outcome = 'Not Interested';
      }
      
      const structuredData = analysis.structuredData || {};
      isMeetingScheduled = !!structuredData.meetingScheduled || !!structuredData.bookMeeting;
      if (isMeetingScheduled) outcome = 'Site Visit Scheduled';
    } 
    // 3. Detect Retell AI Structure
    else if (body.call_type === 'outbound_phone' || body.call_detail) {
      const detail = body.call_detail || body;
      phone = detail.customer_phone_number || '';
      customerName = detail.customer_name || customerName;
      callSid = detail.call_id || callSid;
      durationSeconds = Math.round(detail.duration_ms / 1000 || 0);
      recordingUrl = detail.recording_url || '';
      transcript = detail.transcript || '';
      aiSummary = detail.call_summary || '';
      
      const analysis = detail.analysis || {};
      const sentimentVal = (analysis.user_sentiment || '').toLowerCase();
      if (sentimentVal.includes('positive')) {
        sentiment = 'positive';
        outcome = 'Interested';
      } else if (sentimentVal.includes('negative')) {
        sentiment = 'negative';
        outcome = 'Not Interested';
      }
      
      isMeetingScheduled = !!analysis.book_meeting || !!analysis.meeting_scheduled;
      if (isMeetingScheduled) outcome = 'Site Visit Scheduled';
    } 
    // 4. Fallback: Direct Sandbox / Generic Format
    else {
      phone = body.phone || '+918693081506';
      customerName = body.name || customerName;
      callSid = body.callSid || callSid;
      durationSeconds = body.durationSeconds || 60;
      recordingUrl = body.recordingUrl || '';
      transcript = body.transcript || 'Mock conversation transcript';
      aiSummary = body.aiSummary || 'Outbound call completed.';
      sentiment = body.sentiment || 'neutral';
      outcome = body.outcome || 'Inquiry Completed';
      isMeetingScheduled = body.status === 'meeting_scheduled' || outcome.includes('Site Visit');
    }

    if (!phone) {
      phone = '+918693081506';
    }

    // Lookup or Create Lead in DB
    const db = getDb();
    if (!db.leads) db.leads = [];
    if (!db.callLogs) db.callLogs = [];
    if (!db.meetings) db.meetings = [];

    const cleanTargetPhone = cleanPhone(phone);
    let leadIndex = db.leads.findIndex(l => cleanPhone(l.phone) === cleanTargetPhone);
    
    let finalLeadStatus: Lead['status'] = 'queued';
    if (isMeetingScheduled || outcome.toLowerCase().includes('site visit') || sentiment === 'positive') {
      finalLeadStatus = isMeetingScheduled || outcome.toLowerCase().includes('site visit') ? 'meeting_scheduled' : 'interested';
    } else if (sentiment === 'negative' || outcome.toLowerCase().includes('not interested')) {
      finalLeadStatus = 'not_interested';
    } else {
      finalLeadStatus = 'callback_required';
    }

    let lead: Lead;
    if (leadIndex === -1) {
      console.log(`[Webhook]: Auto-creating new lead for phone: ${phone} (${customerName})`);
      lead = {
        id: `lead-${cleanTargetPhone || Date.now()}`,
        name: customerName,
        phone: phone,
        status: finalLeadStatus,
        createdAt: new Date().toISOString(),
        lastCallAt: new Date().toISOString(),
        notes: `Registered via Gayatri Voice Call: ${aiSummary}`
      };
      db.leads.unshift(lead);
    } else {
      lead = db.leads[leadIndex];
      db.leads[leadIndex] = {
        ...lead,
        name: customerName !== 'Valued Customer' ? customerName : lead.name,
        status: finalLeadStatus,
        lastCallAt: new Date().toISOString(),
        notes: `${lead.notes || ''}\n\n[Gayatri Voice Call - ${new Date().toLocaleDateString()}]: ${aiSummary}`
      };
    }

    const userEmail = (body.userEmail || body.user_email || 'test@gmail.com').trim().toLowerCase();

    // Log the Call Details
    const newCallLog: CallLog = {
      id: `call-${Date.now()}`,
      leadId: lead.id,
      callSid,
      userEmail,
      durationSeconds,
      recordingUrl,
      transcript,
      aiSummary,
      sentiment,
      calledAt: body.called_at || new Date().toISOString(),
      outcome,
      customerName,
      customerPhone: phone,
      detectedQuestions
    };

    // Update existing log if matching callSid, or prepend
    const existingLogIdx = db.callLogs.findIndex(l => l.callSid === callSid);
    if (existingLogIdx >= 0) {
      db.callLogs[existingLogIdx] = {
        ...db.callLogs[existingLogIdx],
        ...newCallLog
      };
    } else {
      db.callLogs.unshift(newCallLog);
    }

    // Save DB
    saveDb(db);
    revalidatePath('/');

    return NextResponse.json({
      success: true,
      message: 'Call log and intelligence successfully filed!',
      callLogId: newCallLog.id,
      outcome,
      customerName,
      leadStatus: finalLeadStatus
    });

  } catch (e: any) {
    console.error('[Webhook Critical Error]:', e);
    return NextResponse.json({ success: false, error: e.message || 'Server error' }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const db = getDb();
    const logs = (db.callLogs || []).map(log => {
      const lead = (db.leads || []).find(l => l.id === log.leadId);
      return {
        ...log,
        userEmail: log.userEmail || 'test@gmail.com',
        leadName: log.customerName || (lead ? lead.name : 'Valued Customer'),
        leadPhone: log.customerPhone || lead?.phone || '',
      };
    });
    return NextResponse.json({
      success: true,
      callLogs: logs,
      leads: db.leads || []
    });
  } catch (e: any) {
    return NextResponse.json({ success: false, error: e.message }, { status: 500 });
  }
}
