import fs from 'fs';
import path from 'path';
import { AppDatabase, Lead, Campaign, ClassifiedEmail, EmailFilterRule, Ticket, Invoice, CallLog, Meeting } from './types';

const DB_FILE = path.join(process.cwd(), 'db.json');

const INITIAL_DATA: AppDatabase = {
  leads: [
    {
      id: 'lead-1',
      name: 'Sarah Connor',
      phone: '+15550199',
      email: 'sconnor@cyberdyne.com',
      company: 'Cyberdyne Systems',
      status: 'callback_required',
      notes: 'Interested in the new automated defense software. Called on 08/01 - requested callback after hours.',
      createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'lead-2',
      name: 'Bruce Wayne',
      phone: '+15551939',
      email: 'bruce@waynecorp.com',
      company: 'Wayne Enterprises',
      status: 'queued',
      notes: 'Lead acquired from Gotham Tech Conference. Prepared for outreach campaign.',
      createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'lead-3',
      name: 'Tony Stark',
      phone: '+15553000',
      email: 'tony@starkindustries.com',
      company: 'Stark Industries',
      status: 'meeting_scheduled',
      notes: 'Demo completed. Scheduled technical deep-dive via Google Meet.',
      createdAt: new Date().toISOString()
    },
    {
      id: 'lead-4',
      name: 'Peter Parker',
      phone: '+15550482',
      email: 'peter@dailybugle.com',
      company: 'Daily Bugle',
      status: 'not_interested',
      notes: 'Freelance photographer. Spoke briefly - has no budget for automation software.',
      createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'lead-aman',
      name: 'Aman',
      phone: '+918693081506',
      email: 'aman@example.com',
      company: 'Aman Corp',
      status: 'queued',
      notes: 'Added via user request for cold-calling testing.',
      createdAt: new Date().toISOString()
    }
  ],
  campaigns: [
    {
      id: 'camp-1',
      name: 'Enterprise AI Suite Launch',
      template: 'Hi {{name}},\n\nI noticed Wayne Enterprises is scaling up its software automation. Our platform can cut cloud costs by 30%. Would you be open to a 10-minute demo this Thursday?\n\nBest,\nFounder',
      sequenceRules: {
        delayDays: 2,
        maxFollowUps: 3
      },
      status: 'active',
      createdAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      repliesCount: 24,
      objectionsCount: 8
    },
    {
      id: 'camp-2',
      name: 'Founder Outreach - Angel Round',
      template: 'Hey {{name}},\n\nI saw your investment in automation solutions. We are building an all-in-one business operations platform and just opened our pre-seed round. Would love to send over our deck.\n\nCheers,\nFounder',
      sequenceRules: {
        delayDays: 3,
        maxFollowUps: 4
      },
      status: 'paused',
      createdAt: new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString(),
      repliesCount: 15,
      objectionsCount: 3
    }
  ],
  emails: [
    {
      id: 'email-1',
      sender: 'alex@sequoiacapital.com',
      subject: 'Follow up on pre-seed deck',
      body: 'Hi, I reviewed your pitch deck and would love to schedule a 30 min chat this Thursday to discuss the traction. Let me know if you can make it.',
      category: 'VC',
      actionableLink: 'https://calendly.com/alex-sequoia/30min',
      receivedAt: new Date().toISOString()
    },
    {
      id: 'email-2',
      sender: 'server-alerts@aws.amazon.com',
      subject: 'CRITICAL: DB CPU usage at 98%',
      body: 'Your production database instance is experiencing high CPU load. Action is required immediately to prevent outage.',
      category: 'Urgent',
      actionableLink: 'https://console.aws.amazon.com/rds',
      receivedAt: new Date().toISOString()
    },
    {
      id: 'email-3',
      sender: 'spammer@win-lottery-now.club',
      subject: 'CONGRATULATIONS!!! You won $10,000,000 cash prize',
      body: 'Click here now to claim your cash reward. Offer expires in 2 hours!',
      category: 'Spam',
      receivedAt: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'email-4',
      sender: 'newsletter@hacker-news.com',
      subject: 'HN Digest: Show HN, Tech Trends and and Launch News',
      body: 'Here is your weekly digest of top stories from Hacker News...',
      category: 'Other',
      receivedAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString()
    }
  ],
  emailRules: [
    {
      id: 'rule-1',
      category: 'VC',
      keywords: ['pitch', 'deck', 'investment', 'funding', 'round', 'investor', 'seed', 'pre-seed', 'capital']
    },
    {
      id: 'rule-2',
      category: 'Urgent',
      keywords: ['urgent', 'critical', 'alert', 'db error', 'db down', 'action required', 'billing failed', 'emergency']
    },
    {
      id: 'rule-3',
      category: 'Spam',
      keywords: ['lottery', 'winner', 'cash prize', 'viagra', 'weight loss', 'rich quick', 'buy bitcoin', 'free money']
    }
  ],
  tickets: [
    {
      id: 'TCK-1001',
      customerName: 'Clark Kent',
      customerEmail: 'clark@dailyplanet.com',
      issueDescription: 'Unable to login to the support dashboard. Kept getting error 500.',
      chatbotHistory: [
        { sender: 'user', message: 'Hello, I cannot access my dashboard', timestamp: new Date(Date.now() - 3600000).toISOString() },
        { sender: 'bot', message: 'Hi! Have you tried clearing your cookies or resetting your password?', timestamp: new Date(Date.now() - 3500000).toISOString() },
        { sender: 'user', message: 'Yes, I did. I still get a Internal Server Error screen', timestamp: new Date(Date.now() - 3400000).toISOString() },
        { sender: 'bot', message: 'I see. Let me escalate this to our technical support team.', timestamp: new Date(Date.now() - 3300000).toISOString() }
      ],
      status: 'Pending',
      createdAt: new Date(Date.now() - 3600000).toISOString()
    },
    {
      id: 'TCK-1002',
      customerName: 'Lois Lane',
      customerEmail: 'lois@dailyplanet.com',
      issueDescription: 'Invoice pdf downloaded is blank for invoice #INV-2026-001.',
      chatbotHistory: [
        { sender: 'user', message: 'My invoice is blank when downloaded', timestamp: new Date(Date.now() - 7200000).toISOString() }
      ],
      status: 'In Progress',
      agentNotes: 'Looking into PDF generator font loading issues.',
      createdAt: new Date(Date.now() - 7200000).toISOString()
    }
  ],
  invoices: [
    {
      id: 'inv-1',
      invoiceNumber: 'INV-2026-001',
      clientName: 'Wayne Enterprises',
      clientEmail: 'billing@waynecorp.com',
      items: [
        { id: '1', description: 'Enterprise Software Subscription - Annual', qty: 1, unitPrice: 12000 },
        { id: '2', description: 'Custom Integration Consulting (Hours)', qty: 40, unitPrice: 150 }
      ],
      taxRate: 8,
      total: 19440,
      status: 'Paid',
      createdAt: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'inv-2',
      invoiceNumber: 'INV-2026-002',
      clientName: 'Stark Industries',
      clientEmail: 'accounts-payable@stark.com',
      items: [
        { id: '1', description: 'API Maintenance Support - Q3', qty: 1, unitPrice: 5000 }
      ],
      taxRate: 10,
      total: 5500,
      status: 'Unpaid',
      createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString()
    }
  ],
  callLogs: [
    {
      id: 'call-1',
      leadId: 'lead-3',
      callSid: 'call_vapi_123456789',
      durationSeconds: 142,
      recordingUrl: 'https://api.vapi.ai/recordings/call_vapi_123456789.mp3',
      transcript: 'Agent: Hi Tony, this is Antigravity outreach. I saw Stark Industries is deploying a new automation pipeline. Are you interested in reducing hosting overhead by 30%?\nTony Stark: Yes, that sounds interesting. We have some custom clusters. How do you handle integrations?\nAgent: We support custom IMAP rules and Supabase integrations out-of-the-box.\nTony Stark: Okay, I would like to schedule a deep-dive demo next Tuesday at 3 PM.\nAgent: Perfect! I am generating a Google Meet link for Tuesday at 3 PM and sending it to tony@starkindustries.com.',
      aiSummary: 'Tony Stark expressed interest in reducing Stark Industries hosting overhead. He scheduled a deep-dive technical demo for next Tuesday at 3:00 PM. Webhook successfully compiled Google Meet invite.',
      sentiment: 'positive',
      calledAt: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 'call-2',
      leadId: 'lead-4',
      callSid: 'call_vapi_987654321',
      durationSeconds: 45,
      recordingUrl: 'https://api.vapi.ai/recordings/call_vapi_987654321.mp3',
      transcript: 'Agent: Hi Peter, I am calling from Antigravity. We automate CRM callback tasks.\nPeter Parker: Hey, sorry, I am just a freelance photographer and college student. I don\'t run any company or have a sales pipeline. So not interested.\nAgent: I understand Peter, thanks for your time!',
      aiSummary: 'Peter Parker declined the offer. He stated he is a freelance photographer and student with no business pipeline or budget.',
      sentiment: 'negative',
      calledAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
    }
  ],
  meetings: [
    {
      id: 'meet-1',
      leadId: 'lead-3',
      googleMeetLink: 'https://meet.google.com/abc-defg-hij',
      scheduledTime: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days from now
      status: 'confirmed',
      createdAt: new Date().toISOString()
    }
  ]
};

export function getDb(): AppDatabase {
  if (!fs.existsSync(DB_FILE)) {
    saveDb(INITIAL_DATA);
    return INITIAL_DATA;
  }
  try {
    const raw = fs.readFileSync(DB_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    
    // Ensure new arrays exist in read data
    if (!parsed.callLogs) parsed.callLogs = [];
    if (!parsed.meetings) parsed.meetings = [];
    return parsed;
  } catch (e) {
    console.error("Error reading database file, resetting to initial data", e);
    saveDb(INITIAL_DATA);
    return INITIAL_DATA;
  }
}

export function saveDb(data: AppDatabase): void {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (e) {
    console.error("Error writing database file", e);
  }
}
