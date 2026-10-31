import { NextRequest, NextResponse } from 'next/server';
import { validateAndFixSarvamCsv } from '@/lib/sarvamCsv';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get('file') as File | null;
    let csvText = '';

    if (file) {
      csvText = await file.text();
    } else {
      const body = await req.json().catch(() => ({}));
      csvText = body.csvText || '';
    }

    if (!csvText) {
      return NextResponse.json({ error: 'No CSV content provided' }, { status: 400 });
    }

    const validationResult = validateAndFixSarvamCsv(csvText);
    return NextResponse.json(validationResult);
  } catch (err: any) {
    console.error('Error validating CSV:', err);
    return NextResponse.json({ error: err.message || 'CSV validation failed' }, { status: 500 });
  }
}
