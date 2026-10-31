import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const API_KEY = process.env.SARVAM_API_KEY || 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI';
const AGENT_ID = process.env.SARVAM_AGENT_ID || 'Gayatari-0922c4e8-551f';
const ORG_ID = process.env.SARVAM_ORG_ID || '01a16c8c-0d2f-7ded-b3cb-6dedfbcc168e';
const WORKSPACE_ID = process.env.SARVAM_WORKSPACE_ID || '01a16c8c-0d68-778c-b5f4-fcd65dd809e6';

/**
 * Proxies call audio recordings directly from Sarvam Voice Agent API
 * with authentication and streams to the client audio player.
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = searchParams.get('id');

    if (!id) {
      return new NextResponse('Missing interaction id', { status: 400 });
    }

    const encodedId = encodeURIComponent(id);
    const sarvamAudioUrl = `https://apps.sarvam.ai/api/analytics/v1/${ORG_ID}/${WORKSPACE_ID}/${AGENT_ID}/recordings/${encodedId}`;

    const res = await fetch(sarvamAudioUrl, {
      headers: {
        'X-API-Key': API_KEY
      }
    });

    if (!res.ok) {
      return new NextResponse('Recording not found or not archived for this call', { status: 404 });
    }

    const audioBuffer = await res.arrayBuffer();

    return new NextResponse(audioBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'audio/wav',
        'Content-Length': audioBuffer.byteLength.toString(),
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=86400, stale-while-revalidate=43200'
      }
    });
  } catch (err: any) {
    console.error('Error fetching call recording:', err);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}
