'use client';

import { useState, useEffect } from 'react';
import { getTickets, saveTicket } from '@/app/actions';
import { Ticket, TicketMessage } from '@/lib/types';
import { 
  Ticket as TicketIcon, 
  MessageCircle, 
  CheckCircle, 
  Clock, 
  AlertCircle, 
  User, 
  Mail, 
  ArrowRight,
  Save,
  MessageSquare,
  Sparkles,
  Zap,
  Globe
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function TicketsDashboardPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);

  // Form edit states
  const [status, setStatus] = useState<Ticket['status']>('Pending');
  const [agentNotes, setAgentNotes] = useState('');
  
  // Webhook simulations log
  const [webhookLogs, setWebhookLogs] = useState<string[]>([]);
  const [triggeringWebhook, setTriggeringWebhook] = useState(false);

  // Fetch tickets
  const fetchTickets = async () => {
    setLoading(true);
    try {
      const list = await getTickets();
      setTickets(list);
      if (list.length > 0) {
        setSelectedTicket(list[0]);
        setStatus(list[0].status);
        setAgentNotes(list[0].agentNotes || '');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTickets();
  }, []);

  const handleSelectTicket = (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setStatus(ticket.status);
    setAgentNotes(ticket.agentNotes || '');
  };

  const handleUpdateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTicket) return;

    const updatedTicket: Ticket = {
      ...selectedTicket,
      status,
      agentNotes: agentNotes || undefined
    };

    // Optimistic update
    setTickets(tickets.map(t => t.id === selectedTicket.id ? updatedTicket : t));
    setSelectedTicket(updatedTicket);

    // Persist
    await saveTicket(updatedTicket);

    // Trigger Simulated Webhook Notification
    setTriggeringWebhook(true);
    const newLog = `[Webhook Triggered] Ticket ${updatedTicket.id} updated status to [${updatedTicket.status}] with notes: "${updatedTicket.agentNotes || 'None'}". Payload dispatched to: https://api.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX`;
    
    setTimeout(() => {
      setWebhookLogs(prev => [newLog, ...prev]);
      setTriggeringWebhook(false);
      alert(`Ticket changes saved. Status successfully pushed to client portal and support Slack!`);
    }, 800);
  };

  // Status statistics
  const pendingCount = tickets.filter(t => t.status === 'Pending').length;
  const progressCount = tickets.filter(t => t.status === 'In Progress').length;
  const resolvedCount = tickets.filter(t => t.status === 'Resolved').length;

  return (
    <div className="space-y-6">
      
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Total Tickets</p>
            <h3 className="text-2xl font-bold mt-1 text-slate-800 dark:text-white">{tickets.length}</h3>
          </div>
          <div className="h-10 w-10 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            <TicketIcon className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Pending Action</p>
            <h3 className="text-2xl font-bold mt-1 text-amber-600 dark:text-amber-400">{pendingCount}</h3>
          </div>
          <div className="h-10 w-10 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
            <AlertCircle className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">In Progress</p>
            <h3 className="text-2xl font-bold mt-1 text-blue-600 dark:text-blue-400">{progressCount}</h3>
          </div>
          <div className="h-10 w-10 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            <Clock className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Resolved</p>
            <h3 className="text-2xl font-bold mt-1 text-emerald-600 dark:text-emerald-400">{resolvedCount}</h3>
          </div>
          <div className="h-10 w-10 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
            <CheckCircle className="h-5 w-5" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* LEFT COLUMN: Tickets Pipeline List */}
        <div className="lg:col-span-1 p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
          <h3 className="font-bold text-slate-800 dark:text-white">Active Queue</h3>
          
          <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
            {loading ? (
              <p className="text-slate-400 text-xs py-4 text-center">Loading ticket queue...</p>
            ) : tickets.length === 0 ? (
              <p className="text-slate-400 text-xs py-4 text-center">Queue is empty!</p>
            ) : (
              tickets.map((ticket) => {
                const isSelected = selectedTicket?.id === ticket.id;
                return (
                  <div
                    key={ticket.id}
                    onClick={() => handleSelectTicket(ticket)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all duration-200 ${
                      isSelected 
                        ? 'border-blue-500 bg-blue-50/10 dark:bg-blue-950/15' 
                        : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/30'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-xs text-slate-800 dark:text-white">{ticket.id}</span>
                      
                      <span className={`px-1.5 py-0.5 rounded text-[8px] font-extrabold uppercase tracking-wide ${
                        ticket.status === 'Resolved'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                          : ticket.status === 'In Progress'
                          ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'
                      }`}>
                        {ticket.status}
                      </span>
                    </div>

                    <p className="font-bold text-xs text-slate-700 dark:text-slate-200 truncate mt-2">{ticket.customerName}</p>
                    <p className="text-[11px] text-slate-400 truncate mt-0.5">{ticket.issueDescription}</p>

                    <div className="flex justify-between items-center text-[9px] text-slate-400 pt-3 mt-3 border-t border-slate-100 dark:border-slate-850">
                      <span>{new Date(ticket.createdAt).toLocaleDateString()}</span>
                      <span>Chat Messages: {ticket.chatbotHistory.length}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Ticket Drawer & Details */}
        <div className="lg:col-span-2 space-y-6">
          {selectedTicket ? (
            <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-6">
              
              {/* Ticket Heading */}
              <div className="flex justify-between items-start pb-4 border-b border-slate-200 dark:border-slate-800">
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="font-bold text-lg text-slate-800 dark:text-white">Ticket details for {selectedTicket.id}</h3>
                  </div>
                  <div className="flex items-center space-x-4 mt-2 text-xs text-slate-400 font-semibold">
                    <span className="flex items-center">
                      <User className="h-3.5 w-3.5 mr-1" />
                      {selectedTicket.customerName}
                    </span>
                    <span className="flex items-center">
                      <Mail className="h-3.5 w-3.5 mr-1" />
                      {selectedTicket.customerEmail}
                    </span>
                  </div>
                </div>

                <span className="text-xs text-slate-400 font-semibold uppercase">
                  Created {new Date(selectedTicket.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>

              {/* Description box */}
              <div className="space-y-1.5">
                <span className="block text-xs font-bold text-slate-400 uppercase">Customer Problem Statement</span>
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-150 dark:border-slate-800 text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                  {selectedTicket.issueDescription}
                </div>
              </div>

              {/* Chatbot Dialogue Logs */}
              <div className="space-y-2">
                <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-400 uppercase">
                  <MessageSquare className="h-4 w-4 text-blue-500" />
                  <span>Escalation Context: Pre-Chat Log Transcript</span>
                </div>
                
                <div className="max-h-40 overflow-y-auto p-4 bg-slate-50/50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-850 rounded-xl space-y-3">
                  {selectedTicket.chatbotHistory.length === 0 ? (
                    <span className="text-xs text-slate-400 italic">No pre-chat details. Ticket was filed directly.</span>
                  ) : (
                    selectedTicket.chatbotHistory.map((chat, idx) => {
                      const isBot = chat.sender === 'bot';
                      return (
                        <div key={idx} className="text-xs">
                          <span className={`font-bold ${isBot ? 'text-blue-500' : 'text-slate-500'}`}>
                            {isBot ? 'SUPPORT BOT:' : 'CLIENT:'}
                          </span>
                          <span className="ml-1 text-slate-600 dark:text-slate-350 italic">"{chat.message}"</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Resolution Form */}
              <form onSubmit={handleUpdateTicket} className="space-y-4 pt-4 border-t border-slate-200 dark:border-slate-800">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Update Ticket Status</label>
                    <select
                      value={status}
                      onChange={(e) => setStatus(e.target.value as Ticket['status'])}
                      className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none font-bold focus:border-blue-500 cursor-pointer appearance-none"
                    >
                      <option value="Pending">Pending</option>
                      <option value="In Progress">In Progress</option>
                      <option value="Resolved">Resolved</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Resolution Notes (Visible to Client)</label>
                  <textarea
                    rows={3}
                    value={agentNotes}
                    onChange={(e) => setAgentNotes(e.target.value)}
                    placeholder="Log technical actions, resolutions, or messages back to the customer here..."
                    className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 resize-none"
                  />
                </div>

                <div className="flex justify-between items-center">
                  <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                    <Globe className="h-3.5 w-3.5 text-blue-500" />
                    <span>Saves instantly to Customer status portal</span>
                  </div>
                  
                  <button
                    type="submit"
                    disabled={triggeringWebhook}
                    className="flex items-center space-x-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-md shadow-blue-500/20"
                  >
                    {triggeringWebhook ? (
                      <>
                        <div className="h-4.5 w-4.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Sending webhooks...</span>
                      </>
                    ) : (
                      <>
                        <Save className="h-4.5 w-4.5" />
                        <span>Save & Push Update</span>
                      </>
                    )}
                  </button>
                </div>
              </form>

            </div>
          ) : (
            <div className="p-12 text-center text-slate-400 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl">
              No tickets selected in active queue.
            </div>
          )}

          {/* Webhook notification logs console */}
          <div className="p-5 bg-slate-900 text-slate-300 font-mono text-xs rounded-2xl shadow-sm border border-slate-800 space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-slate-850">
              <span className="font-bold flex items-center text-blue-400">
                <Zap className="h-4 w-4 mr-1 text-blue-400" />
                Slack Webhook Log Integration Console
              </span>
              <span className="text-[10px] text-slate-500 font-bold uppercase">Simulated Sandbox</span>
            </div>

            <div className="max-h-24 overflow-y-auto space-y-2 pr-1 text-[10px]">
              {webhookLogs.length === 0 ? (
                <span className="text-slate-550 italic">No webhook payloads dispatched yet. Update a ticket to see output log.</span>
              ) : (
                webhookLogs.map((log, idx) => (
                  <div key={idx} className="p-2 bg-black/40 rounded border border-slate-850 text-slate-400 break-all leading-normal">
                    {log}
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
