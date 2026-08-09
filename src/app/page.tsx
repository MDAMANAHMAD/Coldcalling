'use client';

import { useState, useEffect } from 'react';
import { getLeads, getEmails, getTickets, getInvoices } from '@/app/actions';
import { Lead, ClassifiedEmail, Ticket, Invoice } from '@/lib/types';
import { 
  PhoneCall, 
  Mail, 
  Ticket as TicketIcon, 
  FileText, 
  ArrowUpRight, 
  UserCheck, 
  TrendingUp, 
  Clock, 
  ChevronRight,
  ExternalLink,
  Plus,
  Compass,
  AlertTriangle,
  Calendar
} from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

export default function DashboardOverview() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [emails, setEmails] = useState<ClassifiedEmail[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const leadList = await getLeads();
        const emailList = await getEmails();
        const ticketList = await getTickets();
        const invoiceList = await getInvoices();
        
        setLeads(leadList);
        setEmails(emailList);
        setTickets(ticketList);
        setInvoices(invoiceList);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // Filter urgent / VC emails
  const priorityEmails = emails.filter(e => e.category === 'Urgent' || e.category === 'VC').slice(0, 3);
  
  const pendingCallbacks = leads.filter(l => {
    if (!l.followUpDate || l.status !== 'callback_required') return false;
    const today = new Date().toDateString();
    const followDate = new Date(l.followUpDate).toDateString();
    return today === followDate;
  }).slice(0, 3);

  // Filter pending support tickets
  const activeTickets = tickets.filter(t => t.status === 'Pending' || t.status === 'In Progress').slice(0, 3);

  // Calculated totals
  const totalLeads = leads.length;
  const pipelineValue = invoices.reduce((sum, inv) => sum + (inv.status === 'Paid' ? 0 : inv.total), 0);
  const ticketsCount = tickets.filter(t => t.status !== 'Resolved').length;

  return (
    <div className="space-y-8">
      {/* Welcome Banner */}
      <div className="p-6 rounded-3xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-xl shadow-blue-500/10 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black leading-tight">Welcome Back, Tony</h2>
          <p className="text-xs text-blue-100 mt-1 font-medium">Your automated business operations CRM is active. Here is your operational agenda today.</p>
        </div>
        <div className="flex space-x-3">
          <Link
            href="/client-portal"
            target="_blank"
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-xs font-semibold border border-white/20 transition-all"
          >
            Client Facing Chatbot Portal
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        
        {/* CRM Pipeline */}
        <div className="p-5 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex justify-between items-center">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">CRM Lead Pipeline</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-white mt-1.5">{totalLeads} Leads</h3>
            <span className="text-[10px] text-emerald-500 dark:text-emerald-450 font-bold flex items-center mt-1">
              <TrendingUp className="h-3.5 w-3.5 mr-0.5" />
              +15% week-over-week
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            <PhoneCall className="h-6 w-6" />
          </div>
        </div>

        {/* AI Inbox */}
        <div className="p-5 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex justify-between items-center">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Urgent AI Mails</p>
            <h3 className="text-2xl font-black text-rose-600 dark:text-rose-450 mt-1.5">
              {emails.filter(e => e.category === 'Urgent').length} Pending
            </h3>
            <span className="text-[10px] text-slate-400 font-semibold flex items-center mt-1">
              Auto-purged Trash: active
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center">
            <Mail className="h-6 w-6" />
          </div>
        </div>

        {/* Helpdesk */}
        <div className="p-5 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex justify-between items-center">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Unresolved Support</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-white mt-1.5">{ticketsCount} Tickets</h3>
            <span className="text-[10px] text-slate-400 font-semibold flex items-center mt-1">
              Average response: 4.2m
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center">
            <TicketIcon className="h-6 w-6" />
          </div>
        </div>

        {/* Unpaid Invoices / Revenue */}
        <div className="p-5 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex justify-between items-center">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Accounts Receivable</p>
            <h3 className="text-2xl font-black text-amber-600 dark:text-amber-450 mt-1.5">${pipelineValue.toLocaleString()}</h3>
            <span className="text-[10px] text-slate-400 font-semibold flex items-center mt-1">
              Total invoiced: ${invoices.reduce((sum, inv) => sum + inv.total, 0).toLocaleString()}
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
            <FileText className="h-6 w-6" />
          </div>
        </div>

      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* COLUMN 1: Daily Action Items (lg:col-span-8) */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* CRM Callback Queue */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-extrabold text-base text-slate-800 dark:text-white flex items-center">
                <PhoneCall className="h-5 w-5 mr-2 text-blue-500" />
                CRM Daily Callback Queue
              </h3>
              <Link href="/sales/crm" className="text-xs text-blue-600 dark:text-blue-400 font-bold flex items-center hover:underline">
                View CRM Pipeline
                <ChevronRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-850">
              {loading ? (
                <p className="text-slate-400 text-xs py-4 text-center">Loading queue...</p>
              ) : pendingCallbacks.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-400 space-y-1">
                  <p>No cold-calling callbacks scheduled for today.</p>
                  <p className="text-[10px] text-slate-450">Add follow-up dates in the CRM dashboard to populate this queue.</p>
                </div>
              ) : (
                pendingCallbacks.map((lead) => (
                  <div key={lead.id} className="py-3 flex justify-between items-center gap-4">
                    <div>
                      <h4 className="font-bold text-xs text-slate-800 dark:text-white">{lead.name}</h4>
                      <p className="text-[10px] text-slate-400 mt-0.5">{lead.phone || lead.email}</p>
                    </div>
                    
                    <div className="flex items-center space-x-2 text-[10px] text-amber-600 font-semibold bg-amber-50 dark:bg-amber-950/20 px-2 py-1 rounded-lg">
                      <Calendar className="h-3.5 w-3.5 mr-0.5" />
                      <span>{lead.followUpDate ? new Date(lead.followUpDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Today'}</span>
                    </div>

                    <Link
                      href="/sales/crm"
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-[10px]"
                    >
                      Call Lead
                    </Link>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* AI Email Classifier Priority Peeks */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-extrabold text-base text-slate-800 dark:text-white flex items-center">
                <Mail className="h-5 w-5 mr-2 text-indigo-500" />
                Founder AI Priority Inbox
              </h3>
              <Link href="/productivity/emails" className="text-xs text-blue-600 dark:text-blue-400 font-bold flex items-center hover:underline">
                View Smart Inbox
                <ChevronRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-850">
              {loading ? (
                <p className="text-slate-400 text-xs py-4 text-center">Loading email stream...</p>
              ) : priorityEmails.length === 0 ? (
                <p className="py-6 text-center text-xs text-slate-400">No high-priority (Urgent or VC) emails found today.</p>
              ) : (
                priorityEmails.map((email) => (
                  <div key={email.id} className="py-3.5 flex justify-between items-start gap-4">
                    <div className="space-y-1 max-w-[70%]">
                      <div className="flex items-center space-x-2">
                        <span className={`text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded ${
                          email.category === 'Urgent' 
                            ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/20 dark:text-rose-450' 
                            : 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/20 dark:text-indigo-400'
                        }`}>
                          {email.category}
                        </span>
                        <h4 className="font-bold text-xs text-slate-855 dark:text-white truncate" title={email.subject}>
                          {email.subject}
                        </h4>
                      </div>
                      <p className="text-[10px] text-slate-400 truncate">{email.sender}</p>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 line-clamp-1 italic">"{email.body}"</p>
                    </div>

                    {email.actionableLink && (
                      <a
                        href={email.actionableLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center space-x-1 text-[10px] text-blue-600 dark:text-blue-400 font-bold hover:underline py-1.5"
                      >
                        <span>Action</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

        </div>

        {/* COLUMN 2: Shortcuts & Support Consoles (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Quick Shortcuts */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm space-y-4">
            <h3 className="font-extrabold text-base text-slate-800 dark:text-white flex items-center">
              <Compass className="h-5 w-5 mr-2 text-amber-500" />
              Founder Actions
            </h3>
            
            <div className="grid grid-cols-2 gap-3 text-center">
              <Link
                href="/sales/crm"
                className="p-3 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center group hover:border-blue-500/50 transition-all duration-200"
              >
                <Plus className="h-5 w-5 text-blue-500 group-hover:scale-110 transition-transform" />
                <span className="text-[10px] font-bold text-slate-600 dark:text-slate-450 mt-1.5">New CRM Lead</span>
              </Link>

              <Link
                href="/sales/campaigns"
                className="p-3 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center group hover:border-indigo-500/50 transition-all duration-200"
              >
                <Plus className="h-5 w-5 text-indigo-500 group-hover:scale-110 transition-transform" />
                <span className="text-[10px] font-bold text-slate-600 dark:text-slate-450 mt-1.5">New Campaign</span>
              </Link>

              <Link
                href="/productivity/invoices"
                className="p-3 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center group hover:border-amber-500/50 transition-all duration-200"
              >
                <Plus className="h-5 w-5 text-amber-500 group-hover:scale-110 transition-transform" />
                <span className="text-[10px] font-bold text-slate-600 dark:text-slate-450 mt-1.5">New Invoice</span>
              </Link>

              <Link
                href="/client-portal"
                target="_blank"
                className="p-3 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center group hover:border-rose-500/50 transition-all duration-200"
              >
                <ArrowUpRight className="h-5 w-5 text-rose-500 group-hover:scale-110 transition-transform" />
                <span className="text-[10px] font-bold text-slate-600 dark:text-slate-450 mt-1.5">Client Help Portal</span>
              </Link>
            </div>
          </div>

          {/* Active Support Tickets */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-extrabold text-base text-slate-800 dark:text-white flex items-center">
                <TicketIcon className="h-5 w-5 mr-2 text-purple-500" />
                Helpdesk Tickets
              </h3>
              <Link href="/support/tickets" className="text-xs text-blue-600 dark:text-blue-400 font-bold flex items-center hover:underline">
                Console
                <ChevronRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-850">
              {loading ? (
                <p className="text-slate-400 text-xs py-4 text-center">Loading ticket logs...</p>
              ) : activeTickets.length === 0 ? (
                <p className="py-6 text-center text-xs text-slate-400">All customer tickets resolved!</p>
              ) : (
                activeTickets.map((t) => (
                  <div key={t.id} className="py-2.5 flex justify-between items-center gap-3">
                    <div className="max-w-[70%]">
                      <div className="flex items-center space-x-1.5">
                        <span className="font-bold text-[10px] text-slate-800 dark:text-white">{t.id}</span>
                        <span className={`px-1 rounded text-[7px] font-black uppercase tracking-wide ${
                          t.status === 'In Progress' ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-450'
                        }`}>
                          {t.status}
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-500 truncate mt-1">{t.issueDescription}</p>
                    </div>

                    <Link
                      href="/support/tickets"
                      className="text-[10px] font-bold text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Resolve
                    </Link>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
