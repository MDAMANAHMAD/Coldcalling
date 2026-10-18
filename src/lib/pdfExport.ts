import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import { CallLog } from '@/lib/types';
import { getCallTimestampMs, formatCallDuration } from '@/lib/callUtils';

export type PdfReportCategory = 'Interested' | 'Site Visit' | 'Future Plan' | 'Not Interested' | 'All';

interface ExportPdfOptions {
  category: PdfReportCategory;
  calls: (CallLog & { leadName?: string; leadPhone?: string })[];
  getOutcomeTag: (call: CallLog) => { label: string };
  userEmail?: string;
}

export function exportLeadsToPdf({
  category,
  calls,
  getOutcomeTag,
  userEmail = 'test@gmail.com',
}: ExportPdfOptions) {
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

  // 2. Titles and color schemes per category
  const categoryConfig: Record<
    PdfReportCategory,
    { title: string; subtitle: string; primaryColor: [number, number, number]; filename: string }
  > = {
    Interested: {
      title: 'INTERESTED CLIENTS LEADS REPORT',
      subtitle: 'High-intent prospective buyers interested in Sai Complex Dombivli East (1 BHK / 2 BHK)',
      primaryColor: [16, 185, 129], // Emerald green
      filename: `Gayatri_AI_Interested_Leads_${new Date().toISOString().slice(0, 10)}.pdf`,
    },
    'Site Visit': {
      title: 'SITE VISIT SCHEDULED LEADS REPORT',
      subtitle: 'Confirmed site visit appointments booked for Sai Complex Dombivli East',
      primaryColor: [37, 99, 235], // Royal blue
      filename: `Gayatri_AI_Site_Visits_${new Date().toISOString().slice(0, 10)}.pdf`,
    },
    'Future Plan': {
      title: 'FUTURE PLAN / FOLLOW-UP LEADS REPORT',
      subtitle: 'Clients requesting callback later, future purchase plans, or postponed decision',
      primaryColor: [217, 119, 6], // Amber
      filename: `Gayatri_AI_Future_Plan_Leads_${new Date().toISOString().slice(0, 10)}.pdf`,
    },
    'Not Interested': {
      title: 'NOT INTERESTED / DNC LEADS REPORT',
      subtitle: 'Opted out, wrong numbers, or not currently looking to purchase property',
      primaryColor: [225, 29, 72], // Rose red
      filename: `Gayatri_AI_Not_Interested_Leads_${new Date().toISOString().slice(0, 10)}.pdf`,
    },
    All: {
      title: 'COMPLETE CALL LOGS & LEADS REPORT',
      subtitle: 'Comprehensive log of all AI outbound calls conducted by Gayatri Voice Agent',
      primaryColor: [30, 41, 59], // Slate navy
      filename: `Gayatri_AI_All_Leads_Report_${new Date().toISOString().slice(0, 10)}.pdf`,
    },
  };

  const config = categoryConfig[category];
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  const pageWidth = doc.internal.pageSize.getWidth();
  const generatedAt = new Date().toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  // ── HEADER BANNER ──────────────────────────────────────────────────────────
  doc.setFillColor(...config.primaryColor);
  doc.rect(0, 0, pageWidth, 28, 'F');

  // Brand Name
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.text('GAYATRI AI — REAL ESTATE COLD CALLING', 14, 11);

  // Subtitle / Report Title
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(11);
  doc.text(config.title, 14, 18);

  // Right side info (Date & Lead Count)
  doc.setFontSize(9);
  doc.text(`Generated: ${generatedAt}`, pageWidth - 14, 10, { align: 'right' });
  doc.text(`Total Leads: ${filtered.length} | Account: ${userEmail}`, pageWidth - 14, 16, { align: 'right' });
  doc.text(`Project: Sai Complex Dombivli East`, pageWidth - 14, 22, { align: 'right' });

  // Thin accent line below header
  doc.setDrawColor(241, 245, 249);
  doc.setLineWidth(0.5);
  doc.line(0, 28, pageWidth, 28);

  // Subtitle note
  doc.setTextColor(71, 85, 105);
  doc.setFontSize(9);
  doc.setFont('helvetica', 'italic');
  doc.text(config.subtitle, 14, 34);

  // ── TABLE GENERATION ────────────────────────────────────────────────────────
  const tableData = filtered.map((call, index) => {
    const name = call.customerName || call.leadName || 'Valued Customer';
    const phone = call.customerPhone || call.leadPhone || '+918693081506';
    const tag = getOutcomeTag(call).label;
    const timeMs = getCallTimestampMs(call);
    const dateStr = timeMs > 0 ? new Date(timeMs).toLocaleString('en-IN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }) : 'Recent';
    const duration = formatCallDuration(call);
    const summary = call.aiSummary || 'Outbound consultation regarding Sai Complex Dombivli East.';

    return [
      String(index + 1),
      name,
      phone,
      dateStr,
      duration,
      tag,
      summary,
    ];
  });

  if (tableData.length === 0) {
    tableData.push([
      '-',
      'No records found',
      '-',
      '-',
      '-',
      category,
      `No leads currently categorized under "${category}".`,
    ]);
  }

  autoTable(doc, {
    startY: 38,
    head: [['#', 'Customer Name', 'Phone Number', 'Call Date', 'Duration', 'Category', 'Discussion Summary']],
    body: tableData,
    theme: 'grid',
    headStyles: {
      fillColor: config.primaryColor,
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 9,
      halign: 'left',
    },
    styles: {
      fontSize: 8.5,
      textColor: [30, 41, 59],
      cellPadding: 2.5,
      valign: 'middle',
      overflow: 'linebreak',
    },
    alternateRowStyles: {
      fillColor: [248, 250, 252],
    },
    columnStyles: {
      0: { cellWidth: 10, halign: 'center' }, // #
      1: { cellWidth: 38, fontStyle: 'bold' }, // Customer Name
      2: { cellWidth: 38, textColor: [37, 99, 235], fontStyle: 'bold' }, // Phone Number
      3: { cellWidth: 32 }, // Call Date
      4: { cellWidth: 20, halign: 'center' }, // Duration
      5: { cellWidth: 38, fontStyle: 'bold' }, // Category
      6: { cellWidth: 'auto' }, // Summary
    },
    didDrawPage: (data) => {
      // Footer: Page number and branding
      const pageNumber = doc.getNumberOfPages();
      doc.setFontSize(8);
      doc.setTextColor(148, 163, 184);
      doc.setFont('helvetica', 'normal');
      doc.text(
        `Gayatri AI Real Estate Intelligence • Sai Complex, Dombivli East (Shiv Sai Construction Company) • Page ${pageNumber}`,
        14,
        doc.internal.pageSize.getHeight() - 6
      );
      doc.text(
        `Confidential Lead Report`,
        pageWidth - 14,
        doc.internal.pageSize.getHeight() - 6,
        { align: 'right' }
      );
    },
  });

  // 3. Save & trigger download
  doc.save(config.filename);
}
