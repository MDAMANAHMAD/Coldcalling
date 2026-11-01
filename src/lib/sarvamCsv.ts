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
 * Parses raw CSV or spreadsheet text into rows and columns.
 * Automatically detects delimiters: comma, semicolon, tab (TSV), or pipe.
 */
function parseCsvLines(csvText: string): string[][] {
  const lines = csvText.split(/\r?\n/).filter(line => line.trim().length > 0);
  if (lines.length === 0) return [];

  // Auto-detect delimiter from the first few non-empty lines
  const sample = lines.slice(0, 5).join('\n');
  const commaCount = (sample.match(/,/g) || []).length;
  const semiCount = (sample.match(/;/g) || []).length;
  const tabCount = (sample.match(/\t/g) || []).length;
  const pipeCount = (sample.match(/\|/g) || []).length;

  let delimiter = ',';
  if (tabCount > commaCount && tabCount > semiCount) {
    delimiter = '\t';
  } else if (semiCount > commaCount && semiCount > tabCount) {
    delimiter = ';';
  } else if (pipeCount > commaCount && pipeCount > semiCount) {
    delimiter = '|';
  }

  const rows: string[][] = [];

  for (const line of lines) {
    const row: string[] = [];
    let inQuotes = false;
    let field = '';

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === delimiter && !inQuotes) {
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
 * Validates whether uploaded calling sheet matches requirements,
 * and automatically transforms, repairs, and handles interchanged columns, inverted fields,
 * and any column structure (Name-Phone, Phone-Name, multi-column, or no headers)!
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
      errors: ['The uploaded calling sheet is empty.'],
      warnings: [],
      data: [],
      originalHeaders: [],
      cleanedCsvContent: ''
    };
  }

  const firstRow = parsedRows[0];
  // Check if first row is actually data (contains a valid 10-digit phone number)
  const firstRowHasPhone = firstRow.some(cell => isValidIndianMobile(sanitizePhoneNumber(cell)).isValid);
  const isFirstRowHeader = !firstRowHasPhone;
  const rawHeaders = isFirstRowHeader ? firstRow : [];

  let phoneIdx = -1;
  let nameIdx = -1;
  let botMsgIdx = -1;
  let stateIdx = -1;
  let langIdx = -1;

  const phoneKeywords = [
    'phone_number', 'phone', 'mobile', 'mobile_number', 'contact', 'contact_number',
    'number', 'cell', 'cellular', 'tel', 'telephone', 'ph_no', 'phone_no', 'mobile_no',
    'contact_no', 'wa_number', 'whatsapp', 'call', 'caller_id', 'cust_phone', 'client_phone'
  ];

  const nameKeywords = [
    'user_name', 'name', 'customer_name', 'client_name', 'lead_name', 'buyer_name',
    'contact_name', 'person', 'first_name', 'full_name', 'client', 'customer', 'lead', 'buyer'
  ];

  if (isFirstRowHeader) {
    const normalizedHeaders = firstRow.map(h => h.toLowerCase().trim().replace(/[\s\-_]+/g, '_'));

    phoneIdx = normalizedHeaders.findIndex(h => phoneKeywords.some(pk => h === pk || h.includes(pk)));
    nameIdx = normalizedHeaders.findIndex(h => nameKeywords.some(nk => h === nk || (h.includes(nk) && !phoneKeywords.some(pk => h.includes(pk)))));
    
    botMsgIdx = normalizedHeaders.findIndex(h => 
      h === 'initial_bot_message' || h === 'bot_message' || h === 'message' || h === 'greeting'
    );
    stateIdx = normalizedHeaders.findIndex(h => 
      h === 'initial_state_name' || h === 'state_name' || h === 'state'
    );
    langIdx = normalizedHeaders.findIndex(h => 
      h === 'initial_language_name' || h === 'language_name' || h === 'language' || h === 'lang'
    );
  }

  const dataRows = isFirstRowHeader ? parsedRows.slice(1) : parsedRows;
  const colCount = Math.max(...parsedRows.map(r => r.length), 1);

  // Column Value Scoring: Analyze sample of data rows to discover which column actually holds phone & name
  const phoneScores = new Array(colCount).fill(0);
  const nameScores = new Array(colCount).fill(0);
  const sampleLimit = Math.min(dataRows.length, 25);

  for (let i = 0; i < sampleLimit; i++) {
    const row = dataRows[i];
    for (let c = 0; c < row.length; c++) {
      const cell = String(row[c] || '').trim();
      const digits = sanitizePhoneNumber(cell);
      if (isValidIndianMobile(digits).isValid) {
        phoneScores[c]++;
      } else if (/[a-zA-Z\u0900-\u097F]{2,}/.test(cell) && !cell.toLowerCase().includes('http')) {
        nameScores[c]++;
      }
    }
  }

  // Find column with highest phone score
  let maxPhoneScore = 0;
  let bestPhoneCol = -1;
  for (let c = 0; c < colCount; c++) {
    if (phoneScores[c] > maxPhoneScore) {
      maxPhoneScore = phoneScores[c];
      bestPhoneCol = c;
    }
  }

  if (bestPhoneCol !== -1 && (phoneIdx === -1 || phoneScores[bestPhoneCol] > (phoneScores[phoneIdx] || 0))) {
    phoneIdx = bestPhoneCol;
  }

  // Find column with highest name score that isn't the phone column
  let maxNameScore = 0;
  let bestNameCol = -1;
  for (let c = 0; c < colCount; c++) {
    if (c !== phoneIdx && nameScores[c] > maxNameScore) {
      maxNameScore = nameScores[c];
      bestNameCol = c;
    }
  }

  if (bestNameCol !== -1 && (nameIdx === -1 || nameIdx === phoneIdx || nameScores[bestNameCol] > (nameScores[nameIdx] || 0))) {
    nameIdx = bestNameCol;
  }

  // Fallbacks if still not determined
  if (phoneIdx === -1) phoneIdx = 0;
  if (nameIdx === -1) nameIdx = phoneIdx === 0 ? (colCount > 1 ? 1 : -1) : 0;

  const errors: string[] = [];
  const warnings: string[] = [];

  if (!isFirstRowHeader) {
    warnings.push('Header row was absent. Column types were automatically detected from row content.');
  }

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

    // 2. Check for interchanged Name and Phone in this row
    let cleanPhone = sanitizePhoneNumber(rawPhone);
    let isPhoneValid = isValidIndianMobile(cleanPhone).isValid;

    let cleanNameAsPhone = sanitizePhoneNumber(rawName);
    let isNameValidPhone = isValidIndianMobile(cleanNameAsPhone).isValid;

    if (!isPhoneValid && isNameValidPhone) {
      // Swapped columns in this row!
      const temp = rawPhone;
      rawPhone = rawName;
      rawName = temp;
      cleanPhone = cleanNameAsPhone;
      isPhoneValid = true;
      fixedCount++;
    }

    // 3. Dynamic row-level cell scanning: If still not a valid phone, scan ALL cells in the row!
    if (!isPhoneValid) {
      for (let c = 0; c < row.length; c++) {
        const cellValue = String(row[c] || '').trim();
        const cellDigits = sanitizePhoneNumber(cellValue);
        if (isValidIndianMobile(cellDigits).isValid) {
          cleanPhone = cellDigits;
          rawPhone = cellValue;
          isPhoneValid = true;

          // If current candidate name is digits or empty, search for a cell with text
          if (!rawName || /^\d+$/.test(rawName.replace(/\D/g, ''))) {
            for (let nc = 0; nc < row.length; nc++) {
              if (nc !== c) {
                const textVal = String(row[nc] || '').trim();
                if (/[a-zA-Z\u0900-\u097F]{2,}/.test(textVal) && !textVal.toLowerCase().includes('http')) {
                  rawName = textVal;
                  break;
                }
              }
            }
          }
          fixedCount++;
          break;
        }
      }
    }

    const phoneCheck = isValidIndianMobile(cleanPhone);

    // 4. Strict filter: If invalid or missing phone anywhere in row, SKIP and do not try this number
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

    // 5. Duplicate prevention: Skip if number was already seen in this batch
    if (seenPhoneNumbers.has(cleanPhone)) {
      duplicateCount++;
      skippedDetails.push({
        rowNumber: rowNum,
        rawPhone,
        rawName,
        reason: 'Duplicate phone number in sheet (already queued)'
      });
      warnings.push(`Row ${rowNum}: Skipped duplicate phone '+91 ${cleanPhone}'.`);
      continue;
    }

    seenPhoneNumbers.add(cleanPhone);

    // Clean customer name or provide polite fallback if missing
    let cleanName = rawName.replace(/^[.,_\-'"\s]+|[.,_\-'"\s]+$/g, '').trim();
    if (!cleanName || ['n/a', 'na', 'null', 'none', 'undefined', '-', '--', 'nil'].includes(cleanName.toLowerCase())) {
      cleanName = `Buyer ${cleanPhone.slice(-4)}`;
      fixedCount++;
    }

    if (cleanPhone !== rawPhone.trim()) {
      fixedCount++;
    } else {
      validCount++;
    }

    cleanedData.push({
      phone_number: cleanPhone,
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
