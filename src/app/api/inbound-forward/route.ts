import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

// Dedicated recipient for inbound calls: Raj (+918898022337)
const FORWARD_TO_NUMBER = '+918898022337';
const VOBIZ_CALLER_ID = '+918071580297';

export async function POST(req: NextRequest) {
  return handleCallForward(req);
}

export async function GET(req: NextRequest) {
  return handleCallForward(req);
}

async function handleCallForward(req: NextRequest) {
  try {
    // Vobiz Voice XML to bridge the incoming call directly to Asmita mam
    const xmlResponse = `<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial callerId="${VOBIZ_CALLER_ID}" timeout="35">
        <Number>${FORWARD_TO_NUMBER}</Number>
    </Dial>
</Response>`.trim();

    return new NextResponse(xmlResponse, {
      status: 200,
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
      },
    });
  } catch (err: any) {
    console.error('[INBOUND FORWARD ERROR]:', err);
    return new NextResponse(
      `<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>`,
      { status: 500, headers: { 'Content-Type': 'application/xml' } }
    );
  }
}
