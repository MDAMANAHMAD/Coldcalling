import { NextRequest, NextResponse } from 'next/server';
import { validateAndFixSarvamCsv } from '@/lib/sarvamCsv';
import * as XLSX from 'xlsx';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get('file') as File | null;
    let csvText = '';

    if (file) {
      const fileName = (file.name || '').toLowerCase();
      // Handle Excel formats (.xlsx, .xls)
      if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
        const arrayBuffer = await file.arrayBuffer();
        const workbook = XLSX.read(Buffer.from(arrayBuffer), { type: 'buffer' });
        const firstSheetName = workbook.SheetNames[0];
        if (!firstSheetName) {
          return NextResponse.json({ error: 'Uploaded Excel file has no worksheets.' }, { status: 400 });
        }
        const worksheet = workbook.Sheets[firstSheetName];
        csvText = XLSX.utils.sheet_to_csv(worksheet, { blankrows: false });
      } else {
        // Handle CSV, TSV, TXT
        csvText = await file.text();
      }
    } else {
      const body = await req.json().catch(() => ({}));
      csvText = body.csvText || '';
    }

    if (!csvText || csvText.trim().length === 0) {
      return NextResponse.json({ error: 'Uploaded file is empty or contains no readable data.' }, { status: 400 });
    }

    const validationResult = validateAndFixSarvamCsv(csvText);
    return NextResponse.json(validationResult);
  } catch (err: any) {
    console.error('Error validating calling sheet:', err);
    return NextResponse.json({ error: err.message || 'Sheet validation failed' }, { status: 500 });
  }
}
