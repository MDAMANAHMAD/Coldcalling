import { NextRequest, NextResponse } from 'next/server';
import { getSarvamDb, saveSarvamDb } from '@/lib/sarvamDb';
import { SarvamCallRecord } from '@/lib/sarvamTypes';

export const dynamic = 'force-dynamic';

/**
 * Sarvam AI Webhook Endpoint:
 * Receives completed call webhooks from Sarvam Voice Agent / Instant Outbound.
 * Strictly checks outcome and retains ONLY 'Interested' and 'Site Visit' calls,
 * alongside complete turn-by-turn transcripts and audio recordings!
 */
export async function POST(req: NextRequest) {
  try {
    const payload = await req.json();
    console.log('🔔 [Sarvam AI Webhook Received]:', JSON.stringify(payload, null, 2));

    const interactionId = payload.interaction_id || payload.attempt_id || `sarvam-${Date.now()}`;
    const userPhone = payload.user_phone_number || payload.phone || payload.to || '';
    const duration = Math.round(payload.duration || payload.durationSeconds || 0);

    // Format transcript turns
    let transcriptText = '';
    if (Array.isArray(payload.interaction_transcript)) {
      transcriptText = payload.interaction_transcript
        .map((t: any) => `[${t.role === 'agent' ? 'Gayatri' : 'Customer'}]: ${t.indic_text || t.en_text || ''}`)
        .join('\n');
    } else if (typeof payload.transcript === 'string') {
      transcriptText = payload.transcript;
    }

    const lowerTranscript = transcriptText.toLowerCase();

    // Determine high-intent status
    let outcome: SarvamCallRecord['outcome'] = 'Other';
    let bhkPreference: SarvamCallRecord['bhkPreference'] = undefined;
    let siteVisitDay: string | undefined = undefined;
    let siteVisitTime: string | undefined = undefined;

    if (lowerTranscript.includes('2 bhk') || lowerTranscript.includes('two bhk') || lowerTranscript.includes('दो बीएचके')) {
      bhkPreference = '2 BHK';
    } else if (lowerTranscript.includes('1 bhk') || lowerTranscript.includes('one bhk') || lowerTranscript.includes('एक बीएचके')) {
      bhkPreference = '1 BHK';
    }

    if (
      lowerTranscript.includes('साईट विजिट कन्फर्म') ||
      lowerTranscript.includes('site visit') ||
      lowerTranscript.includes('visiting') ||
      lowerTranscript.includes('रविवार') ||
      lowerTranscript.includes('शनिवार') ||
      lowerTranscript.includes('sunday') ||
      lowerTranscript.includes('saturday')
    ) {
      outcome = 'Site Visit';
      // Attempt extract day
      if (lowerTranscript.includes('sunday') || lowerTranscript.includes('रविवार')) siteVisitDay = 'Sunday';
      else if (lowerTranscript.includes('saturday') || lowerTranscript.includes('शनिवार')) siteVisitDay = 'Saturday';
      else siteVisitDay = 'Weekend';
    } else if (
      lowerTranscript.includes('व्हाट्सऐप') ||
      lowerTranscript.includes('whatsapp') ||
      lowerTranscript.includes('details') ||
      lowerTranscript.includes('price') ||
      lowerTranscript.includes('brochure') ||
      lowerTranscript.includes('interested')
    ) {
      outcome = 'Interested';
    } else if (
      lowerTranscript.includes('not interested') ||
      lowerTranscript.includes('नहीं चाहिए') ||
      lowerTranscript.includes('wrong number')
    ) {
      outcome = 'Not Interested';
    }

    // STRICT USER REQUIREMENT:
    // Retain only the call logs of the interested and site visit people!
    if (outcome === 'Interested' || outcome === 'Site Visit') {
      const db = getSarvamDb();

      // Clean full phone number
      const cleanDigits = userPhone.replace(/\D/g, '');
      const fullPhone = cleanDigits.length === 10 ? `+91${cleanDigits}` : userPhone.startsWith('+') ? userPhone : `+${cleanDigits}`;

      const newRecord: SarvamCallRecord = {
        id: `sarvam-${Date.now()}`,
        interactionId,
        customerName: payload.user_name || payload.customerName || 'Valued Client',
        customerPhone: fullPhone, // Always FULL unmasked phone number
        callDate: new Date().toISOString(),
        durationSeconds: duration,
        status: 'completed',
        outcome,
        bhkPreference,
        siteVisitDay,
        siteVisitTime,
        transcript: transcriptText,
        recordingUrl: payload.recording_url || payload.audio_url || '',
        summary: payload.summary || `Client showed strong intent (${outcome}) during Sarvam automated call.`,
        agentId: db.config.agentId,
        fromNumber: db.config.fromNumber
      };

      // Upsert
      db.calls.unshift(newRecord);

      // Update live campaign counter
      if (db.campaigns.length > 0) {
        db.campaigns[0].completedCalls++;
        if (db.campaigns[0].remainingCalls > 0) db.campaigns[0].remainingCalls--;
        if (outcome === 'Interested') db.campaigns[0].interestedCount++;
        if (outcome === 'Site Visit') db.campaigns[0].siteVisitCount++;
        db.campaigns[0].updatedAt = new Date().toISOString();
      }

      saveSarvamDb(db);
      console.log(`✅ [Retained High-Intent Call]: ${outcome} for ${fullPhone}`);
    } else {
      console.log(`ℹ️ [Skipped Call Log]: Outcome was '${outcome}'. Dashboard retains only Interested & Site Visit calls.`);
    }

    return NextResponse.json({ success: true, outcome });
  } catch (err: any) {
    console.error('Webhook error:', err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
