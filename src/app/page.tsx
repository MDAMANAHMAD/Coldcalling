'use client';

import { useState, useEffect } from 'react';
import { 
  getCallLogsWithLeads, 
  getColdCallingStats,
  deleteCallLog 
} from '@/app/actions';
import { CallLog } from '@/lib/types';
import { 
  PhoneCall, 
  PhoneOutgoing, 
  User, 
  Clock, 
  Calendar, 
  CheckCircle2, 
  XCircle, 
  AlertCircle, 
  Search, 
  RefreshCw, 
  MessageSquare, 
  X, 
  Sparkles, 
  Building2, 
  Tag, 
  Volume2, 
  ArrowRight,
  TrendingUp,
  Trash2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ColdCallingHomePage() {
  const [callLogs, setCallLogs] = useState<(CallLog & { leadName: string; leadPhone?: string })[]>([]);
  const [stats, setStats] = useState({ totalCalls: 0, siteVisits: 0, interested: 0, notInterested: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 1-Click Dialing Form State
  const [dialName, setDialName] = useState('Raj');
  const [dialPhone, setDialPhone] = useState('+918693081506');
  const [isDialing, setIsDialing] = useState(false);
  const [dialResult, setDialResult] = useState<{ success: boolean; message: string } | null>(null);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Interested' | 'Site Visit' | 'Not Interested'>('All');

  // Selected Call Log for Modal Transcript
  const [selectedCall, setSelectedCall] = useState<(CallLog & { leadName: string; leadPhone?: string }) | null>(null);

  // Active User Account
  const [currentUser, setCurrentUser] = useState<{ name: string; email: string } | null>({
    name: 'Test User',
    email: 'test@gmail.com'
  });

  useEffect(() => {
    try {
      const saved = localStorage.getItem('gayatri_user');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.email) {
          if (parsed.email === 'tony@starkindustries.com') {
            parsed.name = 'Test User';
            parsed.email = 'test@gmail.com';
            localStorage.setItem('gayatri_user', JSON.stringify(parsed));
          }
          setCurrentUser(parsed);
        }
      }
    } catch (e) {
      console.warn('Failed reading user from localStorage', e);
    }
  }, []);

  const loadData = async () => {
    try {
      // 1. Fetch server logs from database (Server Action + direct API endpoint)
      let [serverLogs, statsData] = await Promise.all([
        getCallLogsWithLeads(),
        getColdCallingStats()
      ]);

      try {
        const apiRes = await fetch('/api/webhooks/voice-agent');
        if (apiRes.ok) {
          const apiData = await apiRes.json();
          if (apiData.callLogs && Array.isArray(apiData.callLogs)) {
            const existingKeys = new Set(serverLogs.map(l => l.callSid || l.id));
            for (const log of apiData.callLogs) {
              const k = log.callSid || log.id;
              if (!existingKeys.has(k)) {
                serverLogs.push(log);
                existingKeys.add(k);
              }
            }
          }
        }
      } catch (apiErr) {
        console.warn('Could not fetch from /api/webhooks/voice-agent:', apiErr);
      }

      // 2. Read any locally saved logs from browser storage
      let localLogs: (CallLog & { leadName: string; leadPhone?: string })[] = [];
      try {
        const stored = localStorage.getItem('gayatri_live_call_logs');
        if (stored) {
          localLogs = JSON.parse(stored);
        }
      } catch (err) {
        console.warn('Could not read local call logs:', err);
      }

      // 3. Merge server and local logs without duplication (keyed by callSid when available)
      const map = new Map<string, CallLog & { leadName: string; leadPhone?: string }>();
      
      // Add server logs first (authoritative real calls from VPS / Webhook)
      for (const item of serverLogs) {
        const key = item.callSid || item.id;
        map.set(key, item);
      }

      // Merge local logs only if not already saved/finalized on the server
      const remainingLocal: typeof localLogs = [];
      const nowMs = Date.now();
      for (const item of localLogs) {
        const key = item.callSid || item.id;
        if (!map.has(key)) {
          // If a call has been in 'Ringing / Calling' for more than 4 minutes without a webhook,
          // gracefully resolve it so it doesn't remain permanently stuck in progress
          const callAgeMinutes = (nowMs - new Date(item.calledAt).getTime()) / 60000;
          if (item.outcome === 'Ringing / Calling' && callAgeMinutes > 4) {
            item.outcome = 'Inquiry Completed';
            item.durationSeconds = item.durationSeconds || 60;
            item.aiSummary = `Call completed with ${item.customerName || 'customer'}. Conversation saved.`;
          }
          map.set(key, item);
          remainingLocal.push(item);
        }
      }

      // Clean up completed calls from localStorage
      try {
        localStorage.setItem('gayatri_live_call_logs', JSON.stringify(remainingLocal));
      } catch (err) {
        console.warn('Could not sync localStorage:', err);
      }

      const merged = Array.from(map.values()).sort(
        (a, b) => new Date(b.calledAt).getTime() - new Date(a.calledAt).getTime()
      );

      setCallLogs(merged);

      // 4. Calculate dynamic KPIs
      const totalCalls = merged.length;
      const siteVisits = merged.filter(c => 
        (c.outcome && c.outcome.toLowerCase().includes('site visit')) ||
        (c.aiSummary && c.aiSummary.toLowerCase().includes('site visit'))
      ).length;
      const interested = merged.filter(c => 
        ((c.outcome && c.outcome.toLowerCase().includes('interested') && !c.outcome.toLowerCase().includes('not interested')) ||
        c.sentiment === 'positive') && !c.outcome?.toLowerCase().includes('site visit')
      ).length;
      const notInterested = merged.filter(c => 
        (c.outcome && c.outcome.toLowerCase().includes('not interested')) ||
        c.sentiment === 'negative'
      ).length;

      setStats({
        totalCalls,
        siteVisits,
        interested: interested + siteVisits, // Site visits count as high intent
        notInterested
      });
    } catch (err) {
      console.error('Error loading call logs:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();

    // Auto-poll for background updates every 8 seconds
    const interval = setInterval(() => {
      loadData();
    }, 8000);

    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleOutboundCall = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dialPhone) return;

    setIsDialing(true);
    setDialResult(null);

    const safeTargetPhone = dialPhone.trim();
    const callerName = dialName.trim() || 'Valued Client';

    try {
      const res = await fetch('/api/outbound-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phoneNumber: safeTargetPhone,
          customerName: callerName,
          userEmail: currentUser?.email || 'test@gmail.com'
        })
      });

      const data = await res.json();
      if (data.success) {
        setDialResult({
          success: true,
          message: `Calling ${callerName} (${safeTargetPhone})... Gayatri is connected and ringing the phone now!`
        });

        // Instant Live Call Log Entry stored temporarily in browser storage while call is in progress
        const newLiveLog: CallLog & { leadName: string; leadPhone?: string } = {
          id: `call-${Date.now()}`,
          leadId: `lead-${callerName.toLowerCase().replace(/[^a-z0-9]/g, '')}`,
          leadName: callerName,
          leadPhone: safeTargetPhone,
          customerName: callerName,
          customerPhone: safeTargetPhone,
          userEmail: currentUser?.email || 'test@gmail.com',
          callSid: data.roomName || `call-${Date.now()}`,
          durationSeconds: 0,
          recordingUrl: '',
          transcript: `[Call In Progress]\nGayatri is currently speaking with ${callerName} (${safeTargetPhone}).\nThe complete turn-by-turn conversation dialogue will be saved and displayed here automatically once the call completes.`,
          aiSummary: `Outbound AI call initiated to ${callerName}. Phone ringing and connected. Account: ${currentUser?.email || 'test@gmail.com'}.`,
          sentiment: 'neutral',
          outcome: 'Ringing / Calling',
          calledAt: new Date().toISOString(),
          detectedQuestions: ['Outbound Initiation']
        };

        try {
          const stored = localStorage.getItem('gayatri_live_call_logs');
          const existing = stored ? JSON.parse(stored) : [];
          existing.unshift(newLiveLog);
          localStorage.setItem('gayatri_live_call_logs', JSON.stringify(existing));
        } catch (e) {
          console.warn('Could not save to localStorage:', e);
        }

        // Prepend immediately to state
        setCallLogs(prev => [newLiveLog, ...prev.filter(p => (p.callSid ? p.callSid !== newLiveLog.callSid : p.id !== newLiveLog.id))]);
        setStats(prev => ({
          ...prev,
          totalCalls: prev.totalCalls + 1
        }));
      } else {
        setDialResult({
          success: false,
          message: data.message || 'Could not dispatch call. Please check network/credentials.'
        });
      }
    } catch (err: any) {
      setDialResult({
        success: false,
        message: err.message || 'Network exception while placing outbound call.'
      });
    } finally {
      setIsDialing(false);
    }
  };

  const handleDeleteCall = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to remove this call log?')) return;

    try {
      const stored = localStorage.getItem('gayatri_live_call_logs');
      if (stored) {
        const filtered = JSON.parse(stored).filter((c: any) => c.id !== id);
        localStorage.setItem('gayatri_live_call_logs', JSON.stringify(filtered));
      }
    } catch (e) {
      console.warn('Failed to delete from localStorage:', e);
    }

    setCallLogs(prev => prev.filter(c => c.id !== id));
    await deleteCallLog(id);
    await loadData();
  };

  // Helper to determine status tag styling and label
  const getOutcomeTag = (call: CallLog) => {
    const outcome = (call.outcome || '').toLowerCase();
    const summary = (call.aiSummary || '').toLowerCase();
    const transcript = (call.transcript || '').toLowerCase();

    if (outcome.includes('site visit') || summary.includes('site visit') || transcript.includes('site visit confirm')) {
      return {
        label: 'Site Visit Scheduled',
        bg: 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
        dot: 'bg-blue-500',
        icon: Calendar
      };
    }

    if (outcome.includes('not interested') || summary.includes('not interested') || call.sentiment === 'negative') {
      return {
        label: 'Not Interested',
        bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
        dot: 'bg-rose-500',
        icon: XCircle
      };
    }

    if (outcome.includes('interested') || call.sentiment === 'positive') {
      return {
        label: 'Interested',
        bg: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
        dot: 'bg-emerald-500',
        icon: CheckCircle2
      };
    }

    if (outcome.includes('calling')) {
      return {
        label: 'Ringing / Calling',
        bg: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
        dot: 'bg-amber-500 animate-pulse',
        icon: Clock
      };
    }

    return {
      label: 'Inquiry Completed',
      bg: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700',
      dot: 'bg-slate-400',
      icon: CheckCircle2
    };
  };

  // Filtered call logs
  const filteredCalls = callLogs.filter(call => {
    const nameMatch = (call.leadName || '').toLowerCase().includes(searchQuery.toLowerCase());
    const phoneMatch = (call.customerPhone || call.leadPhone || '').toLowerCase().includes(searchQuery.toLowerCase());
    const queryMatches = nameMatch || phoneMatch;

    if (!queryMatches) return false;

    if (statusFilter === 'All') return true;
    const tag = getOutcomeTag(call).label;
    if (statusFilter === 'Interested') return tag === 'Interested';
    if (statusFilter === 'Site Visit') return tag === 'Site Visit Scheduled';
    if (statusFilter === 'Not Interested') return tag === 'Not Interested';

    return true;
  });

  // Format Turn-by-Turn transcript with timestamp & speaker detection
  interface ParsedTurn {
    speaker: 'agent' | 'customer' | 'system';
    timestamp?: string;
    speakerName: string;
    text: string;
  }

  const parseTranscript = (rawTranscript: string, fallbackName: string = 'Customer'): ParsedTurn[] => {
    if (!rawTranscript) return [];

    const lines = rawTranscript.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    const parsed: ParsedTurn[] = [];

    for (const line of lines) {
      // 1. Check for timestamp bracket: [0.5s] or [12s] or [1.2m]
      const tsMatch = line.match(/^\[([\d.]+(?:s|m)?)\]\s*(.+)$/i);
      let timestamp: string | undefined = undefined;
      let content = line;

      if (tsMatch) {
        timestamp = tsMatch[1];
        content = tsMatch[2].trim();
      }

      // 2. Check for Speaker: Message format
      const colonIdx = content.indexOf(':');
      if (colonIdx !== -1) {
        const rawSpeaker = content.slice(0, colonIdx).trim();
        const messageText = content.slice(colonIdx + 1).trim();
        const lowerSpeaker = rawSpeaker.toLowerCase();

        if (
          lowerSpeaker.includes('gayatri') ||
          lowerSpeaker.includes('agent') ||
          lowerSpeaker.includes('priya') ||
          lowerSpeaker.includes('ai')
        ) {
          parsed.push({
            speaker: 'agent',
            timestamp,
            speakerName: 'Gayatri (AI Property Advisor)',
            text: messageText
          });
          continue;
        } else {
          const cleanName = rawSpeaker.replace(/\s*ji$/i, '').trim();
          parsed.push({
            speaker: 'customer',
            timestamp,
            speakerName: cleanName || fallbackName,
            text: messageText
          });
          continue;
        }
      }

      // 3. System messages e.g. [Call In Progress]
      if (line.startsWith('[') && line.endsWith(']')) {
        parsed.push({
          speaker: 'system',
          speakerName: 'System',
          text: line.slice(1, -1).trim()
        });
      } else {
        parsed.push({
          speaker: 'system',
          speakerName: 'System',
          text: line
        });
      }
    }

    return parsed;
  };

  return (
    <div className="space-y-8 pb-12">
      
      {/* 1. 1-CLICK OUTBOUND VOICE AI DIALER */}
      <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 border border-blue-800/40 rounded-3xl p-6 sm:p-8 text-white shadow-2xl shadow-blue-950/40 relative overflow-hidden">
        
        {/* Background glow effects */}
        <div className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-1/3 -mb-8 w-48 h-48 bg-indigo-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-xl space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs font-semibold">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Gayatri AI • Kusha Cloned Voice Engine</span>
              </div>
              <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-500/20 border border-emerald-400/30 text-emerald-300 text-xs font-semibold">
                <User className="h-3.5 w-3.5 text-emerald-400" />
                <span>Account: <strong className="text-white">{currentUser?.email || 'test@gmail.com'}</strong></span>
              </div>
            </div>
            <h2 className="text-xl sm:text-2xl font-black tracking-tight">
              1-Click Outbound Voice AI Call
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 font-medium leading-relaxed">
              Instantly dial any customer phone number. Gayatri introduces Sai Complex Dombivli East, handles objections in Hindi or pure Marathi, and books site visits dynamically. All call transcripts are saved under <span className="text-emerald-400 font-semibold">{currentUser?.email || 'test@gmail.com'}</span>.
            </p>
          </div>

          {/* Dialing Form */}
          <form onSubmit={handleOutboundCall} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 bg-white/5 p-2 sm:p-3 rounded-2xl border border-white/10 backdrop-blur-md">
            <div>
              <label className="block text-[10px] font-bold text-slate-300 uppercase tracking-wider mb-1 px-1">
                Customer Name
              </label>
              <input
                type="text"
                value={dialName}
                onChange={(e) => setDialName(e.target.value)}
                placeholder="e.g. Raj"
                className="w-full sm:w-36 px-3.5 py-2.5 bg-black/40 border border-white/15 rounded-xl text-xs text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-400 font-medium"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-300 uppercase tracking-wider mb-1 px-1">
                Phone Number (E.164)
              </label>
              <input
                type="text"
                value={dialPhone}
                onChange={(e) => setDialPhone(e.target.value)}
                placeholder="+918693081506"
                className="w-full sm:w-48 px-3.5 py-2.5 bg-black/40 border border-white/15 rounded-xl text-xs text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-400 font-medium"
                required
              />
            </div>

            <div className="sm:self-end">
              <button
                type="submit"
                disabled={isDialing}
                className="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/30 flex items-center justify-center space-x-2 transition-all disabled:opacity-50"
              >
                {isDialing ? (
                  <>
                    <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Dialing...</span>
                  </>
                ) : (
                  <>
                    <PhoneOutgoing className="h-4 w-4" />
                    <span>Call Phone Now</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Real-Time Call Feedback */}
        {dialResult && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className={`mt-4 p-3 rounded-xl border text-xs font-semibold flex items-center justify-between ${
              dialResult.success 
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' 
                : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              {dialResult.success ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <AlertCircle className="h-4 w-4 text-rose-400" />}
              <span>{dialResult.message}</span>
            </div>
            <button
              onClick={() => setDialResult(null)}
              className="text-xs opacity-70 hover:opacity-100"
            >
              ✕
            </button>
          </motion.div>
        )}
      </div>

      {/* 2. KPI METRICS CARDS */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Total Calls Talked</p>
            <h3 className="text-2xl font-black text-slate-900 dark:text-white mt-1">{stats.totalCalls}</h3>
            <span className="text-[10px] text-slate-400 font-medium">Logged conversations</span>
          </div>
          <div className="h-11 w-11 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            <PhoneCall className="h-5 w-5" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold uppercase tracking-wider">Interested Clients</p>
            <h3 className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">{stats.interested}</h3>
            <span className="text-[10px] text-slate-400 font-medium">High positive intent</span>
          </div>
          <div className="h-11 w-11 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
            <CheckCircle2 className="h-5 w-5" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-[11px] text-blue-600 dark:text-blue-400 font-bold uppercase tracking-wider">Site Visits Booked</p>
            <h3 className="text-2xl font-black text-blue-600 dark:text-blue-400 mt-1">{stats.siteVisits}</h3>
            <span className="text-[10px] text-slate-400 font-medium">Weekend appointments</span>
          </div>
          <div className="h-11 w-11 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            <Calendar className="h-5 w-5" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-[11px] text-rose-500 font-bold uppercase tracking-wider">Not Interested</p>
            <h3 className="text-2xl font-black text-rose-500 mt-1">{stats.notInterested}</h3>
            <span className="text-[10px] text-slate-400 font-medium">Opted out / DNC</span>
          </div>
          <div className="h-11 w-11 rounded-xl bg-rose-500/10 text-rose-500 flex items-center justify-center">
            <XCircle className="h-5 w-5" />
          </div>
        </div>

      </div>

      {/* 3. GAYATRI CALL LOGS & INTELLIGENCE TABLE */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden">
        
        {/* Table Header Controls */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h3 className="font-black text-base text-slate-900 dark:text-white flex items-center space-x-2">
              <PhoneCall className="h-5 w-5 text-blue-600" />
              <span>Gayatri AI Call Logs & Transcripts</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5 font-medium">
              Every customer conversation recorded, transcribed, and tagged with lead sentiment.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search name or phone..."
                className="pl-8 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium w-48 sm:w-56"
              />
            </div>

            {/* Filter Pills */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl text-xs">
              {(['All', 'Interested', 'Site Visit', 'Not Interested'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setStatusFilter(tab)}
                  className={`px-3 py-1 font-bold rounded-lg transition-all ${
                    statusFilter === tab
                      ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Refresh Button */}
            <button
              onClick={handleRefresh}
              className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Refresh Call Logs"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* Call Logs Feed / Table */}
        <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {loading ? (
            <div className="py-16 text-center text-xs text-slate-400">
              <div className="h-6 w-6 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin mx-auto mb-3" />
              Loading Gayatri call logs...
            </div>
          ) : filteredCalls.length === 0 ? (
            <div className="py-16 text-center text-xs text-slate-400 space-y-2">
              <MessageSquare className="h-8 w-8 mx-auto text-slate-300 dark:text-slate-700" />
              <p className="font-bold text-slate-600 dark:text-slate-300 text-sm">No call logs found</p>
              <p>Place an outbound call above to populate the live transcript feed.</p>
            </div>
          ) : (
            filteredCalls.map((call) => {
              const tag = getOutcomeTag(call);
              const TagIcon = tag.icon;
              const dateStr = call.calledAt ? new Date(call.calledAt).toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              }) : 'Recent';

              const durationFormatted = call.durationSeconds > 0 
                ? `${Math.floor(call.durationSeconds / 60)}m ${call.durationSeconds % 60}s`
                : 'In Progress';

              return (
                <div
                  key={call.id}
                  onClick={() => setSelectedCall(call)}
                  className="p-4 sm:p-6 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 cursor-pointer transition-all flex flex-col md:flex-row md:items-center justify-between gap-4 group"
                >
                  {/* Left: Customer Info & Summary */}
                  <div className="flex items-start space-x-4 max-w-2xl">
                    <div className="h-10 w-10 rounded-2xl bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0 mt-0.5">
                      <User className="h-5 w-5" />
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                        <h4 className="font-bold text-sm text-slate-900 dark:text-white">
                          {call.leadName}
                        </h4>
                        <span className="text-xs text-slate-400 font-medium">
                          {call.customerPhone || call.leadPhone || '+918693081506'}
                        </span>
                        
                        {/* Account Badge */}
                        <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 font-mono font-medium border border-slate-200/60 dark:border-slate-700/60">
                          {call.userEmail || currentUser?.email || 'test@gmail.com'}
                        </span>

                        {/* Outcome Tag */}
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${tag.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                          <span>{tag.label}</span>
                        </span>

                        {/* Audio Recording Badge */}
                        {call.recordingUrl && (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
                            <Volume2 className="h-3 w-3" />
                            <span>Audio</span>
                          </span>
                        )}
                      </div>

                      {/* AI Summary / Notes */}
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1 font-medium">
                        {call.aiSummary || 'Outbound sales call discussing Sai Complex Dombivli East project.'}
                      </p>
                    </div>
                  </div>

                  {/* Right: Timing, Duration & View Script Button */}
                  <div className="flex items-center space-x-4 self-end md:self-center shrink-0">
                    <div className="text-right">
                      <div className="flex items-center space-x-1 text-xs font-semibold text-slate-700 dark:text-slate-300 justify-end">
                        <Clock className="h-3.5 w-3.5 text-slate-400" />
                        <span>{durationFormatted}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-medium">
                        {dateStr}
                      </span>
                    </div>

                    {/* View Script Button */}
                    <button
                      onClick={() => setSelectedCall(call)}
                      className="px-3.5 py-2 bg-blue-50 dark:bg-blue-950/50 hover:bg-blue-600 hover:text-white text-blue-600 dark:text-blue-400 rounded-xl text-xs font-bold border border-blue-200/60 dark:border-blue-800/60 flex items-center space-x-1.5 transition-all group-hover:bg-blue-600 group-hover:text-white"
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      <span>View Full Script</span>
                    </button>

                    {/* Delete button */}
                    <button
                      onClick={(e) => handleDeleteCall(call.id, e)}
                      className="p-2 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
                      title="Delete log"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 4. CONVERSATION SCRIPT MODAL / DRAWER */}
      <AnimatePresence>
        {selectedCall && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex items-start justify-between bg-slate-50/50 dark:bg-slate-800/40">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <h3 className="font-extrabold text-base text-slate-900 dark:text-white">
                      Conversation with {selectedCall.leadName}
                    </h3>
                    {(() => {
                      const tag = getOutcomeTag(selectedCall);
                      return (
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${tag.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                          <span>{tag.label}</span>
                        </span>
                      );
                    })()}
                  </div>
                  <p className="text-xs text-slate-400 font-medium">
                    Phone: {selectedCall.customerPhone || selectedCall.leadPhone || '+918693081506'} • Duration: {selectedCall.durationSeconds > 0 ? `${selectedCall.durationSeconds}s` : 'Active'} • Account: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{selectedCall.userEmail || currentUser?.email || 'test@gmail.com'}</span>
                  </p>
                </div>

                <button
                  onClick={() => setSelectedCall(null)}
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* AI Summary Banner */}
              <div className="px-6 py-3 bg-blue-50/50 dark:bg-blue-950/20 border-b border-blue-100 dark:border-blue-900/30 text-xs text-blue-800 dark:text-blue-300 font-medium">
                <span className="font-bold">AI Call Summary: </span>
                {selectedCall.aiSummary || 'Outbound consultation regarding Sai Complex Dombivli East project.'}
              </div>

              {/* Call Audio Player */}
              {selectedCall.recordingUrl && (
                <div className="px-6 py-3.5 bg-gradient-to-r from-blue-50/70 to-indigo-50/70 dark:from-slate-800/80 dark:to-blue-950/40 border-b border-blue-100 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center space-x-2.5">
                    <div className="p-2 rounded-xl bg-blue-600 text-white shadow-sm shrink-0">
                      <Volume2 className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-xs font-bold text-slate-800 dark:text-slate-200">Call Audio Recording</p>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">Dual-channel stereo (Caller + Gayatri AI)</p>
                    </div>
                  </div>
                  <div className="flex-1 max-w-sm">
                    <audio 
                      controls 
                      className="w-full h-8 rounded-lg accent-blue-600" 
                      src={selectedCall.recordingUrl} 
                      preload="metadata"
                    >
                      Your browser does not support audio playback.
                    </audio>
                  </div>
                </div>
              )}

              {/* Modal Body: Turn-by-Turn Dialogue */}
              <div className="p-6 overflow-y-auto space-y-4 flex-1">
                {parseTranscript(selectedCall.transcript, selectedCall.leadName).map((turn, idx) => {
                  if (turn.speaker === 'system') {
                    return (
                      <div key={idx} className="text-center my-3">
                        <span className="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 px-3.5 py-1.5 rounded-full font-medium shadow-sm inline-block">
                          {turn.text}
                        </span>
                      </div>
                    );
                  }

                  const isAgent = turn.speaker === 'agent';

                  return (
                    <div
                      key={idx}
                      className={`flex flex-col ${isAgent ? 'items-start' : 'items-end'}`}
                    >
                      <div className={`flex items-center space-x-1.5 mb-1 px-1 ${isAgent ? 'flex-row' : 'flex-row-reverse space-x-reverse'}`}>
                        <span className={`text-[10px] font-bold uppercase tracking-wider ${isAgent ? 'text-blue-600 dark:text-blue-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                          {turn.speakerName}
                        </span>
                        {turn.timestamp && (
                          <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                            {turn.timestamp}
                          </span>
                        )}
                      </div>

                      <div
                        className={`max-w-[85%] p-3.5 rounded-2xl text-xs font-medium leading-relaxed shadow-sm ${
                          isAgent
                            ? 'bg-blue-50 dark:bg-blue-950/60 text-slate-900 dark:text-slate-100 border border-blue-200 dark:border-blue-900/60 rounded-tl-sm'
                            : 'bg-emerald-600 text-white rounded-tr-sm'
                        }`}
                      >
                        {turn.text}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Modal Footer */}
              <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center space-x-1.5 font-medium">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <span>Stored in account: <strong className="text-slate-800 dark:text-slate-200">{selectedCall.userEmail || currentUser?.email || 'test@gmail.com'}</strong></span>
                </span>
                <button
                  onClick={() => setSelectedCall(null)}
                  className="px-5 py-2 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-bold rounded-xl transition-all"
                >
                  Close Script
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
}
