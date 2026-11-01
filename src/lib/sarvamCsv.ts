import { SarvamCsvRow, CsvValidationResult, CsvSkippedRowDetail } from './sarvamTypes';

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
 * Normalizes phone number to standard 10-digit Indian mobile format.
 * Strips whitespace, country codes (+91, 91), leading 0, Excel .0 decimals, and special characters.
 */
export function sanitizePhoneNumber(raw: any): string {
  if (raw === null || raw === undefined) return '';
  let str = String(raw).trim().replace(/\.0+$/, '');
  const digits = str.replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) {
    return digits.slice(2);
  }
  if (digits.length === 11 && digits.startsWith('0')) {
    return digits.slice(1);
  }
  return digits;
}

/**
 * Validates whether a sanitized phone number is a valid, callable Indian mobile number.
 * Strict rules to guarantee invalid numbers or missing data are never dialed:
 * 1. Must not be empty or null
 * 2. Must be exactly 10 digits
 * 3. Must start with 6, 7, 8, or 9
 * 4. Must not be repeating dummy digits (0000000000, 9999999999, etc.)
 * 5. Must not be sequential dummy sequences (1234567890, etc.)
 */
export function isValidIndianMobile(cleanDigits: string): { isValid: boolean; reason?: string } {
  if (!cleanDigits || cleanDigits.trim().length === 0) {
    return { isValid: false, reason: 'Phone number is missing or empty' };
  }

  if (cleanDigits.length !== 10) {
    return { 
      isValid: false, 
      reason: cleanDigits.length < 10 
        ? `Incomplete phone number (${cleanDigits.length} digits, must be 10)` 
        : `Invalid phone length (${cleanDigits.length} digits, must be 10)` 
    };
  }

  if (!/^[6-9]/.test(cleanDigits)) {
    return { 
      isValid: false, 
      reason: `Invalid starting digit '${cleanDigits[0]}'. Indian mobile numbers must start with 6, 7, 8, or 9` 
    };
  }

  // Reject repeating dummy numbers like 0000000000, 1111111111, ..., 9999999999
  if (/^(\d)\1{9}$/.test(cleanDigits)) {
    return { isValid: false, reason: 'Dummy/test repeating digits' };
  }

  // Reject sequential test sequences
  if (cleanDigits === '1234567890' || cleanDigits === '0123456789' || cleanDigits === '9876543210') {
    return { isValid: false, reason: 'Dummy sequential test number' };
  }

  return { isValid: true };
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
  const seenPhoneNumbers = new Set<string>();
  const skippedDetails: CsvSkippedRowDetail[] = [];
  let validCount = 0;
  let fixedCount = 0;
  let invalidCount = 0;
  let missingDataCount = 0;
  let duplicateCount = 0;

  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    const rowNum = isFirstRowHeader ? i + 2 : i + 1; // 1-indexed row number in original file

    // 1. Check if row is completely empty
    if (row.length === 0 || row.every(cell => !cell || cell.trim() === '')) {
      missingDataCount++;
      skippedDetails.push({
        rowNumber: rowNum,
        reason: 'Entire row is blank or missing data'
      });
      continue;
    }

    let rawPhone = phoneIdx !== -1 && row[phoneIdx] !== undefined ? String(row[phoneIdx]).trim() : '';
    let rawName = nameIdx !== -1 && row[nameIdx] !== undefined ? String(row[nameIdx]).trim() : '';

    // 2. Check if phone column has missing or placeholder data
    const isMissingPhone = !rawPhone || ['n/a', 'na', 'null', 'none', 'undefined', '-', '--', 'nil'].includes(rawPhone.toLowerCase());
    if (isMissingPhone) {
      // Check if maybe swapped with name column
      if (rawName && sanitizePhoneNumber(rawName)) {
        const temp = rawPhone;
        rawPhone = rawName;
        rawName = temp;
        fixedCount++;
      } else {
        missingDataCount++;
        invalidCount++;
        skippedDetails.push({
          rowNumber: rowNum,
          rawPhone,
          rawName,
          reason: 'Missing phone number (empty data cell)'
        });
        warnings.push(`Row ${rowNum}: Skipped due to missing phone number.`);
        continue;
      }
    }

    // Auto-detect if name and phone are swapped
    const candidatePhoneDigits = sanitizePhoneNumber(rawPhone);
    const candidateNameDigits = sanitizePhoneNumber(rawName);
    if (!isValidIndianMobile(candidatePhoneDigits).isValid && isValidIndianMobile(candidateNameDigits).isValid) {
      const temp = rawPhone;
      rawPhone = rawName;
      rawName = temp;
      fixedCount++;
    }

    const cleanDigits = sanitizePhoneNumber(rawPhone);
    const phoneCheck = isValidIndianMobile(cleanDigits);

    // 3. Strict filter: If invalid number, SKIP and do not try this number
    if (!phoneCheck.isValid) {
      invalidCount++;
      skippedDetails.push({
        rowNumber: rowNum,
        rawPhone,
        rawName,
        reason: phoneCheck.reason || 'Invalid phone number'
      });
      warnings.push(`Row ${rowNum}: Skipped invalid phone '${rawPhone}'. Reason: ${phoneCheck.reason}.`);
      continue;
    }

    // 4. Duplicate prevention: Skip if number was already seen in this batch
    if (seenPhoneNumbers.has(cleanDigits)) {
      duplicateCount++;
      skippedDetails.push({
        rowNumber: rowNum,
        rawPhone,
        rawName,
        reason: 'Duplicate phone number in sheet (already queued)'
      });
      warnings.push(`Row ${rowNum}: Skipped duplicate phone '+91 ${cleanDigits}'.`);
      continue;
    }

    seenPhoneNumbers.add(cleanDigits);

    // Clean customer name or provide polite fallback if missing
    let cleanName = rawName.replace(/^[.,_\-'"\s]+|[.,_\-'"\s]+$/g, '').trim();
    if (!cleanName || ['n/a', 'na', 'null', 'none', 'undefined', '-', '--', 'nil'].includes(cleanName.toLowerCase())) {
      cleanName = `Buyer ${cleanDigits.slice(-4)}`;
      fixedCount++;
    }

    if (cleanDigits !== rawPhone.trim()) {
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
    missingDataRows: missingDataCount,
    duplicateRows: duplicateCount,
    skippedDetails,
    errors,
    warnings,
    data: cleanedData,
    originalHeaders: rawHeaders,
    cleanedCsvContent
  };
}
