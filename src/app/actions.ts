'use server';

import { getDb, saveDb } from '@/lib/db';
import { Lead, Campaign, ClassifiedEmail, EmailFilterRule, Ticket, Invoice, TicketMessage, ImapConfig, CallLog, Meeting } from '@/lib/types';
import { revalidatePath } from 'next/cache';
import { ImapFlow } from 'imapflow';
import { simpleParser } from 'mailparser';

// --- LEADS ACTIONS ---
export async function getLeads(): Promise<Lead[]> {
  const db = getDb();
  return db.leads.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function saveLead(lead: Lead): Promise<Lead> {
  const db = getDb();
  const index = db.leads.findIndex(l => l.id === lead.id);
  
  if (index >= 0) {
    db.leads[index] = lead;
  } else {
    db.leads.push(lead);
  }
  
  saveDb(db);
  revalidatePath('/');
  revalidatePath('/sales/crm');
  revalidatePath('/dashboard/cold-calling');
  return lead;
}

export async function deleteLead(id: string): Promise<boolean> {
  const db = getDb();
  const initialLength = db.leads.length;
  db.leads = db.leads.filter(l => l.id !== id);
  
  if (db.leads.length < initialLength) {
    saveDb(db);
    revalidatePath('/');
    revalidatePath('/sales/crm');
    revalidatePath('/dashboard/cold-calling');
    return true;
  }
  return false;
}

export async function bulkImportLeads(leadsInput: Omit<Lead, 'id' | 'createdAt'>[]): Promise<{ imported: number; skipped: number }> {
  const db = getDb();
  let imported = 0;
  let skipped = 0;

  for (const input of leadsInput) {
    // Prevent duplicate leads by phone number
    const exists = db.leads.some(l => l.phone.replace(/\D/g, '') === input.phone.replace(/\D/g, ''));
    if (exists) {
      skipped++;
      continue;
    }

    const newLead: Lead = {
      id: `lead-${Math.random().toString(36).substr(2, 9)}`,
      name: input.name,
      phone: input.phone,
      email: input.email || undefined,
      company: input.company || undefined,
      status: 'queued',
      notes: input.notes || 'Bulk imported from CSV file.',
      createdAt: new Date().toISOString()
    };

    db.leads.push(newLead);
    imported++;
  }

  if (imported > 0) {
    saveDb(db);
  }

  revalidatePath('/sales/crm');
  revalidatePath('/dashboard/cold-calling');
  revalidatePath('/');
  return { imported, skipped };
}

// --- CAMPAIGNS ACTIONS ---
export async function getCampaigns(): Promise<Campaign[]> {
  const db = getDb();
  return db.campaigns;
}

export async function saveCampaign(campaign: Campaign): Promise<Campaign> {
  const db = getDb();
  const index = db.campaigns.findIndex(c => c.id === campaign.id);
  
  if (index >= 0) {
    db.campaigns[index] = campaign;
  } else {
    db.campaigns.push(campaign);
  }
  
  saveDb(db);
  revalidatePath('/sales/campaigns');
  return campaign;
}

// --- EMAILS ACTIONS ---
export async function getEmails(): Promise<ClassifiedEmail[]> {
  const db = getDb();
  return db.emails.sort((a, b) => new Date(b.receivedAt).getTime() - new Date(a.receivedAt).getTime());
}

export async function getEmailRules(): Promise<EmailFilterRule[]> {
  const db = getDb();
  return db.emailRules;
}

export async function saveEmailRules(rules: EmailFilterRule[]): Promise<EmailFilterRule[]> {
  const db = getDb();
  db.emailRules = rules;
  saveDb(db);
  
  // Re-classify existing emails when rules are updated
  reclassifyAllEmails(db);
  
  revalidatePath('/productivity/emails');
  return rules;
}

function reclassifyAllEmails(db: any) {
  db.emails = db.emails.map((email: ClassifiedEmail) => {
    let finalCategory: 'Urgent' | 'VC' | 'Other' | 'Spam' | 'Trash' = 'Other';
    const textToSearch = `${email.subject} ${email.body}`.toLowerCase();
    
    // Evaluate rules
    for (const rule of db.emailRules) {
      const match = rule.keywords.some((kw: string) => textToSearch.includes(kw.toLowerCase()));
      if (match) {
        finalCategory = rule.category;
        break; // Stop at first matching rule category
      }
    }
    
    // Generate actionable links if VC or Urgent
    let actionableLink = email.actionableLink;
    if (finalCategory === 'VC' && !actionableLink) {
      actionableLink = 'https://calendly.com/founder/meeting';
    } else if (finalCategory === 'Urgent' && !actionableLink) {
      actionableLink = 'https://console.aws.amazon.com';
    }
    
    return {
      ...email,
      category: finalCategory,
      actionableLink
    };
  });
  saveDb(db);
}

export async function createEmail(emailInput: { sender: string; subject: string; body: string }): Promise<ClassifiedEmail> {
  const db = getDb();
  const textToSearch = `${emailInput.subject} ${emailInput.body}`.toLowerCase();
  
  let category: 'Urgent' | 'VC' | 'Other' | 'Spam' | 'Trash' = 'Other';
  for (const rule of db.emailRules) {
    const match = rule.keywords.some((kw: string) => textToSearch.includes(kw.toLowerCase()));
    if (match) {
      category = rule.category;
      break;
    }
  }

  let actionableLink: string | undefined;
  if (category === 'VC') {
    actionableLink = 'https://calendly.com/founder/pitch-meeting';
  } else if (category === 'Urgent') {
    actionableLink = 'https://dashboard.stripe.com';
  }

  const newEmail: ClassifiedEmail = {
    id: `email-${Math.random().toString(36).substr(2, 9)}`,
    ...emailInput,
    category,
    actionableLink,
    receivedAt: new Date().toISOString()
  };

  db.emails.push(newEmail);
  saveDb(db);
  revalidatePath('/');
  revalidatePath('/productivity/emails');
  return newEmail;
}

export async function deleteEmail(id: string): Promise<boolean> {
  const db = getDb();
  const index = db.emails.findIndex(e => e.id === id);
  if (index >= 0) {
    // Soft delete rule: if they delete from Trash, it is permanent. Otherwise, move to Trash
    const email = db.emails[index];
    if (email.category === 'Trash' || email.category === 'Spam') {
      db.emails = db.emails.filter(e => e.id !== id);
    } else {
      db.emails[index].category = 'Trash';
    }
    saveDb(db);
    revalidatePath('/productivity/emails');
    return true;
  }
  return false;
}

export async function purgeTrashEmails(): Promise<number> {
  const db = getDb();
  const initialCount = db.emails.length;
  db.emails = db.emails.filter(e => e.category !== 'Trash' && e.category !== 'Spam');
  const deletedCount = initialCount - db.emails.length;
  if (deletedCount > 0) {
    saveDb(db);
    revalidatePath('/productivity/emails');
  }
  return deletedCount;
}

// --- TICKETS ACTIONS ---
export async function getTickets(): Promise<Ticket[]> {
  const db = getDb();
  return db.tickets.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function getTicketById(id: string): Promise<Ticket | null> {
  const db = getDb();
  return db.tickets.find(t => t.id === id || t.id.toLowerCase() === id.toLowerCase()) || null;
}

export async function saveTicket(ticket: Ticket): Promise<Ticket> {
  const db = getDb();
  const index = db.tickets.findIndex(t => t.id === ticket.id);
  
  if (index >= 0) {
    db.tickets[index] = ticket;
  } else {
    db.tickets.push(ticket);
  }
  
  saveDb(db);
  revalidatePath('/support/tickets');
  return ticket;
}

export async function createTicket(ticketInput: { customerName: string; customerEmail: string; issueDescription: string; chatbotHistory: TicketMessage[] }): Promise<Ticket> {
  const db = getDb();
  const ticketCount = db.tickets.length;
  const ticketId = `TCK-${1001 + ticketCount}`;
  
  const newTicket: Ticket = {
    id: ticketId,
    customerName: ticketInput.customerName,
    customerEmail: ticketInput.customerEmail,
    issueDescription: ticketInput.issueDescription,
    chatbotHistory: ticketInput.chatbotHistory,
    status: 'Pending',
    createdAt: new Date().toISOString()
  };
  
  db.tickets.push(newTicket);
  saveDb(db);
  
  // Simulate Webhook / Notification to human support channel
  console.log(`[SLACK WEBHOOK ALERT] New Ticket Raised: ${ticketId} - ${ticketInput.customerName}: ${ticketInput.issueDescription}`);
  
  revalidatePath('/support/tickets');
  return newTicket;
}

// --- INVOICES ACTIONS ---
export async function getInvoices(): Promise<Invoice[]> {
  const db = getDb();
  return db.invoices.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function saveInvoice(invoice: Invoice): Promise<Invoice> {
  const db = getDb();
  const index = db.invoices.findIndex(i => i.id === invoice.id);
  
  if (index >= 0) {
    db.invoices[index] = invoice;
  } else {
    db.invoices.push(invoice);
  }
  
  saveDb(db);
  revalidatePath('/');
  revalidatePath('/productivity/invoices');
  return invoice;
}

// --- IMAP ACTIONS ---
export async function getImapConfig(): Promise<ImapConfig | null> {
  const db = getDb();
  return db.imapConfig || null;
}

export async function saveImapConfig(config: ImapConfig): Promise<ImapConfig> {
  const db = getDb();
  db.imapConfig = config;
  saveDb(db);
  return config;
}

export async function syncRealEmails(): Promise<{ success: boolean; newCount: number; error?: string }> {
  const db = getDb();
  const config = db.imapConfig;
  
  if (!config) {
    return { 
      success: false, 
      newCount: 0, 
      error: 'IMAP connection details are missing. Please configure your settings in the configuration panel.' 
    };
  }

  const client = new ImapFlow({
    host: config.host,
    port: config.port,
    secure: config.secure,
    auth: {
      user: config.user,
      pass: config.pass
    },
    logger: false,
    connectionTimeout: 15000
  });

  try {
    await client.connect();
  } catch (e: any) {
    console.error("IMAP Connection Error:", e);
    return { 
      success: false, 
      newCount: 0, 
      error: `Failed to connect to IMAP server: ${e.message || e}` 
    };
  }

  let newCount = 0;
  
  try {
    // Select folder and get lock
    const lock = await client.getMailboxLock('INBOX');
    
    try {
      // Find unread emails (unseen messages)
      const messages = await client.search({ seen: false });
      
      if (messages && messages.length > 0) {
        // Limit sync to latest 10 messages to avoid timeouts during demos
        const targetUids = messages.slice(-10);
        
        for (const uid of targetUids) {
          const rawMessage = await client.fetchOne(uid, { source: true });
          if (!rawMessage || !rawMessage.source) continue;
          
          const parsed = await simpleParser(rawMessage.source);
          
          const sender = parsed.from?.text || parsed.from?.value?.[0]?.address || 'Unknown Sender';
          const subject = parsed.subject || '(No Subject)';
          const body = parsed.text || parsed.html || '';
          const date = parsed.date ? parsed.date.toISOString() : new Date().toISOString();
          
          // Check for duplication
          const exists = db.emails.some(e => 
            e.sender === sender && 
            e.subject === subject && 
            Math.abs(new Date(e.receivedAt).getTime() - new Date(date).getTime()) < 60000
          );
          
          if (exists) continue;
          
          // Classify email based on rule keywords
          const textToSearch = `${subject} ${body}`.toLowerCase();
          let category: 'Urgent' | 'VC' | 'Other' | 'Spam' | 'Trash' = 'Other';
          
          for (const rule of db.emailRules) {
            const match = rule.keywords.some((kw: string) => textToSearch.includes(kw.toLowerCase()));
            if (match) {
              category = rule.category;
              break;
            }
          }
          
          let actionableLink: string | undefined;
          if (category === 'VC') {
            actionableLink = 'https://calendly.com/founder/pitch-meeting';
          } else if (category === 'Urgent') {
            actionableLink = 'https://console.aws.amazon.com';
          }
          
          db.emails.push({
            id: `email-${Math.random().toString(36).substr(2, 9)}`,
            sender,
            subject,
            body,
            category,
            actionableLink,
            receivedAt: date
          });
          
          newCount++;
        }
        
        if (newCount > 0) {
          saveDb(db);
        }
      }
    } finally {
      lock.release();
    }
  } catch (e: any) {
    console.error("IMAP sync processing error:", e);
    return { 
      success: false, 
      newCount: 0, 
      error: `Failed during sync processing: ${e.message || e}` 
    };
  } finally {
    await client.logout();
  }
  
  revalidatePath('/');
  revalidatePath('/productivity/emails');
  return { success: true, newCount };
}

// --- AUTOMATED AI COLD CALLING & OUTBOUND DIALER ACTIONS ---

export async function getCallLogsWithLeads(): Promise<(CallLog & { leadName: string; leadCompany?: string })[]> {
  const db = getDb();
  return db.callLogs.map(log => {
    const lead = db.leads.find(l => l.id === log.leadId);
    return {
      ...log,
      leadName: lead ? lead.name : 'Unknown Customer',
      leadCompany: lead?.company
    };
  }).sort((a, b) => new Date(b.calledAt).getTime() - new Date(a.calledAt).getTime());
}

export async function getMeetingsWithLeads(): Promise<(Meeting & { leadName: string; leadEmail?: string; leadCompany?: string })[]> {
  const db = getDb();
  return db.meetings.map(meet => {
    const lead = db.leads.find(l => l.id === meet.leadId);
    return {
      ...meet,
      leadName: lead ? lead.name : 'Unknown Lead',
      leadEmail: lead?.email,
      leadCompany: lead?.company
    };
  }).sort((a, b) => new Date(a.scheduledTime).getTime() - new Date(b.scheduledTime).getTime());
}

export async function getColdCallingStats() {
  const db = getDb();
  const totalLeads = db.leads.length;
  
  // Total completed calls: unique records in call_logs
  const completedCalls = db.callLogs.length;
  
  // Scheduled meetings: entries in meetings
  const meetingsScheduled = db.meetings.filter(m => m.status === 'confirmed').length;
  
  // Conversion rate: percent of leads called that converted to meeting_scheduled or interested
  // Out of those called:
  const calledLeadIds = new Set(db.callLogs.map(log => log.leadId));
  const interestedOrScheduledCount = db.leads.filter(l => 
    calledLeadIds.has(l.id) && (l.status === 'interested' || l.status === 'meeting_scheduled')
  ).length;
  
  const conversionRate = calledLeadIds.size > 0 
    ? Math.round((interestedOrScheduledCount / calledLeadIds.size) * 100) 
    : 0;

  return {
    totalLeads,
    completedCalls,
    conversionRate,
    meetingsScheduled
  };
}

export async function triggerAIOutboundCampaign(leadIds: string[], agentPrompt: string): Promise<{ dispatchedCount: number; error?: string }> {
  const db = getDb();
  let dispatchedCount = 0;

  // 1. Move leads to 'calling' status in the local DB
  db.leads = db.leads.map(lead => {
    if (leadIds.includes(lead.id)) {
      dispatchedCount++;
      return {
        ...lead,
        status: 'calling',
        notes: `${lead.notes || ''}\n\n[Dialer Campaign Triggered on ${new Date().toLocaleString()}]: Voice agent campaign initiated with customized prompt instructions.`
      };
    }
    return lead;
  });

  saveDb(db);
  revalidatePath('/dashboard/cold-calling');
  revalidatePath('/sales/crm');

  // 2. REST API Vapi/Retell Trigger Simulation
  // In production, this reads VAPI_API_KEY from env and executes POST calls.
  const isProdConfigured = !!process.env.VAPI_API_KEY;
  
  if (isProdConfigured) {
    console.log(`[VAPI INTEGRATION TRIGGER]: Start batch campaign dispatch for ${leadIds.length} lead IDs.`);
    // Execute calls sequentially or concurrently using fetch
    for (const leadId of leadIds) {
      const lead = db.leads.find(l => l.id === leadId);
      if (!lead) continue;
      
      try {
        const response = await fetch('https://api.vapi.ai/call/phone', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${process.env.VAPI_API_KEY}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            phoneNumberId: process.env.VAPI_PHONE_NUMBER_ID,
            customer: {
              number: lead.phone,
              name: lead.name
            },
            assistant: {
              transcriptionProvider: { provider: 'deepgram' },
              model: { provider: 'openai', model: 'gpt-4', messages: [{ role: 'system', content: agentPrompt }] }
            },
            webhookUrl: `${process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'}/api/webhooks/voice-agent`
          })
        });
        
        if (!response.ok) {
          console.error(`[Vapi HTTP Error for lead ${leadId}]:`, await response.text());
        }
      } catch (err) {
        console.error(`[Vapi Network Exception for lead ${leadId}]:`, err);
      }
    }
  } else {
    // Sandbox simulator fallback logging
    console.log(`[AI DIALER SANDBOX MODE]: Dispatching calls to Vapi.ai API endpoints without live keys...`);
    console.log(`[Custom Agent Instructions]: ${agentPrompt}`);
    
    // Simulate campaign dialer delays in background logs
    leadIds.forEach(id => {
      const target = db.leads.find(l => l.id === id);
      if (target) {
        console.log(`[CAMPAIGN QUEUE DIALER]: Initiated mock outbound call sequence to phone: ${target.phone} (${target.name})`);
      }
    });
  }

  return { dispatchedCount };
}

