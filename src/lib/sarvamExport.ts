import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import { SarvamCallRecord, TimeFilterPeriod } from './sarvamTypes';
import { formatFullPhoneNumber } from './sarvamCsv';

/**
 * Downloads leads in full, unmasked CSV format
 */
export function exportToCsv(
  records: SarvamCallRecord[],
  categoryName: 'Interested' | 'Site_Visit' | 'All'
): void {
  const headers = [
    'ID',
    'Customer Name',
    'Full Phone Number',
    'Outcome',
    'BHK Preference',
    'Site Visit Day',
    'Site Visit Time',
    'Duration (Seconds)',
    'Call Date',
    'Summary'
  ];

  const rows = records.map(r => [
    r.id,
    `"${(r.customerName || 'Valued Customer').replace(/"/g, '""')}"`,
    `"${r.customerPhone}"`, // Strictly unmasked e.g. +919821361686
    r.outcome,
    r.bhkPreference || '—',
    r.siteVisitDay || '—',
    r.siteVisitTime || '—',
    r.durationSeconds,
    r.callDate,
    `"${(r.summary || '').replace(/"/g, '""')}"`
  ]);

  const csvContent = [headers.join(','), ...rows.map(row => row.join(','))].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `Sai_Garden_${categoryName}_Full_Contacts_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Downloads leads in branded Qualivo / Sai Garden PDF with unmasked phone numbers, visit times, and summaries
 */
export function exportToPdf(
  records: SarvamCallRecord[],
  category: 'Interested' | 'Site Visit' | 'All',
  period: TimeFilterPeriod
): void {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  const isSiteVisit = category === 'Site Visit';
  const primaryColor: [number, number, number] = isSiteVisit ? [37, 99, 235] : [16, 185, 129];

  // Header Banner
  doc.setFillColor(...primaryColor);
  doc.rect(0, 0, 297, 24, 'F');

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(14);
  doc.setTextColor(255, 255, 255);
  doc.text(`SAI GARDEN DOMBIVLI EAST — ${category.toUpperCase()} LEADS REPORT`, 14, 11);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8.5);
  doc.text(
    `Qualivo Voice Intelligence  |  Period: ${period.toUpperCase()}  |  Total Leads: ${records.length}  |  Exported: ${new Date().toLocaleString()}`,
    14,
    18
  );

  const tableData = records.map((r, idx) => [
    idx + 1,
    r.customerName || 'Valued Customer',
    r.customerPhone, // Strictly full unmasked phone number
    r.bhkPreference || '—',
    isSiteVisit ? `${r.siteVisitDay || '—'} ${r.siteVisitTime ? '@ ' + r.siteVisitTime : ''}` : r.outcome,
    `${Math.floor(r.durationSeconds / 60)}m ${r.durationSeconds % 60}s`,
    new Date(r.callDate).toLocaleDateString(),
    r.summary || 'Lead captured from automated call.'
  ]);

  autoTable(doc, {
    startY: 28,
    head: [[
      '#',
      'Customer Name',
      'Phone Number (Full)',
      'BHK',
      isSiteVisit ? 'Visit Schedule' : 'Status',
      'Duration',
      'Date',
      'Conversation Summary'
    ]],
    body: tableData,
    theme: 'striped',
    headStyles: {
      fillColor: primaryColor,
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 8.5
    },
    bodyStyles: {
      fontSize: 8,
      cellPadding: 2.5
    },
    columnStyles: {
      0: { cellWidth: 10, halign: 'center' },
      1: { cellWidth: 35, fontStyle: 'bold' },
      2: { cellWidth: 34, fontStyle: 'bold', textColor: [37, 99, 235] },
      3: { cellWidth: 18, halign: 'center' },
      4: { cellWidth: 32 },
      5: { cellWidth: 18, halign: 'center' },
      6: { cellWidth: 22, halign: 'center' },
      7: { cellWidth: 'auto' }
    },
    alternateRowStyles: {
      fillColor: [248, 250, 252]
    }
  });

  doc.save(`Sai_Garden_${category.replace(/\s+/g, '_')}_Leads_${new Date().toISOString().slice(0, 10)}.pdf`);
}
