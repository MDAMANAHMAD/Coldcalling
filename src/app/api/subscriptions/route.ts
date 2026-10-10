import { NextRequest, NextResponse } from 'next/server';
import { getDb, saveDb } from '@/lib/db';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

// Base default recharge balances if not customized by user yet
const DEFAULT_SUBSCRIPTIONS = {
  vobiz: {
    id: 'vobiz',
    name: 'Vobiz Telephony (SIP Trunk)',
    provider: 'Vobiz AI',
    role: 'Carrier line for outbound calls & caller ID (+918071580297)',
    allocatedBalance: 500.0, // INR
    currency: 'INR',
    unit: '₹',
    rateDescription: '₹0.40 / minute outbound call billing',
    rechargeUrl: 'https://vobiz.ai',
    rechargeNote: 'Prepaid wallet recharge required for carrier SIP dialer',
    minThreshold: 50.0,
  },
  cartesia: {
    id: 'cartesia',
    name: 'Cartesia Voice Engine',
    provider: 'Cartesia AI',
    role: 'Gayatri Kusha Cloned Voice (sonic-3.5 Real-Time TTS)',
    allocatedBalance: 25.0, // USD
    currency: 'USD',
    unit: '$',
    rateDescription: '~$0.075 / 1,000 characters synthesized',
    rechargeUrl: 'https://play.cartesia.ai',
    rechargeNote: 'Prepaid character credits / monthly tier renewal',
    minThreshold: 3.0,
  },
  deepgram: {
    id: 'deepgram',
    name: 'Deepgram Speech-to-Text',
    provider: 'Deepgram (Nova-3)',
    role: 'Real-time conversational Hindi & English speech recognition',
    allocatedBalance: 20.0, // USD
    currency: 'USD',
    unit: '$',
    rateDescription: '$0.0043 / audio minute stream',
    rechargeUrl: 'https://console.deepgram.com',
    rechargeNote: "Project wallet balance on amanahmad0406@gmail.com's Project",
    minThreshold: 2.0,
  },
  livekit: {
    id: 'livekit',
    name: 'LiveKit Cloud Infrastructure',
    provider: 'LiveKit Cloud',
    role: 'Cloud WebRTC audio server & SIP gateway bridge (cold-calling-j7qhnkas)',
    allocatedBalance: 50.0, // GB free monthly
    currency: 'GB',
    unit: 'GB',
    rateDescription: 'Includes 50 GB free monthly bandwidth & agent minutes',
    rechargeUrl: 'https://cloud.livekit.io',
    rechargeNote: 'Active cloud tier. Top-up only if monthly bandwidth exceeds 50 GB',
    minThreshold: 5.0,
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini AI Brain',
    provider: 'Google AI Studio',
    role: 'Ultra-low latency conversation logic (gemini-3.5-flash-lite)',
    allocatedBalance: 100.0, // % quota
    currency: '%',
    unit: '%',
    rateDescription: '$0.075 / 1M input tokens, $0.30 / 1M output tokens',
    rechargeUrl: 'https://aistudio.google.com',
    rechargeNote: 'Pay-as-you-go quota on Google Cloud API billing',
    minThreshold: 10.0,
  },
};

