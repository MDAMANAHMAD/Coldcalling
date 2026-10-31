import { SarvamCsvRow, CsvValidationResult } from './sarvamTypes';

/**
 * Standard Sarvam AI Samvaad Campaign Header format:
 * phone_number,user_name,initial_bot_message,initial_state_name,initial_language_name
 */
export const SARVAM_EXPECTED_HEADERS = [
  'phone_number',
  'user_name',
  'initial_bot_message',
  'initial_state_name',
  'initial_language_name'
];

/**
 * Normalizes phone number to standard 10-digit or +91 standard format
 */
export function sanitizePhoneNumber(raw: string): string {
  if (!raw) return '';
  const digits = raw.replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) {
    return digits.slice(2);
  }
  if (digits.length === 11 && digits.startsWith('0')) {
    return digits.slice(1);
  }
  return digits;
}

/**
 * Formats unmasked phone number for full display
 */
export function formatFullPhoneNumber(phone: string): string {
  if (!phone) return '—';
  const clean = sanitizePhoneNumber(phone);
  if (clean.length === 10) {
    return `+91 ${clean.slice(0, 5)} ${clean.slice(5)}`;
  }
  return phone.startsWith('+') ? phone : `+91 ${clean}`;
}

/**
 * Parses raw CSV text into rows and columns
 */
function parseCsvLines(csvText: string): string[][] {
  const lines = csvText.split(/\r?\n/).filter(line => line.trim().length > 0);
  const rows: string[][] = [];

  for (const line of lines) {
    const row: string[] = [];
    let inQuotes = false;
    let field = '';

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        row.push(field.trim());
        field = '';
      } else {
        field += char;
      }
    }
    row.push(field.trim());
    rows.push(row.map(r => r.replace(/^["']|["']$/g, '').trim()));
  }

  return rows;
}

/**
 * Validates whether uploaded CSV matches Sarvam AI's requirements,
 * and automatically transforms/heals any misplaced, misnamed, or unformatted columns!
 */
export function validateAndFixSarvamCsv(rawCsv: string): CsvValidationResult {
  const parsedRows = parseCsvLines(rawCsv);
  if (parsedRows.length === 0) {
    return {
      isValid: false,
      totalRows: 0,
      validRows: 0,
      fixedRows: 0,
      invalidRows: 0,
      errors: ['The uploaded CSV file is empty.'],
      warnings: [],
      data: [],
      originalHeaders: [],
      cleanedCsvContent: ''
    };
  }

  const rawHeaders = parsedRows[0];
  const normalizedHeaders = rawHeaders.map(h => h.toLowerCase().trim().replace(/[\s\-_]+/g, '_'));

  // Detect column indexes
  let phoneIdx = normalizedHeaders.findIndex(h => 
    h === 'phone_number' || h === 'phone' || h === 'mobile' || h === 'contact' || h === 'number' || h === 'mobile_number'
  );
  let nameIdx = normalizedHeaders.findIndex(h => 
    h === 'user_name' || h === 'name' || h === 'customer_name' || h === 'client_name' || h === 'lead_name'
  );
  let botMsgIdx = normalizedHeaders.findIndex(h => 
    h === 'initial_bot_message' || h === 'bot_message' || h === 'message' || h === 'greeting'
  );
  let stateIdx = normalizedHeaders.findIndex(h => 
    h === 'initial_state_name' || h === 'state_name' || h === 'state'
  );
  let langIdx = normalizedHeaders.findIndex(h => 
    h === 'initial_language_name' || h === 'language_name' || h === 'language' || h === 'lang'
  );

  const errors: string[] = [];
  const warnings: string[] = [];

  // If header wasn't found, check if first row itself is data
  let isFirstRowHeader = true;
  if (phoneIdx === -1 && nameIdx === -1) {
    const firstRowDigits0 = sanitizePhoneNumber(parsedRows[0][0]);
    const firstRowDigits1 = parsedRows[0].length > 1 ? sanitizePhoneNumber(parsedRows[0][1]) : '';
    if (firstRowDigits0.length === 10 || firstRowDigits1.length === 10) {
      isFirstRowHeader = false;
      warnings.push('Header row was missing. Column types were automatically detected from row values.');
      if (firstRowDigits0.length === 10) {
        phoneIdx = 0;
        nameIdx = parsedRows[0].length > 1 ? 1 : -1;
      } else {
        phoneIdx = 1;
        nameIdx = 0;
      }
    }
  }

  if (phoneIdx === -1) {
    errors.push('Could not detect a Phone Number column. Please ensure there is a phone column in the CSV.');
  }

  const dataRows = isFirstRowHeader ? parsedRows.slice(1) : parsedRows;
  const cleanedData: SarvamCsvRow[] = [];
  let validCount = 0;
  let fixedCount = 0;
  let invalidCount = 0;

  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    if (row.length === 0 || row.every(cell => cell === '')) continue;

    let rawPhone = phoneIdx !== -1 && row[phoneIdx] !== undefined ? row[phoneIdx] : '';
    let rawName = nameIdx !== -1 && row[nameIdx] !== undefined ? row[nameIdx] : '';

    // Auto-detect if name and phone are swapped
    if (rawPhone && !sanitizePhoneNumber(rawPhone) && rawName && sanitizePhoneNumber(rawName)) {
      const temp = rawPhone;
      rawPhone = rawName;
      rawName = temp;
      fixedCount++;
    }

    const cleanDigits = sanitizePhoneNumber(rawPhone);
    const cleanName = rawName.trim().replace(/^[.,_\-'"\s]+|[.,_\-'"\s]+$/g, '') || 'Valued Customer';

    if (cleanDigits.length === 10) {
      if (cleanDigits !== rawPhone) {
        fixedCount++;
      } else {
        validCount++;
      }

      cleanedData.push({
        phone_number: cleanDigits,
        user_name: cleanName,
        initial_bot_message: botMsgIdx !== -1 && row[botMsgIdx] ? row[botMsgIdx] : '',
        initial_state_name: stateIdx !== -1 && row[stateIdx] ? row[stateIdx] : '',
        initial_language_name: langIdx !== -1 && row[langIdx] ? row[langIdx] : ''
      });
    } else {
      invalidCount++;
      warnings.push(`Row ${i + 1}: Skipped invalid phone '${rawPhone}'. Must be a 10-digit Indian phone number.`);
    }
  }

  // Generate verified Sarvam AI CSV string
  const headerLine = SARVAM_EXPECTED_HEADERS.join(',');
  const lines = [headerLine];
  for (const row of cleanedData) {
    const escapedName = row.user_name.includes(',') ? `"${row.user_name}"` : row.user_name;
    lines.push(`${row.phone_number},${escapedName},,,`);
  }
  const cleanedCsvContent = lines.join('\n');

  const isValid = errors.length === 0 && cleanedData.length > 0;

  return {
    isValid,
    totalRows: dataRows.length,
    validRows: validCount,
    fixedRows: fixedCount,
    invalidRows: invalidCount,
    errors,
    warnings,
    data: cleanedData,
    originalHeaders: rawHeaders,
    cleanedCsvContent
  };
}
