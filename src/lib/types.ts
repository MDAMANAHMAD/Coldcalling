export interface Profile {
  id: string;
  fullName: string;
  email: string;
  role: 'founder' | 'sales_rep' | 'support_agent';
}

export interface Lead {
  id: string;
  name: string;
  phone: string;
  email?: string;
  company?: string;
  status: 'queued' | 'calling' | 'interested' | 'not_interested' | 'callback_required' | 'meeting_scheduled' | 'failed';
  notes?: string;
  lastCallAt?: string; // ISO string
  followUpDate?: string; // ISO string
  createdAt: string; // ISO string
}

export interface Campaign {
  id: string;
  name: string;
  template: string;
  sequenceRules: {
    delayDays: number;
    maxFollowUps: number;
  };
  status: 'active' | 'paused' | 'completed';
  createdAt: string;
  repliesCount: number;
  objectionsCount: number;
}

export interface ClassifiedEmail {
  id: string;
  sender: string;
  subject: string;
  body: string;
  category: 'Urgent' | 'VC' | 'Other' | 'Spam' | 'Trash';
  actionableLink?: string;
  receivedAt: string;
}

export interface EmailFilterRule {
  id: string;
  category: 'Urgent' | 'VC' | 'Spam' | 'Trash';
  keywords: string[];
}

export interface TicketMessage {
  sender: 'user' | 'bot' | 'agent';
  message: string;
  timestamp: string;
}

export interface Ticket {
  id: string; // #TCK-XXXX
  customerName: string;
  customerEmail: string;
  issueDescription: string;
  chatbotHistory: TicketMessage[];
  status: 'Pending' | 'In Progress' | 'Resolved';
  agentNotes?: string;
  createdAt: string;
}

export interface InvoiceItem {
  id: string;
  description: string;
  qty: number;
  unitPrice: number;
}

export interface Invoice {
  id: string;
  invoiceNumber: string;
  clientName: string;
  clientEmail: string;
  items: InvoiceItem[];
  taxRate: number;
  total: number;
  status: 'Unpaid' | 'Paid' | 'Overdue';
  createdAt: string;
}

export interface ImapConfig {
  host: string;
  port: number;
  user: string;
  pass: string;
  secure: boolean;
}

export interface CallLog {
  id: string;
  leadId: string;
  callSid: string;
  durationSeconds: number;
  recordingUrl?: string;
  transcript: string;
  aiSummary: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  calledAt: string;
}

export interface Meeting {
  id: string;
  leadId: string;
  googleMeetLink: string;
  scheduledTime: string; // ISO string
  status: 'confirmed' | 'rescheduled' | 'cancelled';
  createdAt: string;
}

export interface AppDatabase {
  leads: Lead[];
  campaigns: Campaign[];
  emails: ClassifiedEmail[];
  emailRules: EmailFilterRule[];
  tickets: Ticket[];
  invoices: Invoice[];
  imapConfig?: ImapConfig;
  callLogs: CallLog[];
  meetings: Meeting[];
}