// --- LIVEKIT + GEMINI LIVE + VOBIZ AUTOMATIC OUTBOUND CALL ACTION (100% NATIVE NODE.JS) ---
import { SipClient } from 'livekit-server-sdk';

export async function triggerLiveKitOutboundCall(phoneNumber: string, customerName: string, company: string = ""): Promise<{ success: boolean; message: string; output?: string }> {
  try {
    const rawEnvUrl = process.env.LIVEKIT_URL || 'cold-calling-j7qhnkas.livekit.cloud';
    const cleanHost = rawEnvUrl
      .replace(/^[a-zA-Z]+:\/\//, '') // strip any protocol (wss://, ws://, https://, http://)
      .replace(/\/+$/, '')            // strip trailing slashes
      .trim()
      .replace(/['"]/g, '');

    const httpUrl = `https://${cleanHost || 'cold-calling-j7qhnkas.livekit.cloud'}`;
    const apiKey = (process.env.LIVEKIT_API_KEY || 'APIAkEXqBNfS2LP').trim().replace(/['"]/g, '');
    const apiSecret = (process.env.LIVEKIT_API_SECRET || 'dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT').trim().replace(/['"]/g, '');
    const trunkId = (process.env.SIP_OUTBOUND_TRUNK_ID || 'ST_TEGVYguUkfe9').trim().replace(/['"]/g, '');

    const sipClient = new SipClient(httpUrl, apiKey, apiSecret);

    const safePhone = phoneNumber.replace(/[^0-9+]/g, '');
    const cleanId = safePhone.replace('+', '');
    const uniqueRoom = `call-${customerName.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Math.random().toString(36).substring(2, 10)}`;

    const metadata = JSON.stringify({
      customer_name: customerName,
      phone_number: safePhone,
      company: company || 'Client'
    });

    console.log(`[LIVEKIT NODE SDK TRIGGER]: Dialing ${safePhone} in room ${uniqueRoom} with Trunk ${trunkId}`);

    const participant = await sipClient.createSipParticipant(
      trunkId,
      safePhone,
      uniqueRoom,
      {
        participantIdentity: `sip-${cleanId}`,
        participantName: customerName,
        participantMetadata: metadata,
        playRingtone: true,
        hidePhoneNumber: false,
        waitUntilAnswered: true,
      }
    );

    console.log(`[LIVEKIT NODE SDK SUCCESS]: Participant created:`, participant);

    return {
      success: true,
      message: `Outbound SIP call successfully dispatched to ${safePhone}! Phone is ringing now.`,
      output: `Room: ${uniqueRoom}`
    };
  } catch (error: any) {
    console.error(`[LIVEKIT NODE SDK ERROR]:`, error);
    return {
      success: false,
      message: error?.message || 'Failed to dispatch outbound SIP call via LiveKit.',
      output: error?.stack || String(error)
    };
  }
}

