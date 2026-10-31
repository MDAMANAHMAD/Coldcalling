export interface SarvamCsvRow {
  phone_number: string;
  user_name: string;
  initial_bot_message?: string;
  initial_state_name?: string;
  initial_language_name?: string;
  [key: string]: any;
}

export interface CsvValidationResult {
  isValid: boolean;
  totalRows: number;
  validRows: number;
  fixedRows: number;
  invalidRows: number;
  errors: string[];
  warnings: string[];
  data: SarvamCsvRow[];
  originalHeaders: string[];
  cleanedCsvContent: string;
}

export interface SarvamCallRecord {
  id: string;
  interactionId?: string;
  customerName: string;
  customerPhone: string; // Stored in FULL unmasked format e.g. +919821361686
  callDate: string; // ISO string
  durationSeconds: number;
  status: 'completed' | 'ongoing' | 'failed' | 'no-answer' | 'busy' | 'scheduled';
  outcome: 'Interested' | 'Site Visit' | 'Not Interested' | 'Call Back' | 'Voicemail' | 'Other';
  bhkPreference?: '1 BHK' | '2 BHK' | 'Both' | 'None';
  siteVisitDay?: string;
  siteVisitTime?: string;
  budget?: string;
  transcript: string;
  recordingUrl?: string;
  summary: string;
  agentId: string;
  fromNumber: string;
}

export interface LiveCampaignProgress {
  campaignId: string;
  campaignName: string;
  totalContacts: number;
  completedCalls: number;
  remainingCalls: number;
  ongoingCalls: number;
  successfulCalls: number;
  failedCalls: number;
  interestedCount: number;
  siteVisitCount: number;
  startedAt: string;
  updatedAt: string;
  status: 'running' | 'paused' | 'completed' | 'idle';
  currentBatchFile?: string;
}

export interface SarvamAnalyticsSummary {
  totalCalls: number;
  totalDurationSeconds: number;
  avgDurationSeconds: number;
  connectionRate: number;
  interestedCount: number;
  interestedRate: number;
  siteVisitCount: number;
  siteVisitRate: number;
  notInterestedCount: number;
  oneBhkCount: number;
  twoBhkCount: number;
  dailyTrends: { date: string; calls: number; interested: number; siteVisits: number }[];
  hourlyDistribution: { hour: string; count: number }[];
}

export type TimeFilterPeriod = 'today' | 'yesterday' | 'last_7_days' | 'last_30_days' | 'all';