export async function GET() {
  try {
    const db = getDb();
    const callLogs = db.callLogs || [];

    // Calculate actual usage from logged calls
    let totalDurationSeconds = 0;
    for (const log of callLogs) {
      totalDurationSeconds += Number(log.durationSeconds || 0);
    }
    const totalMinutes = totalDurationSeconds / 60;
    const totalCalls = callLogs.length;

    // Approximate consumption metrics
    const consumedVobizInr = Math.round(totalMinutes * 0.40 * 100) / 100;
    // ~350 characters spoken per minute of call
    const estimatedChars = Math.round(totalMinutes * 350);
    const consumedCartesiaUsd = Math.round(((estimatedChars / 1000) * 0.075) * 100) / 100;
    const consumedDeepgramUsd = Math.round((totalMinutes * 0.0043) * 100) / 100;
    // ~0.5 MB bandwidth per minute of audio
    const consumedLivekitGb = Math.round(((totalMinutes * 0.5) / 1024) * 1000) / 1000;
    // ~1200 tokens per minute
    const estimatedTokens = Math.round(totalMinutes * 1200);
    const consumedGeminiPercent = Math.min(100, Math.round((totalCalls * 0.2) * 10) / 10);

    const savedSubscriptions = (db as any).subscriptions || {};

    const items = [
      {
        ...DEFAULT_SUBSCRIPTIONS.vobiz,
        allocatedBalance: savedSubscriptions.vobiz?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.vobiz.allocatedBalance,
        consumed: consumedVobizInr,
        remaining: Math.max(0, Math.round(((savedSubscriptions.vobiz?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.vobiz.allocatedBalance) - consumedVobizInr) * 100) / 100),
        status: ((savedSubscriptions.vobiz?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.vobiz.allocatedBalance) - consumedVobizInr) <= DEFAULT_SUBSCRIPTIONS.vobiz.minThreshold ? 'Needs Recharge' : 'Active & Healthy',
        isLow: ((savedSubscriptions.vobiz?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.vobiz.allocatedBalance) - consumedVobizInr) <= DEFAULT_SUBSCRIPTIONS.vobiz.minThreshold,
      },
      {
        ...DEFAULT_SUBSCRIPTIONS.cartesia,
        allocatedBalance: savedSubscriptions.cartesia?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.cartesia.allocatedBalance,
        consumed: consumedCartesiaUsd,
        remaining: Math.max(0, Math.round(((savedSubscriptions.cartesia?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.cartesia.allocatedBalance) - consumedCartesiaUsd) * 100) / 100),
        status: ((savedSubscriptions.cartesia?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.cartesia.allocatedBalance) - consumedCartesiaUsd) <= DEFAULT_SUBSCRIPTIONS.cartesia.minThreshold ? 'Needs Recharge' : 'Active & Healthy',
        isLow: ((savedSubscriptions.cartesia?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.cartesia.allocatedBalance) - consumedCartesiaUsd) <= DEFAULT_SUBSCRIPTIONS.cartesia.minThreshold,
      },
      {
        ...DEFAULT_SUBSCRIPTIONS.deepgram,
        allocatedBalance: savedSubscriptions.deepgram?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.deepgram.allocatedBalance,
        consumed: consumedDeepgramUsd,
        remaining: Math.max(0, Math.round(((savedSubscriptions.deepgram?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.deepgram.allocatedBalance) - consumedDeepgramUsd) * 100) / 100),
        status: ((savedSubscriptions.deepgram?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.deepgram.allocatedBalance) - consumedDeepgramUsd) <= DEFAULT_SUBSCRIPTIONS.deepgram.minThreshold ? 'Needs Recharge' : 'Active & Healthy',
        isLow: ((savedSubscriptions.deepgram?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.deepgram.allocatedBalance) - consumedDeepgramUsd) <= DEFAULT_SUBSCRIPTIONS.deepgram.minThreshold,
      },
      {
        ...DEFAULT_SUBSCRIPTIONS.livekit,
        allocatedBalance: savedSubscriptions.livekit?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.livekit.allocatedBalance,
        consumed: consumedLivekitGb,
        remaining: Math.max(0, Math.round(((savedSubscriptions.livekit?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.livekit.allocatedBalance) - consumedLivekitGb) * 100) / 100),
        status: 'Active & Healthy',
        isLow: false,
      },
      {
        ...DEFAULT_SUBSCRIPTIONS.gemini,
        allocatedBalance: savedSubscriptions.gemini?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.gemini.allocatedBalance,
        consumed: consumedGeminiPercent,
        remaining: Math.max(0, Math.round(((savedSubscriptions.gemini?.allocatedBalance ?? DEFAULT_SUBSCRIPTIONS.gemini.allocatedBalance) - consumedGeminiPercent) * 10) / 10),
        status: 'Active & Healthy',
        isLow: false,
      },
    ];

    const needsRechargeCount = items.filter(i => i.isLow).length;

    return NextResponse.json({
      success: true,
      projectName: 'Qualivo',
      activeUsageStats: {
        totalCalls,
        totalMinutes: Math.round(totalMinutes * 100) / 100,
        estimatedChars,
        estimatedTokens,
      },
      subscriptions: items,
      needsRechargeCount,
      excludedFallbacks: [
        { name: 'ElevenLabs', role: 'TTS Backup Voice (Inactive / Standby only)' },
        { name: 'Groq LPU', role: 'LLM Backup Brain (Inactive / Standby only)' },
        { name: 'Fireworks AI', role: 'LLM Backup Brain (Inactive / Standby only)' },
      ],
    });
  } catch (err: any) {
    console.error('Error fetching subscriptions:', err);
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { serviceId, newBalance } = body;

    if (!serviceId || typeof newBalance !== 'number' || newBalance < 0) {
      return NextResponse.json(
        { success: false, message: 'Invalid serviceId or balance.' },
        { status: 400 }
      );
    }

    const db = getDb();
    if (!(db as any).subscriptions) {
      (db as any).subscriptions = {};
    }
    if (!(db as any).subscriptions[serviceId]) {
      (db as any).subscriptions[serviceId] = {};
    }

    (db as any).subscriptions[serviceId].allocatedBalance = Math.round(newBalance * 100) / 100;
    (db as any).subscriptions[serviceId].updatedAt = new Date().toISOString();
    saveDb(db);

    return NextResponse.json({
      success: true,
      message: `Updated ${serviceId} allocated balance to ${newBalance}.`,
      updated: (db as any).subscriptions[serviceId],
    });
  } catch (err: any) {
    console.error('Error updating subscriptions:', err);
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}
