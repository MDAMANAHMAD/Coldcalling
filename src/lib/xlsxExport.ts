import * as XLSX from 'xlsx';
import { CallLog } from '@/lib/types';
import { getCallTimestampMs, formatCallDuration, getCallPickedInfo } from '@/lib/callUtils';

export type XlsxReportCategory = 'Interested' | 'Site Visit' | 'Future Plan' | 'Not Interested' | 'All';

interface ExportXlsxOptions {
  category: XlsxReportCategory;
  calls: (CallLog & { leadName?: string; leadPhone?: string })[];
  getOutcomeTag: (call: CallLog) => { label: string };
  userEmail?: string;
}

export function exportLeadsToXlsx({
  category,
  calls,
  getOutcomeTag,
  userEmail = 'test@gmail.com',
}: ExportXlsxOptions) {
  // 1. Filter calls based on category
  const filtered = calls.filter((call) => {
    const tag = getOutcomeTag(call).label;
    if (category === 'All') return true;
    if (category === 'Interested') return tag === 'Interested';
    if (category === 'Future Plan') return tag === 'Future Plan / Need Afterwards';
    if (category === 'Site Visit') return tag === 'Site Visit Scheduled';
    if (category === 'Not Interested') return tag === 'Not Interested';
    return true;
  });

  // 2. Prepare headers & rows
  const headers = [
    'S.No',
    'Customer Name',
    'Phone Number',
    'Date & Time (IST)',
    'Duration',
    'Outcome / Intent',
    'Call Picked Up',
    'AI Executive Summary',
    'Verbatim Transcript',
    'Call SID / ID'
  ];

  const rows = filtered.map((call, idx) => {
    const timestampMs = getCallTimestampMs(call);
    const dateStr = timestampMs > 0
      ? new Date(timestampMs).toLocaleString('en-IN', {
          timeZone: 'Asia/Kolkata',
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        })
      : (call.calledAt || 'N/A');

    const duration = formatCallDuration(call);
    const outcome = getOutcomeTag(call).label;
    const pickedInfo = getCallPickedInfo(call);
    const name = call.customerName || call.leadName || 'Customer';
    const phone = call.customerPhone || call.leadPhone || '';
    const summary = call.aiSummary || '';
    const transcript = call.transcript || '';
    const callSid = call.callSid || call.id || '';

    return [
      idx + 1,
      name,
      phone,
      dateStr,
      duration,
      outcome,
      pickedInfo.label,
      summary,
      transcript,
      callSid
    ];
  });

  const sheetData = [headers, ...rows];
  const worksheet = XLSX.utils.aoa_to_sheet(sheetData);

  // Set column widths for clean readability
  worksheet['!cols'] = [
    { wch: 6 },   // S.No
    { wch: 22 },  // Customer Name
    { wch: 18 },  // Phone Number
    { wch: 22 },  // Date & Time
    { wch: 14 },  // Duration
    { wch: 22 },  // Outcome / Intent
    { wch: 16 },  // Call Picked Up
    { wch: 55 },  // AI Summary
    { wch: 80 },  // Transcript
    { wch: 28 },  // Call SID
  ];

  const workbook = XLSX.utils.book_new();
  const sheetName = category === 'All' ? 'All Leads' : category.slice(0, 31);
  XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);

  const dateSuffix = new Date().toISOString().slice(0, 10);
  const cleanCategoryName = category.replace(/\s+/g, '_');
  const filename = `Gayatri_AI_${cleanCategoryName}_Leads_${dateSuffix}.xlsx`;

  XLSX.writeFile(workbook, filename);
}
