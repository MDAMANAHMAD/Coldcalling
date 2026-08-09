'use client';

import { useState, useEffect } from 'react';
import { 
  getLeads, 
  getCallLogsWithLeads, 
  getMeetingsWithLeads, 
  getColdCallingStats, 
  bulkImportLeads, 
  triggerAIOutboundCampaign,
  deleteLead,
  triggerLiveKitOutboundCall
} from '@/app/actions';
import { Lead, CallLog, Meeting } from '@/lib/types';
import { 
  PhoneCall, 
  Mail, 
  Building, 
  Upload, 
  FileSpreadsheet, 
  Play, 
  Search, 
  Filter, 
  AlertCircle, 
  Video, 
  Clock, 
  CheckCircle, 
  HelpCircle,
  Sparkles,
  ArrowRight,
  Terminal,
  Send,
  Trash2,
  Volume2,
  Radio,
  Zap,
  PhoneOutgoing
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// Pre-populated Sales Outbound Script Prompt
const INITIAL_AGENT_PROMPT = `You are a professional outbound AI business representative calling on behalf of Antigravity Suite. Your goal is to introduce our business operations pipeline to the contact, address their objections, and schedule a 10-minute deep-dive demo.

Knowledge Base:
- Product: Antigravity is a unified SaaS that covers Sales CRM, Founder Email classification, invoice auto-generation, and support ticketing.
- Price Objection: If they say it is too expensive, offer a 14-day free trial or a custom startup discount.
- Competitor Objection: If they use Salesforce or HubSpot, highlight that we integrate out-of-the-box and save 10+ manual hours a week.
- Meeting Scheduling: If they agree, check for next Tuesday at 3 PM and confirm their email address to send a Google Meet link.`;

export default function ColdCallingDashboard() {
  const [stats, setStats] = useState({ totalLeads: 0, completedCalls: 0, conversionRate: 0, meetingsScheduled: 0 });
  const [leads, setLeads] = useState<Lead[]>([]);
  const [callLogs, setCallLogs] = useState<(CallLog & { leadName: string; leadCompany?: string })[]>([]);
  const [meetings, setMeetings] = useState<(Meeting & { leadName: string; leadEmail?: string; leadCompany?: string })[]>([]);
  
  const [activeTab, setActiveTab] = useState<'leads' | 'calls' | 'meetings'>('leads');
  const [loading, setLoading] = useState(true);

  // Search & Filter
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  
  // CSV Import states
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [parsedLeads, setParsedLeads] = useState<any[]>([]);
  const [countryCode, setCountryCode] = useState('+91'); // Default India formatting
  const [importReport, setImportReport] = useState<{ imported: number; skipped: number } | null>(null);

  // Campaign Outbound prompt state
  const [agentPrompt, setAgentPrompt] = useState(INITIAL_AGENT_PROMPT);
  const [selectedLeadIds, setSelectedLeadIds] = useState<string[]>([]);
  const [dispatchStatus, setDispatchStatus] = useState<string | null>(null);

  // Webhook Simulator states
  const [simLeadId, setSimLeadId] = useState('');
  const [simOutcome, setSimOutcome] = useState<'interested' | 'not_interested' | 'callback_required' | 'meeting_scheduled'>('meeting_scheduled');
  const [simMeetingTime, setSimMeetingTime] = useState(new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString().substring(0, 16)); // 2 days default
  const [simDuration, setSimDuration] = useState(120);
  const [simTranscript, setSimTranscript] = useState("Agent: Hi Bruce, scheduling a Google Meet for Wayne Enterprises.\nBruce Wayne: Yes, schedule it.");
  const [webhookResult, setWebhookResult] = useState<any>(null);
  const [sendingWebhook, setSendingWebhook] = useState(false);

  // Audio Playback Mock
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null);

  // LiveKit Direct Dialing states
  const [livekitDialing, setLivekitDialing] = useState(false);
  const [livekitTargetPhone, setLivekitTargetPhone] = useState('+918693081506');
  const [livekitTargetName, setLivekitTargetName] = useState('Aman');
  const [livekitResult, setLivekitResult] = useState<{ success: boolean; message: string; output?: string } | null>(null);

  const handleTriggerLiveKitCall = async () => {
    setLivekitDialing(true);
    setLivekitResult(null);
    try {
      const response = await fetch('/api/outbound-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phoneNumber: livekitTargetPhone,
          customerName: livekitTargetName,
          company: "Aman Corp"
        })
      });
      const data = await response.json();
      setLivekitResult({
        success: data.success,
        message: data.message || (data.success ? 'Call dispatched successfully!' : 'Call failed.'),
        output: data.roomName ? `Room: ${data.roomName}` : data.error
      });
      await loadDashboardData();
    } catch (e: any) {
      setLivekitResult({ success: false, message: e.message || "Failed to trigger call." });
    } finally {
      setLivekitDialing(false);
    }
  };

  // Fetch all dashboard data
  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const dbLeads = await getLeads();
      const dbCalls = await getCallLogsWithLeads();
      const dbMeets = await getMeetingsWithLeads();
      const dbStats = await getColdCallingStats();

      setLeads(dbLeads);
      setCallLogs(dbCalls);
      setMeetings(dbMeets);
      setStats(dbStats);

      if (dbLeads.length > 0) {
        setSimLeadId(dbLeads[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Standard E.164 phone formatting logic
  const formatE164 = (phone: string, defaultCode: string): string => {
    let clean = phone.replace(/\D/g, ''); // strip formatting
    if (phone.startsWith('+')) {
      return `+${clean}`;
    }
    // If digits are 10, prepend selected country code
    if (clean.length === 10) {
      return `${defaultCode}${clean}`;
    }
    // If it already starts with country code (e.g. 91 or 1), add +
    if (clean.length > 10 && (clean.startsWith('91') || clean.startsWith('1'))) {
      return `+${clean}`;
    }
    return `+${clean}`;
  };

  // CSV Drag and Drop Parsers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const parseCsvText = (text: string) => {
    // Basic CSV parser splitting lines and handling commas/quotes
    const lines = text.split(/\r?\n/).filter(line => line.trim() !== '');
    if (lines.length === 0) return;

    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    
    // Check required columns
    const nameIdx = headers.findIndex(h => h.includes('name'));
    const phoneIdx = headers.findIndex(h => h.includes('phone'));
    const emailIdx = headers.findIndex(h => h.includes('email'));
    const companyIdx = headers.findIndex(h => h.includes('company'));

    if (nameIdx === -1 || phoneIdx === -1) {
      alert("CSV must contain 'Name' and 'Phone' headers!");
      return;
    }

    const leads: any[] = [];

    for (let i = 1; i < lines.length; i++) {
      // Split regex considering quotes
      const cells = lines[i].split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/).map(c => c.trim().replace(/^"|"$/g, ''));
      if (cells.length <= Math.max(nameIdx, phoneIdx)) continue;

      const name = cells[nameIdx];
      const rawPhone = cells[phoneIdx];
      if (!name || !rawPhone) continue;

      const cleanPhone = formatE164(rawPhone, countryCode);
      const email = emailIdx !== -1 ? cells[emailIdx] : '';
      const company = companyIdx !== -1 ? cells[companyIdx] : '';

      leads.push({ name, phone: cleanPhone, email, company });
    }

    setParsedLeads(leads);
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].name.endsWith('.csv')) {
      const file = files[0];
      setCsvFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        parseCsvText(event.target?.result as string);
      };
      reader.readAsText(file);
    } else {
      alert("Please upload a valid CSV file!");
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0 && files[0].name.endsWith('.csv')) {
      const file = files[0];
      setCsvFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        parseCsvText(event.target?.result as string);
      };
      reader.readAsText(file);
    }
  };

  // Submit CSV Leads
  const handleBulkInsert = async () => {
    if (parsedLeads.length === 0) return;
    try {
      const report = await bulkImportLeads(parsedLeads);
      setImportReport(report);
      setParsedLeads([]);
      setCsvFile(null);
      await loadDashboardData();
      setTimeout(() => setImportReport(null), 5000);
    } catch (e) {
      console.error(e);
      alert("Error importing leads");
    }
  };

  // Select / Check leads
  const toggleSelectLead = (id: string) => {
    setSelectedLeadIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAllLeads = (filteredLeads: Lead[]) => {
    const queuedIds = filteredLeads.filter(l => l.status === 'queued').map(l => l.id);
    if (selectedLeadIds.length === queuedIds.length) {
      setSelectedLeadIds([]);
    } else {
      setSelectedLeadIds(queuedIds);
    }
  };

  // Launch AI Outreach Campaign
  const handleStartCampaign = async () => {
    if (selectedLeadIds.length === 0) {
      alert("Please select at least one 'queued' lead to dial!");
      return;
    }
    setDispatchStatus("Initiating call sequences...");
    try {
      const res = await triggerAIOutboundCampaign(selectedLeadIds, agentPrompt);
      setDispatchStatus(`Success: Initiated outbound campaigns for ${res.dispatchedCount} voice agents!`);
      setSelectedLeadIds([]);
      await loadDashboardData();
      setTimeout(() => setDispatchStatus(null), 4000);
    } catch (e) {
      console.error(e);
      setDispatchStatus("Dialer Campaign Failed");
    }
  };

  // Simulated Webhook triggers
  const handleTriggerMockWebhook = async () => {
    if (!simLeadId) {
      alert("Please select a target lead to simulate call webhook!");
      return;
    }
    
    setSendingWebhook(true);
    setWebhookResult(null);

    const targetLead = leads.find(l => l.id === simLeadId);
    if (!targetLead) return;

    // Build Webhook Request Payload simulating Vapi end-of-call-report
    const payload = {
      phone: targetLead.phone,
      status: simOutcome,
      durationSeconds: simDuration,
      recordingUrl: `https://api.vapi.ai/recordings/mock_vapi_${Math.random().toString(36).substr(2, 9)}.mp3`,
      transcript: simTranscript,
      aiSummary: `Simulated sales call with ${targetLead.name} regarding Antigravity operations. Conversation marked outcome: ${simOutcome}.`,
      sentiment: simOutcome === 'meeting_scheduled' || simOutcome === 'interested' ? 'positive' : simOutcome === 'not_interested' ? 'negative' : 'neutral',
      meetingTime: simOutcome === 'meeting_scheduled' ? new Date(simMeetingTime).toISOString() : undefined
    };

    try {
      const response = await fetch('/api/webhooks/voice-agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const json = await response.json();
      setWebhookResult({
        status: response.status,
        body: json
      });

      // Reload dashboard stats
      await loadDashboardData();
    } catch (e: any) {
      setWebhookResult({
        status: 500,
        body: { error: e.message || 'Webhook post error' }
      });
    } finally {
      setSendingWebhook(false);
    }
  };

  const handleMockAudio = (logId: string) => {
    if (playingAudioId === logId) {
      setPlayingAudioId(null);
    } else {
      setPlayingAudioId(logId);
      // Automatically toggle off after 3 seconds to simulate brief playback
      setTimeout(() => setPlayingAudioId(prev => prev === logId ? null : prev), 5000);
    }
  };

  const handleDeleteLeadEntry = async (id: string) => {
    if (!confirm("Are you sure you want to delete this lead?")) return;
    await deleteLead(id);
    await loadDashboardData();
  };

  // Filter leads
  const filteredLeads = leads.filter(l => {
    const matchesSearch = 
      l.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (l.company || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      l.phone.includes(searchTerm);
      
    const matchesStatus = statusFilter === 'All' || l.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      
      {/* 0. LiveKit + Gemini Live Direct Outbound Calling Banner */}
      <div className="p-6 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-indigo-500/30 rounded-3xl shadow-xl text-white relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20"></div>
        
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="space-y-2 max-w-xl">
            <div className="flex items-center space-x-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-400 animate-ping"></span>
              <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 border border-indigo-400/30 text-[10px] font-black uppercase tracking-wider text-indigo-300 flex items-center gap-1">
                <Radio className="h-3 w-3 text-emerald-400" /> LiveKit + Gemini Live Speech-to-Speech
              </span>
            </div>
            <h2 className="text-xl font-black tracking-tight text-white flex items-center gap-2">
              <PhoneOutgoing className="h-5 w-5 text-indigo-400" />
              1-Click Outbound Voice AI Call
            </h2>
            <p className="text-xs text-slate-300 leading-relaxed font-medium">
              Directly dial out via Vobiz SIP Trunk to your physical phone. Sarah (Gemini Live) will deliver the opening sales pitch and qualify the call in real-time.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 bg-black/40 p-3 rounded-2xl border border-indigo-500/20 backdrop-blur-md">
            <div>
              <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1">Contact Name</label>
              <input
                type="text"
                value={livekitTargetName}
                onChange={(e) => setLivekitTargetName(e.target.value)}
                className="w-28 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs font-bold text-white outline-none focus:border-indigo-400"
                placeholder="Name"
              />
            </div>
            <div>
              <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1">Phone Number (E.164)</label>
              <input
                type="text"
                value={livekitTargetPhone}
                onChange={(e) => setLivekitTargetPhone(e.target.value)}
                className="w-40 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs font-mono font-bold text-emerald-400 outline-none focus:border-indigo-400"
                placeholder="+918693081506"
              />
            </div>
            <div className="sm:self-end">
              <button
                onClick={handleTriggerLiveKitCall}
                disabled={livekitDialing || !livekitTargetPhone}
                className="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 text-white rounded-xl font-extrabold text-xs shadow-lg shadow-emerald-500/20 flex items-center justify-center gap-2 transition-all transform active:scale-95"
              >
                {livekitDialing ? (
                  <>
                    <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></span>
                    <span>Dialing via SIP...</span>
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4 fill-white" />
                    <span>Call My Phone Now</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Live execution feedback alert */}
        {livekitResult && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`mt-4 p-3 rounded-xl text-xs font-medium border flex items-start justify-between gap-3 ${
              livekitResult.success 
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300' 
                : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
            }`}
          >
            <div>
              <p className="font-bold">{livekitResult.message}</p>
              {livekitResult.output && (
                <pre className="mt-2 p-2 bg-black/60 rounded-lg text-[10px] font-mono text-slate-300 max-h-24 overflow-y-auto whitespace-pre-wrap">
                  {livekitResult.output}
                </pre>
              )}
            </div>
            <button 
              onClick={() => setLivekitResult(null)}
              className="text-slate-400 hover:text-white text-xs font-bold"
            >
              ✕
            </button>
          </motion.div>
        )}
      </div>

      {/* 1. Summary Metrics Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="p-4 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Total Leads Loaded</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{stats.totalLeads}</h3>
          </div>
          <div className="h-10 w-10 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-xl flex items-center justify-center">
            <FileSpreadsheet className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Completed Calls</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{stats.completedCalls}</h3>
          </div>
          <div className="h-10 w-10 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-xl flex items-center justify-center">
            <PhoneCall className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Conversion Rate</p>
            <h3 className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">{stats.conversionRate}%</h3>
          </div>
          <div className="h-10 w-10 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl flex items-center justify-center">
            <Sparkles className="h-5 w-5" />
          </div>
        </div>

        <div className="p-4 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Meet Appointments</p>
            <h3 className="text-2xl font-black text-purple-650 dark:text-purple-400 mt-1">{stats.meetingsScheduled} Scheduled</h3>
          </div>
          <div className="h-10 w-10 bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-xl flex items-center justify-center">
            <Video className="h-5 w-5" />
          </div>
        </div>

      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* LEFT COLUMN: CSV Zone & Campaigns Agent settings (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* CSV drag upload zone */}
          <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-100 dark:border-slate-850">
              <h4 className="font-bold text-sm text-slate-800 dark:text-white flex items-center">
                <FileSpreadsheet className="h-4.5 w-4.5 text-blue-500 mr-1.5" />
                CSV Bulk Import Engine
              </h4>
              <span className="text-[10px] text-slate-400 font-semibold bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                E.164 Cleaned
              </span>
            </div>

            {/* Country Formatting Settings */}
            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400">Standardize Prefix:</span>
              <select
                value={countryCode}
                onChange={(e) => setCountryCode(e.target.value)}
                className="px-2 py-1 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg font-bold"
              >
                <option value="+91">+91 (India)</option>
                <option value="+1">+1 (US/Canada)</option>
                <option value="+44">+44 (UK)</option>
              </select>
            </div>

            {/* Drag & Drop Area */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleFileDrop}
              className={`p-6 border-2 border-dashed rounded-xl flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
                dragOver 
                  ? 'border-blue-500 bg-blue-50/10' 
                  : 'border-slate-200 dark:border-slate-800 hover:border-slate-350 dark:hover:border-slate-700'
              }`}
              onClick={() => document.getElementById('csv-file-picker')?.click()}
            >
              <input
                id="csv-file-picker"
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleFileSelect}
              />
              <Upload className="h-8 w-8 text-slate-350 mb-2" />
              <p className="text-xs font-bold text-slate-750 dark:text-slate-200">
                {csvFile ? csvFile.name : "Drag & Drop CSV lead list"}
              </p>
              <p className="text-[10px] text-slate-400 mt-1">
                Required columns: Name, Phone (Email/Company optional)
              </p>
            </div>

            {/* CSV Parser Preview & Save */}
            {parsedLeads.length > 0 && (
              <motion.div 
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="space-y-3 pt-2"
              >
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 font-medium">Parsed <strong>{parsedLeads.length}</strong> leads</span>
                  <button 
                    onClick={() => setParsedLeads([])} 
                    className="text-slate-400 hover:text-slate-650"
                  >
                    Clear
                  </button>
                </div>

                <div className="max-h-24 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 border border-slate-150 dark:border-slate-800 rounded-lg p-2 text-[10px] bg-slate-50 dark:bg-slate-900">
                  {parsedLeads.map((lead, idx) => (
                    <div key={idx} className="py-1 flex justify-between">
                      <span className="font-bold text-slate-700 dark:text-slate-300 truncate max-w-[120px]">{lead.name}</span>
                      <span className="font-mono text-slate-500">{lead.phone}</span>
                    </div>
                  ))}
                </div>

                <button
                  onClick={handleBulkInsert}
                  className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold shadow-md shadow-blue-500/20"
                >
                  Insert Leads to Queue
                </button>
              </motion.div>
            )}

            {/* Import report results */}
            {importReport && (
              <div className="p-3 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 rounded-xl text-[11px] text-emerald-600 dark:text-emerald-450 leading-relaxed font-medium">
                Successfully imported <strong>{importReport.imported}</strong> leads. Skipped <strong>{importReport.skipped}</strong> duplicate phone numbers.
              </div>
            )}
          </div>

          {/* AI Voice Agent Prompt Config */}
          <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <div className="flex items-center space-x-1.5 pb-2 border-b border-slate-100 dark:border-slate-850">
              <Sparkles className="h-4.5 w-4.5 text-indigo-500" />
              <h4 className="font-bold text-sm text-slate-850 dark:text-white">AI Voice Agent Settings</h4>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1.5">Custom Outbound Call Script</label>
              <textarea
                value={agentPrompt}
                onChange={(e) => setAgentPrompt(e.target.value)}
                rows={7}
                className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-xs outline-none focus:border-blue-500 resize-none font-medium leading-relaxed"
                placeholder="Give instructions to the AI voice model..."
              />
            </div>

            <div className="pt-2">
              <button
                onClick={handleStartCampaign}
                disabled={selectedLeadIds.length === 0}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl font-bold text-xs shadow-md shadow-indigo-500/20 transition-all flex items-center justify-center space-x-1.5"
              >
                <Play className="h-4 w-4 fill-white" />
                <span>Start AI Campaign ({selectedLeadIds.length})</span>
              </button>
            </div>

            {dispatchStatus && (
              <div className="p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/30 rounded-xl text-[11px] text-blue-600 dark:text-blue-450 leading-relaxed font-semibold">
                {dispatchStatus}
              </div>
            )}
          </div>

        </div>

        {/* RIGHT COLUMN: Webhook sandbox & Data Tabs (lg:col-span-8) */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* 1. Webhook Simulator Sandbox Drawer */}
          <div className="p-6 bg-slate-950 border border-slate-800 text-slate-350 rounded-3xl shadow-lg space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-850">
              <span className="font-extrabold flex items-center text-blue-450 text-sm font-mono">
                <Terminal className="h-5 w-5 mr-1.5 text-blue-450" />
                Webhook Testing Sandbox Console
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-black/40 px-2 py-0.5 rounded border border-slate-850">
                Local Simulator
              </span>
            </div>

            <p className="text-[11px] text-slate-400 leading-normal">
              Simulate call webhooks from Vapi.ai / Retell AI. This schedules meetings, updates CRM logs, and creates Google Meet invites in real-time.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
              <div className="col-span-2">
                <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">Target CRM Lead</label>
                <select
                  value={simLeadId}
                  onChange={(e) => setSimLeadId(e.target.value)}
                  className="w-full px-3 py-2 bg-black border border-slate-800 rounded-xl outline-none font-bold text-slate-300 cursor-pointer"
                >
                  {leads.map(l => (
                    <option key={l.id} value={l.id}>{l.name} ({l.phone})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">Call Sentiment / Outcome</label>
                <select
                  value={simOutcome}
                  onChange={(e) => setSimOutcome(e.target.value as any)}
                  className="w-full px-3 py-2 bg-black border border-slate-800 rounded-xl outline-none font-bold text-slate-300 cursor-pointer"
                >
                  <option value="meeting_scheduled">Meeting Scheduled</option>
                  <option value="interested">Interested - No Meeting</option>
                  <option value="not_interested">Not Interested</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">Call Duration (Sec)</label>
                <input
                  type="number"
                  value={simDuration}
                  onChange={(e) => setSimDuration(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 bg-black border border-slate-800 rounded-xl outline-none font-bold text-slate-300 text-center"
                />
              </div>
            </div>

            {simOutcome === 'meeting_scheduled' && (
              <div>
                <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">Calendar Appointment Time</label>
                <input
                  type="datetime-local"
                  value={simMeetingTime}
                  onChange={(e) => setSimMeetingTime(e.target.value)}
                  className="w-full px-3 py-2 bg-black border border-slate-800 rounded-xl outline-none font-bold text-slate-300"
                />
              </div>
            )}

            <div>
              <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">Call Transcript Text</label>
              <textarea
                value={simTranscript}
                onChange={(e) => setSimTranscript(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 bg-black border border-slate-800 rounded-xl outline-none text-slate-300 font-mono text-[10px] resize-none"
              />
            </div>

            <div className="flex gap-4 items-center">
              <button
                onClick={handleTriggerMockWebhook}
                disabled={sendingWebhook || !simLeadId}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl font-bold text-xs flex items-center justify-center space-x-1.5 transition-colors shadow"
              >
                <Send className="h-4 w-4" />
                <span>Simulate Webhook Trigger</span>
              </button>
            </div>

            {/* Output log */}
            {webhookResult && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="p-3 bg-black border border-slate-800 rounded-xl text-[10px] font-mono space-y-1.5"
              >
                <div className="flex justify-between items-center text-slate-400 pb-1 border-b border-slate-900">
                  <span>HTTP Response Status: <strong>{webhookResult.status}</strong></span>
                  <span className={webhookResult.status === 200 ? 'text-emerald-500' : 'text-rose-500'}>
                    {webhookResult.status === 200 ? 'SUCCESS' : 'FAILED'}
                  </span>
                </div>
                <pre className="text-slate-300 max-h-20 overflow-y-auto whitespace-pre-wrap leading-normal font-sans">
                  {JSON.stringify(webhookResult.body, null, 2)}
                </pre>
              </motion.div>
            )}
          </div>

          {/* 2. Data Navigation Tabs Card */}
          <div className="bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden flex flex-col h-full">
            
            {/* Tabs Header */}
            <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 flex justify-between items-center">
              <div className="flex space-x-2">
                <button
                  onClick={() => setActiveTab('leads')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === 'leads' ? 'bg-blue-650 text-white shadow-sm' : 'text-slate-500 dark:text-slate-450 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  CRM Leads
                </button>
                <button
                  onClick={() => setActiveTab('calls')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === 'calls' ? 'bg-blue-650 text-white shadow-sm' : 'text-slate-500 dark:text-slate-450 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  Call Logs ({callLogs.length})
                </button>
                <button
                  onClick={() => setActiveTab('meetings')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === 'meetings' ? 'bg-blue-650 text-white shadow-sm' : 'text-slate-500 dark:text-slate-450 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  Google Meet Links ({meetings.length})
                </button>
              </div>

              {activeTab === 'leads' && (
                <div className="relative max-w-xs">
                  <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search leads..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-8 pr-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 rounded-lg text-[11px] outline-none focus:border-blue-500"
                  />
                </div>
              )}
            </div>

            {/* Content Drawer Panels */}
            <div className="flex-1 min-h-[350px] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-850">
              
              {/* LEADS TAB PANEL */}
              {activeTab === 'leads' && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                        <th className="px-5 py-3 text-center">
                          <input
                            type="checkbox"
                            className="rounded border-slate-200 dark:border-slate-700 text-blue-650 cursor-pointer"
                            checked={selectedLeadIds.length > 0 && selectedLeadIds.length === filteredLeads.filter(l => l.status === 'queued').length}
                            onChange={() => toggleSelectAllLeads(filteredLeads)}
                          />
                        </th>
                        <th className="px-5 py-3">Lead Info</th>
                        <th className="px-5 py-3">Company</th>
                        <th className="px-5 py-3">Campaign Status</th>
                        <th className="px-5 py-3">Last Dialed</th>
                        <th className="px-5 py-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-850">
                      {loading ? (
                        <tr>
                          <td colSpan={6} className="text-center py-12 text-slate-400">Loading leads pipeline...</td>
                        </tr>
                      ) : filteredLeads.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="text-center py-12 text-slate-400">No leads found in this filter list.</td>
                        </tr>
                      ) : (
                        filteredLeads.map((lead) => (
                          <tr key={lead.id} className="hover:bg-slate-50/30 dark:hover:bg-slate-800/10">
                            <td className="px-5 py-4 text-center">
                              <input
                                type="checkbox"
                                className="rounded border-slate-200 dark:border-slate-700 text-blue-650 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                                disabled={lead.status !== 'queued'}
                                checked={selectedLeadIds.includes(lead.id)}
                                onChange={() => toggleSelectLead(lead.id)}
                              />
                            </td>
                            <td className="px-5 py-4">
                              <div>
                                <h5 className="font-bold text-slate-800 dark:text-white leading-tight">{lead.name}</h5>
                                <div className="flex gap-2 text-[10px] text-slate-400 mt-1">
                                  <span>{lead.phone}</span>
                                  {lead.email && (
                                    <>
                                      <span>•</span>
                                      <span className="truncate max-w-[120px]">{lead.email}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </td>
                            <td className="px-5 py-4 font-medium text-slate-600 dark:text-slate-400">
                              {lead.company || '-'}
                            </td>
                            <td className="px-5 py-4">
                              <span className={`px-2 py-0.5 rounded font-extrabold text-[9px] uppercase tracking-wide border ${
                                lead.status === 'queued'
                                  ? 'bg-slate-50 border-slate-200 text-slate-600 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400'
                                  : lead.status === 'calling'
                                  ? 'bg-blue-50 border-blue-200 text-blue-600 dark:bg-blue-950/20 dark:border-blue-900 dark:text-blue-400 animate-pulse'
                                  : lead.status === 'meeting_scheduled'
                                  ? 'bg-purple-50 border-purple-200 text-purple-650 dark:bg-purple-950/20 dark:border-purple-900 dark:text-purple-400'
                                  : lead.status === 'interested'
                                  ? 'bg-emerald-50 border-emerald-200 text-emerald-650 dark:bg-emerald-950/20 dark:border-emerald-900 dark:text-emerald-400'
                                  : lead.status === 'failed'
                                  ? 'bg-rose-50 border-rose-200 text-rose-650 dark:bg-rose-950/20 dark:border-rose-900 dark:text-rose-450'
                                  : 'bg-amber-50 border-amber-200 text-amber-600 dark:bg-amber-950/20 dark:border-amber-900 dark:text-amber-400'
                              }`}>
                                {lead.status.replace('_', ' ')}
                              </span>
                            </td>
                            <td className="px-5 py-4 text-[10px] text-slate-400">
                              {lead.lastCallAt ? new Date(lead.lastCallAt).toLocaleDateString() : 'Never'}
                            </td>
                            <td className="px-5 py-4 text-right">
                              <button
                                onClick={() => handleDeleteLeadEntry(lead.id)}
                                className="p-1 text-slate-400 hover:text-rose-500 rounded transition-colors"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {/* CALL LOGS TAB PANEL */}
              {activeTab === 'calls' && (
                <div className="p-4 space-y-4">
                  {callLogs.length === 0 ? (
                    <p className="text-slate-400 text-center py-12">No call log entries recorded yet.</p>
                  ) : (
                    callLogs.map((log) => (
                      <div key={log.id} className="p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-150 dark:border-slate-800 rounded-2xl space-y-3">
                        <div className="flex justify-between items-start gap-4">
                          <div>
                            <h5 className="font-bold text-slate-800 dark:text-white leading-tight">
                              AI Outbound Call to: <strong>{log.leadName}</strong> {log.leadCompany ? `(${log.leadCompany})` : ''}
                            </h5>
                            <span className="text-[10px] text-slate-400 font-medium">
                              ID: {log.callSid} • {new Date(log.calledAt).toLocaleString()}
                            </span>
                          </div>

                          <div className="flex items-center space-x-2">
                            {/* Sentiment badge */}
                            <span className={`px-2 py-0.5 rounded font-extrabold text-[8px] uppercase tracking-widest ${
                              log.sentiment === 'positive'
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                                : log.sentiment === 'negative'
                                ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/20 dark:text-rose-450'
                                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                            }`}>
                              {log.sentiment} sentiment
                            </span>
                            
                            <span className="text-[10px] text-slate-400 flex items-center font-bold">
                              <Clock className="h-3.5 w-3.5 mr-0.5 text-slate-350" />
                              {log.durationSeconds}s
                            </span>
                          </div>
                        </div>

                        {/* Summary & Transcript collapsible */}
                        <div className="space-y-2 text-xs">
                          <p className="text-slate-500 dark:text-slate-400 leading-relaxed bg-white dark:bg-slate-950 p-2.5 border border-slate-100 dark:border-slate-900 rounded-lg">
                            <strong>AI Summary:</strong> {log.aiSummary}
                          </p>

                          {/* Recording simulation player */}
                          <div className="flex items-center justify-between p-2 rounded-lg bg-blue-50/50 dark:bg-blue-950/10 border border-blue-100/30 text-[11px]">
                            <button
                              onClick={() => handleMockAudio(log.id)}
                              className="flex items-center space-x-1 text-blue-600 dark:text-blue-400 font-bold"
                            >
                              <Volume2 className="h-3.5 w-3.5 animate-bounce" style={{ animationPlayState: playingAudioId === log.id ? 'running' : 'paused' }} />
                              <span>{playingAudioId === log.id ? "Mock Playing Audio Recording..." : "Listen Call Recording"}</span>
                            </button>
                            {playingAudioId === log.id && (
                              <span className="text-[10px] text-slate-400">0:03 / 2:22</span>
                            )}
                          </div>

                          <div className="bg-slate-100 dark:bg-slate-950 p-3 rounded-lg border border-slate-200/50 dark:border-slate-900 max-h-36 overflow-y-auto">
                            <span className="block font-bold text-[10px] text-slate-400 uppercase tracking-wide mb-1.5">Dialogue Transcript Log:</span>
                            <p className="font-mono text-[10px] whitespace-pre-line text-slate-600 dark:text-slate-400 leading-normal">
                              {log.transcript}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* MEETINGS TAB PANEL */}
              {activeTab === 'meetings' && (
                <div className="p-4 space-y-3">
                  {meetings.length === 0 ? (
                    <p className="text-slate-400 text-center py-12">No scheduled Google Meet appointments logged.</p>
                  ) : (
                    meetings.map((meet) => (
                      <div key={meet.id} className="p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-150 dark:border-slate-800 rounded-2xl flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                        <div className="space-y-1">
                          <h5 className="font-bold text-slate-850 dark:text-white leading-tight">
                            Google Meet Demo: <strong>{meet.leadName}</strong> {meet.leadCompany ? `(${meet.leadCompany})` : ''}
                          </h5>
                          <div className="flex flex-col sm:flex-row gap-2 text-[10px] text-slate-400 font-semibold">
                            <span className="flex items-center text-indigo-600 dark:text-indigo-400">
                              <Clock className="h-3.5 w-3.5 mr-0.5" />
                              {new Date(meet.scheduledTime).toLocaleString([], { dateStyle: 'long', timeStyle: 'short' })}
                            </span>
                            {meet.leadEmail && <span>• Email: {meet.leadEmail}</span>}
                          </div>
                        </div>

                        <div className="flex items-center space-x-3">
                          <span className={`px-2 py-0.5 rounded font-extrabold text-[8px] uppercase tracking-wide ${
                            meet.status === 'confirmed'
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                              : 'bg-slate-100 text-slate-500'
                          }`}>
                            {meet.status}
                          </span>

                          <a
                            href={meet.googleMeetLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-xs flex items-center justify-center space-x-1.5 shadow"
                          >
                            <Video className="h-4 w-4" />
                            <span>Join Meet Session</span>
                          </a>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

            </div>

          </div>
        </div>

      </div>

    </div>
  );
}
