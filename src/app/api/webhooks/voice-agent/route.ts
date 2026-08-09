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
    let callSid = `call_sid_${Math.random().toString(36).substr(2, 9)}`;
    let durationSeconds = 0;
    let recordingUrl = '';
    let transcript = '';
    let aiSummary = '';
    let sentiment: 'positive' | 'neutral' | 'negative' = 'neutral';
    let isMeetingScheduled = false;
    let meetingTimeStr = '';

    // 1. Detect Vapi.ai Structure
    if (body.message?.type === 'end-of-call-report' || body.message?.call) {
      const callData = body.message.call;
      phone = callData.customer?.number || '';
      callSid = callData.id || callSid;
      durationSeconds = Math.round(callData.duration || 0);
      recordingUrl = callData.recordingUrl || '';
      transcript = callData.transcript || '';
      aiSummary = callData.summary || '';
      
      const analysis = callData.analysis || {};
      const sentimentVal = (analysis.sentiment || '').toLowerCase();
      if (sentimentVal.includes('positive') || sentimentVal.includes('interested')) {
        sentiment = 'positive';
      } else if (sentimentVal.includes('negative') || sentimentVal.includes('not interested')) {
        sentiment = 'negative';
      }
      
      // Look for structured calendar data from agent analysis
      const structuredData = analysis.structuredData || {};
      isMeetingScheduled = !!structuredData.meetingScheduled || !!structuredData.bookMeeting;
      meetingTimeStr = structuredData.meetingTime || structuredData.scheduledTime || '';
    } 
    // 2. Detect Retell AI Structure
    else if (body.call_type === 'outbound_phone' || body.call_detail) {
      const detail = body.call_detail || body;
      phone = detail.customer_phone_number || '';
      callSid = detail.call_id || callSid;
      durationSeconds = Math.round(detail.duration_ms / 1000 || 0);
      recordingUrl = detail.recording_url || '';
      transcript = detail.transcript || '';
      aiSummary = detail.call_summary || '';
      
      const analysis = detail.analysis || {};
      const sentimentVal = (analysis.user_sentiment || '').toLowerCase();
      if (sentimentVal.includes('positive')) {
        sentiment = 'positive';
      } else if (sentimentVal.includes('negative')) {
        sentiment = 'negative';
      }
      
      isMeetingScheduled = !!analysis.book_meeting || !!analysis.meeting_scheduled;
      meetingTimeStr = analysis.meeting_timestamp || '';
    } 
    // 3. Fallback: Direct Sandbox Simulator Format
    else {
      phone = body.phone || '';
      callSid = body.callSid || callSid;
      durationSeconds = body.durationSeconds || 60;
      recordingUrl = body.recordingUrl || 'https://api.vapi.ai/recordings/mock.mp3';
      transcript = body.transcript || 'Mock transcript';
      aiSummary = body.aiSummary || 'Mock call summary';
      sentiment = body.sentiment || 'neutral';
      isMeetingScheduled = body.status === 'meeting_scheduled' || !!body.meetingTime;
      meetingTimeStr = body.meetingTime || '';
    }

    if (!phone) {
      return NextResponse.json({ success: false, error: 'Customer phone number not found in webhook payload.' }, { status: 400 });
    }

    // Lookup Lead in Local DB
    const db = getDb();
    const cleanTargetPhone = cleanPhone(phone);
    
    const leadIndex = db.leads.findIndex(l => cleanPhone(l.phone) === cleanTargetPhone);
    
    if (leadIndex === -1) {
      console.warn(`[Webhook Warning]: No lead found matching phone: ${phone}`);
      return NextResponse.json({ success: false, error: `Lead not found for phone: ${phone}` }, { status: 404 });
    }

    const lead = db.leads[leadIndex];
    let finalLeadStatus: Lead['status'] = 'queued';

    // Determine status logic based on webhook analytics
    if (isMeetingScheduled || sentiment === 'positive') {
      finalLeadStatus = isMeetingScheduled ? 'meeting_scheduled' : 'interested';
    } else if (sentiment === 'negative') {
      finalLeadStatus = 'not_interested';
    } else {
      finalLeadStatus = 'callback_required';
    }

    // Update Lead records
    db.leads[leadIndex] = {
      ...lead,
      status: finalLeadStatus,
      lastCallAt: new Date().toISOString(),
      notes: `${lead.notes || ''}\n\n[AI Outbound Call Outcome - ${new Date().toLocaleDateString()}]: ${aiSummary}`
    };

    // Log the Call Details
    const newCallLog: CallLog = {
      id: `call-${Math.random().toString(36).substr(2, 9)}`,
      leadId: lead.id,
      callSid,
      durationSeconds,
      recordingUrl,
      transcript,
      aiSummary,
      sentiment,
      calledAt: new Date().toISOString()
    };
    db.callLogs.push(newCallLog);

    // If meeting confirmed, trigger calendar invite creation
    let googleMeetLink = '';
    let generatedMeeting: Meeting | null = null;
    
    if (finalLeadStatus === 'meeting_scheduled' || isMeetingScheduled) {
      // Simulate Google Meet integration link builder
      const meetId = Math.random().toString(36).substr(2, 3) + '-' + Math.random().toString(36).substr(2, 4) + '-' + Math.random().toString(36).substr(2, 3);
      googleMeetLink = `https://meet.google.com/${meetId}`;
      
      const scheduledTime = meetingTimeStr ? new Date(meetingTimeStr).toISOString() : new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(); // 3 days layout fallback

      generatedMeeting = {
        id: `meet-${Math.random().toString(36).substr(2, 9)}`,
        leadId: lead.id,
        googleMeetLink,
        scheduledTime,
        status: 'confirmed',
        createdAt: new Date().toISOString()
      };
      
      db.meetings.push(generatedMeeting);
      console.log(`[CALENDAR WEBHOOK SUCCESS]: Created Google Meet session: ${googleMeetLink} for ${lead.name} (${lead.email || 'No email'})`);
    }

    // Save DB
    saveDb(db);
    revalidatePath('/');
    revalidatePath('/dashboard/cold-calling');
    revalidatePath('/support/tickets');

    return NextResponse.json({
      success: true,
      message: 'Webhook processed, call logs filed, and lead updated.',
      leadStatus: finalLeadStatus,
      callLogId: newCallLog.id,
      meetingScheduled: !!generatedMeeting,
      googleMeetLink
    });

  } catch (e: any) {
    console.error('[Webhook Critical Error]:', e);
    return NextResponse.json({ success: false, error: e.message || 'Server error' }, { status: 500 });
  }
}
