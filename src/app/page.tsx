'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import * as XLSX from 'xlsx';
import { 
  getCallLogsWithLeads, 
  getColdCallingStats,
  deleteCallLog 
} from '@/app/actions';
import { CallLog } from '@/lib/types';
import { getCallTimestampMs, getCallPickedInfo, formatCallDuration } from '@/lib/callUtils';
import { 
  PhoneCall, 
  PhoneOutgoing, 
  PhoneOff,
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
  Download, 
  Upload, 
  List, 
  Play, 
  Pause, 
  Square, 
  Copy, 
  Check, 
  FileSpreadsheet, 
  FileText, 
  ChevronDown, 
  ChevronUp, 
  BarChart3, 
  CalendarDays, 
  MapPin, 
  AlertTriangle,
  RotateCcw,
  Trash2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { exportLeadsToPdf, PdfReportCategory } from '@/lib/pdfExport';

// Helper to determine status tag styling and label with strict 3-category precedence
export const getOutcomeTag = (call: CallLog) => {
  const outcome = (call.outcome || '').toLowerCase();
  const summary = (call.aiSummary || '').toLowerCase();
  const transcript = (call.transcript || '').toLowerCase();

  // 1. In-progress ringing / calling
  if (outcome.includes('calling') || outcome.includes('ringing')) {
    return {
      label: 'Calling / Ringing',
      bg: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
      dot: 'bg-amber-500 animate-pulse',
      icon: Clock
    };
  }

  // 2. Not Interested (Declined, rejected, location mismatch, negative sentiment, or unanswered)
  const isNotInterested = 
    outcome.includes('not interested') || 
    outcome.includes('declined') ||
    outcome.includes('rejected') ||
    outcome.includes('nahi chahiye') ||
    outcome.includes('location mismatch') ||
    outcome.includes('not picked') ||
    outcome.includes('unanswered') ||
    outcome.includes('missed') ||
    call.sentiment === 'negative';

  if (isNotInterested) {
    return {
      label: 'Not Interested',
      bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
      dot: 'bg-rose-500',
      icon: XCircle
    };
  }

  // 3. Site Visit (Confirmed appointment)
  const isSiteVisit = 
    outcome.includes('site visit') || 
    summary.includes('confirmed site visit') ||
    summary.includes('scheduled site visit') ||
    summary.includes('site visit confirmed') ||
    transcript.includes('site visit confirm');

  if (isSiteVisit) {
    return {
      label: 'Site Visit',
      bg: 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
      dot: 'bg-blue-500',
      icon: Calendar
    };
  }

  // 4. Interested (All positive intent, pricing, brochure, and future plans/follow-ups)
  return {
    label: 'Interested',
    bg: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
    dot: 'bg-emerald-500',
    icon: CheckCircle2
  };
};

export const getSentimentTag = (call: CallLog) => {
  const sentiment = (call.sentiment || '').toLowerCase();
  if (sentiment === 'positive') {
    return {
      label: 'Positive',
      bg: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
      dot: 'bg-emerald-500',
      emoji: '😊'
    };
  }
  if (sentiment === 'negative') {
    return {
      label: 'Negative',
      bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
      dot: 'bg-rose-500',
      emoji: '😟'
    };
  }
  return {
    label: 'Neutral',
    bg: 'bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700',
    dot: 'bg-slate-400',
    emoji: '😐'
  };
};

// Types for Concurrent Batch Dialer
type CampaignContact = { name: string; phone: string };
type CampaignEntry = CampaignContact & { 
  status: 'queued' | 'calling' | 'done' | 'error'; 
  error?: string; 
  callSid?: string;
  durationSeconds?: number;
};

type LiveSlot = {
  slotId: 1 | 2;
  contactName: string;
  phoneNumber: string;
  status: 'idle' | 'calling' | 'connected' | 'completed' | 'error';
  elapsedSeconds: number;
  callSid?: string;
  error?: string;
};

export default function ColdCallingHomePage() {
  const [callLogs, setCallLogs] = useState<(CallLog & { leadName: string; leadPhone?: string })[]>([]);
  const [stats, setStats] = useState({ totalCalls: 0, siteVisits: 0, interested: 0, notInterested: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Locked 1.0x Voice Speed (No UI slider, locked permanently)
  const voiceSpeed = 1.0;

  // Analytics Period Filter State
  const [analyticsPeriod, setAnalyticsPeriod] = useState<'all' | 'today' | 'week' | 'month' | 'year'>('all');

  // 1-Click Dialing Form State
  const [dialName, setDialName] = useState('Raj');
  const [dialPhone, setDialPhone] = useState('+918693081506');
  const [isDialing, setIsDialing] = useState(false);
  const [isTerminating, setIsTerminating] = useState(false);
  const [dialResult, setDialResult] = useState<{ success: boolean; message: string } | null>(null);

  // ── Batch Campaign State ──
  const [batchContacts, setBatchContacts] = useState<CampaignEntry[]>([]);
  const [campaignRunning, setCampaignRunning] = useState(false);
  const [campaignPaused, setCampaignPaused] = useState(false);
  const [campaignAlert, setCampaignAlert] = useState<string | null>(null);
  const [manualList, setManualList] = useState('');
  const [showManualPaste, setShowManualPaste] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // References to control asynchronous worker loop safely
  const campaignStopRef = useRef(false);
  const campaignPauseRef = useRef(false);
  const batchContactsRef = useRef<CampaignEntry[]>([]);
  batchContactsRef.current = batchContacts;

  // Real-Time Active Live Call Slots (2 Concurrent Channels)
  const [activeSlots, setActiveSlots] = useState<{ 1: LiveSlot; 2: LiveSlot }>({
    1: { slotId: 1, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 },
    2: { slotId: 2, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 },
  });

  // Timer interval for updating active call elapsed seconds in real-time
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveSlots(prev => {
        let changed = false;
        const next = { ...prev };
        for (const slotKey of [1, 2] as const) {
          if (next[slotKey].status === 'calling' || next[slotKey].status === 'connected') {
            next[slotKey] = { ...next[slotKey], elapsedSeconds: next[slotKey].elapsedSeconds + 1 };
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Search & Filter State (Strictly 3 outcome categories)
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Interested' | 'Site Visit' | 'Not Interested'>('All');

  // Visit Schedule Dropdown / Collapsible State
  const [isVisitScheduleOpen, setIsVisitScheduleOpen] = useState(true);

  // Selected Call Log for Verbatim Modal Transcript
  const [selectedCall, setSelectedCall] = useState<(CallLog & { leadName: string; leadPhone?: string }) | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);

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

  // PDF Export Dropdown State
  const [pdfMenuOpen, setPdfMenuOpen] = useState(false);
  const pdfDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (pdfDropdownRef.current && !pdfDropdownRef.current.contains(event.target as Node)) {
        setPdfMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Analytics Period Filtering
  const filteredCallsForAnalytics = useMemo(() => {
    if (analyticsPeriod === 'all') return callLogs;
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    
    // Start of week (Monday)
    const dayOfWeek = now.getDay();
    const diffToMonday = (dayOfWeek === 0 ? -6 : 1) - dayOfWeek;
    const weekStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diffToMonday).getTime();
    
    // Start of month
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
    
    // Start of year
    const yearStart = new Date(now.getFullYear(), 0, 1).getTime();

    return callLogs.filter(c => {
      const callMs = getCallTimestampMs(c);
      if (analyticsPeriod === 'today') return callMs >= todayStart;
      if (analyticsPeriod === 'week') return callMs >= weekStart;
      if (analyticsPeriod === 'month') return callMs >= monthStart;
      if (analyticsPeriod === 'year') return callMs >= yearStart;
      return true;
    });
  }, [callLogs, analyticsPeriod]);

  // Strictly 3 Categories (+ Total)
  const periodStats = useMemo(() => {
    const totalCalls = filteredCallsForAnalytics.length;
    let siteVisits = 0;
    let interested = 0;
    let notInterested = 0;

    for (const call of filteredCallsForAnalytics) {
      const tag = getOutcomeTag(call).label;
      if (tag === 'Site Visit') {
        siteVisits++;
      } else if (tag === 'Interested') {
        interested++;
      } else if (tag === 'Not Interested') {
        notInterested++;
      }
    }

    return {
      totalCalls,
      siteVisits,
      interested,
      notInterested
    };
  }, [filteredCallsForAnalytics]);

  // Extract confirmed site visits & arrange chronologically (nearest upcoming at top)
  const siteVisits = useMemo(() => {
    const visits: {
      id: string;
      customerName: string;
      customerPhone: string;
      day: string;
      time: string;
      flatType: string;
      status: string;
      createdAt?: string;
      scheduledDateMs: number;
      displayDate: string;
      summary: string;
      originalCall: (CallLog & { leadName: string; leadPhone?: string });
    }[] = [];

    const visitCalls = filteredCallsForAnalytics.filter(c => {
      const tag = getOutcomeTag(c);
      return tag.label === 'Site Visit' || 
             (c.aiSummary && c.aiSummary.toLowerCase().includes('site visit')) ||
             (c.transcript && c.transcript.toLowerCase().includes('site visit'));
    });

    const now = new Date();

    for (const c of visitCalls) {
      const text = ((c.aiSummary || '') + ' ' + (c.transcript || '')).toLowerCase();
      
      let day = 'Saturday';
      let dayOffset = 5; // default ahead
      if (text.includes('sunday') || text.includes('ravivar') || text.includes('raviwar') || text.includes('रविवार')) {
        day = 'Sunday';
        dayOffset = 6;
      } else if (text.includes('saturday') || text.includes('shanivar') || text.includes('shaniwar') || text.includes('शनिवार')) {
        day = 'Saturday';
        dayOffset = 5;
      } else if (text.includes('friday') || text.includes('shukravar') || text.includes('शुक्रवार')) {
        day = 'Friday';
        dayOffset = 4;
      } else if (text.includes('tomorrow') || text.includes('udya') || text.includes('उद्या') || text.includes('kal')) {
        day = 'Tomorrow';
        dayOffset = 1;
      }

      let time = '11:00 AM';
      let hour = 11;
      let minute = 0;
      if (text.includes('4 pm') || text.includes('4 baje') || text.includes('4:00') || text.includes('shaam') || text.includes('संध्याकाळी') || text.includes('evening')) {
        time = '4:00 PM';
        hour = 16;
      } else if (text.includes('3 pm') || text.includes('3 baje')) {
        time = '3:00 PM';
        hour = 15;
      } else if (text.includes('11') || text.includes('subah') || text.includes('सकाळी') || text.includes('morning')) {
        time = '11:00 AM';
        hour = 11;
      }

      let flatType = '1 BHK / 2 BHK';
      if (text.includes('2 bhk') || text.includes('2bhk') || text.includes('दोन') || text.includes('don bhk') || text.includes('two')) {
        flatType = '2 BHK (₹45L)';
      } else if (text.includes('1 bhk') || text.includes('1bhk') || text.includes('एक') || text.includes('one')) {
        flatType = '1 BHK (₹30L)';
      }

      const name = c.customerName || c.leadName || 'Interested Buyer';
      const phone = c.customerPhone || c.leadPhone || '';
      const summary = c.aiSummary || 'Site visit confirmed for Sai Garden project.';

      // Calculate scheduled date timestamp for sorting
      const callDate = new Date(c.calledAt || (c as any).createdAt || Date.now());
      const scheduledDate = new Date(callDate);
      scheduledDate.setDate(callDate.getDate() + (day === 'Tomorrow' ? 1 : 2));
      scheduledDate.setHours(hour, minute, 0, 0);

      const scheduledDateMs = scheduledDate.getTime();
      const displayDate = `${day}, ${scheduledDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} at ${time}`;

      visits.push({
        id: c.callSid || c.id || String(Math.random()),
        customerName: name,
        customerPhone: phone,
        day,
        time,
        flatType,
        status: 'Confirmed Visit',
        createdAt: (c as any).createdAt || c.calledAt || new Date().toISOString(),
        scheduledDateMs,
        displayDate,
        summary,
        originalCall: c
      });
    }

    // Sort: schedule closest to current date at the top
    visits.sort((a, b) => a.scheduledDateMs - b.scheduledDateMs);

    return visits;
  }, [filteredCallsForAnalytics]);

  const handleDownloadPdf = (category: PdfReportCategory) => {
    setPdfMenuOpen(false);
    exportLeadsToPdf({
      category,
      calls: filteredCallsForAnalytics,
      getOutcomeTag,
      userEmail: currentUser?.email || 'test@gmail.com',
    });
  };

  const loadData = async () => {
    try {
      let [serverLogs, statsData] = await Promise.all([
        getCallLogsWithLeads(),
        getColdCallingStats()
      ]);

      try {
        const apiRes = await fetch(`/api/webhooks/voice-agent?t=${Date.now()}`, {
          cache: 'no-store',
          headers: { 'Cache-Control': 'no-cache' }
        });
        if (apiRes.ok) {
          const apiData = await apiRes.json();
          if (apiData.callLogs && Array.isArray(apiData.callLogs)) {
            const existingKeys = new Set(serverLogs.map(l => l.callSid || l.id));
            for (const log of apiData.callLogs) {
              const k = log.callSid || log.id;
              if (!existingKeys.has(k)) {
                serverLogs.push(log);
                existingKeys.add(k);
              } else {
                const exIdx = serverLogs.findIndex(l => (l.callSid || l.id) === k);
                if (exIdx >= 0) {
                  const currentTranscript = serverLogs[exIdx].transcript || '';
                  const newTranscript = log.transcript || '';
                  const isServerInProgress = serverLogs[exIdx].outcome === 'Calling...' || serverLogs[exIdx].outcome === 'Ringing / Calling' || currentTranscript.includes('[Call In Progress]');
                  if (isServerInProgress || newTranscript.length >= currentTranscript.length) {
                    serverLogs[exIdx] = { ...serverLogs[exIdx], ...log };
                  }
                }
              }
            }
          }
        }
      } catch (apiErr) {
        console.warn('Could not fetch from /api/webhooks/voice-agent:', apiErr);
      }

      // Read preserved call history from local storage as backup
      let permanentHistory: (CallLog & { leadName: string; leadPhone?: string })[] = [];
      try {
        const stored = localStorage.getItem('gayatri_permanent_history');
        if (stored) {
          permanentHistory = JSON.parse(stored).filter((item: any) => {
            if (!item) return false;
            const sid = (item.callSid || item.id || '').toLowerCase();
            if (sid.includes('probe') || sid === 'gayatri-persistent-storage') return false;
            return true;
          });
        }
      } catch (err) {
        console.warn('Could not read permanent call history:', err);
      }

      // Merge server and local history: Server + permanent ledger are source of truth
      const map = new Map<string, CallLog & { leadName: string; leadPhone?: string }>();
      const nowMs = Date.now();

      for (const item of serverLogs) {
        if (!item || item.callSid === 'gayatri-persistent-storage') continue;
        const sid = (item.callSid || item.id || '').toLowerCase();
        if (sid.includes('probe')) continue;
        map.set(item.callSid || item.id, item);
      }

      for (const localItem of permanentHistory) {
        if (!localItem || localItem.callSid === 'gayatri-persistent-storage') continue;
        const key = localItem.callSid || localItem.id;
        if (!map.has(key)) {
          map.set(key, localItem);
        }
      }

      // Mark timed out ringing calls (> 75s) as unanswered
      for (const [key, item] of map.entries()) {
        const isCallingState = item.outcome === 'Ringing / Calling' || item.outcome === 'Calling...';
        if (isCallingState) {
          const itemTime = getCallTimestampMs(item);
          const callAgeSeconds = itemTime > 0 ? (nowMs - itemTime) / 1000 : 999;
          if (callAgeSeconds > 75) {
            item.outcome = 'Not Picked Up';
            item.durationSeconds = item.durationSeconds || 0;
            if (!item.transcript || item.transcript.includes('[Call In Progress]')) {
              item.transcript = '[Call was unanswered or disconnected before conversation started]';
            }
            if (!item.aiSummary || item.aiSummary.includes('Calling') || item.aiSummary.includes('ringing')) {
              item.aiSummary = 'Customer did not answer or call was disconnected before conversation.';
            }
            map.set(key, item);
          }
        }
      }

      const merged = Array.from(map.values()).sort(
        (a, b) => getCallTimestampMs(b) - getCallTimestampMs(a)
      );

      // Persist full verbatim call ledger in browser storage
      try {
        localStorage.setItem('gayatri_permanent_history', JSON.stringify(merged));
      } catch (err) {
        console.warn('Could not persist permanent call history:', err);
      }

      setCallLogs(merged);

      // Keep selected transcript modal synced in real-time
      if (selectedCall) {
        const updated = merged.find(c => (c.callSid && c.callSid === selectedCall.callSid) || c.id === selectedCall.id);
        if (updated && (
          updated.transcript !== selectedCall.transcript || 
          updated.outcome !== selectedCall.outcome || 
          updated.aiSummary !== selectedCall.aiSummary
        )) {
          setSelectedCall(updated);
        }
      }

      // Calculate strict 3-category KPIs
      const totalCalls = merged.length;
      let siteVisits = 0;
      let interested = 0;
      let notInterested = 0;

      for (const call of merged) {
        const tag = getOutcomeTag(call).label;
        if (tag === 'Site Visit') {
          siteVisits++;
        } else if (tag === 'Interested') {
          interested++;
        } else if (tag === 'Not Interested') {
          notInterested++;
        }
      }

      setStats({
        totalCalls,
        siteVisits,
        interested,
        notInterested
      });
    } catch (err) {
      console.error('Failed to load call logs:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      loadData();
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  // 1-Click Outbound Single Call
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
          userEmail: currentUser?.email || 'test@gmail.com',
          voiceSpeed: 1.0
        })
      });

      const data = await res.json();
      if (data.success) {
        setDialResult({
          success: true,
          message: `Calling ${callerName} (${safeTargetPhone})... Gayatri is connected and ringing the phone now!`
        });

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
          transcript: `[Call In Progress]\nGayatri is currently speaking with ${callerName} (${safeTargetPhone}).\nThe complete verbatim conversation will be saved here automatically once the call completes.`,
          aiSummary: `Outbound AI call initiated to ${callerName}. Phone ringing and connected. Account: ${currentUser?.email || 'test@gmail.com'}.`,
          sentiment: 'neutral',
          outcome: 'Ringing / Calling',
          calledAt: new Date().toISOString(),
          detectedQuestions: ['Outbound Initiation']
        };

        try {
          const stored = localStorage.getItem('gayatri_permanent_history');
          const existing = stored ? JSON.parse(stored) : [];
          existing.unshift(newLiveLog);
          localStorage.setItem('gayatri_permanent_history', JSON.stringify(existing));
        } catch (e) {
          console.warn('Could not save to localStorage:', e);
        }

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

  const handleTerminateAllCalls = async () => {
    if (!confirm('Are you sure you want to terminate all active calls immediately?')) return;

    setIsTerminating(true);
    try {
      const res = await fetch('/api/terminate-calls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (data.success) {
        setDialResult({
          success: true,
          message: data.message || `Terminated active call(s).`
        });
        loadData();
      } else {
        setDialResult({
          success: false,
          message: data.error || 'Failed to terminate active calls.'
        });
      }
    } catch (err: any) {
      setDialResult({
        success: false,
        message: err.message || 'Error connecting to terminate calls API.'
      });
    } finally {
      setIsTerminating(false);
    }
  };

  // ── Batch Campaign Helpers (XLSX, XLS, CSV & Text Upload) ──
  const parseSpreadsheetOrText = async (file: File): Promise<{ name: string; phone: string }[]> => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    const contacts: { name: string; phone: string }[] = [];

    if (ext === 'xlsx' || ext === 'xls') {
      const data = await file.arrayBuffer();
      const workbook = XLSX.read(data, { type: 'array' });
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json<Record<string, any>>(firstSheet);

      for (const row of rows) {
        let name = '';
        let phone = '';

        for (const [key, rawVal] of Object.entries(row)) {
          const k = key.toLowerCase().trim();
          const v = String(rawVal ?? '').trim();
          if (!v) continue;

          // Flexible header matching for Name and Phone
          if (!phone && (k.includes('phone') || k.includes('mobile') || k.includes('number') || k.includes('contact') || k.includes('tel'))) {
            phone = v;
          } else if (!name && (k.includes('name') || k.includes('customer') || k.includes('client') || k.includes('lead'))) {
            name = v;
          }
        }

        // Clean phone number: remove non-digit characters except leading +
        const cleanPhone = phone.replace(/[^\d+]/g, '');
        // Must contain at least 7 digits to be a valid phone number, skip empty rows!
        if (cleanPhone && cleanPhone.replace(/\D/g, '').length >= 7) {
          contacts.push({
            name: name || 'Customer',
            phone: cleanPhone.startsWith('+') ? cleanPhone : (cleanPhone.length === 10 ? `+91${cleanPhone}` : `+${cleanPhone}`)
          });
        }
      }
    } else {
      // Plain CSV or text
      const text = await file.text();
      const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith('#'));
      for (const line of lines) {
        if (/^(name|phone|contact|number|customer|lead)/i.test(line)) continue;
        const parts = line.split(/,/).map(p => p.trim().replace(/^["']|["']$/g, ''));
        if (parts.length >= 2) {
          const isFirstPhone = /^\+?[\d\s\-()]{7,}$/.test(parts[0]);
          const name = isFirstPhone ? (parts[1] || 'Customer') : parts[0];
          const rawPhone = isFirstPhone ? parts[0] : parts[1];
          const cleanPhone = rawPhone.replace(/[^\d+]/g, '');
          if (cleanPhone.replace(/\D/g, '').length >= 7) {
            contacts.push({
              name,
              phone: cleanPhone.startsWith('+') ? cleanPhone : (cleanPhone.length === 10 ? `+91${cleanPhone}` : `+${cleanPhone}`)
            });
          }
        } else if (parts.length === 1) {
          const cleanPhone = parts[0].replace(/[^\d+]/g, '');
          if (cleanPhone.replace(/\D/g, '').length >= 7) {
            contacts.push({
              name: 'Customer',
              phone: cleanPhone.startsWith('+') ? cleanPhone : (cleanPhone.length === 10 ? `+91${cleanPhone}` : `+${cleanPhone}`)
            });
          }
        }
      }
    }

    return contacts;
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const parsed = await parseSpreadsheetOrText(file);
      if (parsed.length > 0) {
        setBatchContacts(parsed.map(c => ({ ...c, status: 'queued' as const })));
        setCampaignAlert(null);
      } else {
        alert('Could not find any valid phone numbers in the uploaded file. Please ensure column contains phone numbers.');
      }
    } catch (err: any) {
      alert(`Error reading file: ${err.message}`);
    }
    if (e.target) e.target.value = '';
  };

  const handleManualListLoad = () => {
    const lines = manualList.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    const parsed: { name: string; phone: string }[] = [];
    for (const line of lines) {
      if (/^(name|phone|contact|number|customer)/i.test(line)) continue;
      const parts = line.split(/,/).map(p => p.trim().replace(/^["']|["']$/g, ''));
      if (parts.length >= 2) {
        const isFirstPhone = /^\+?[\d\s\-()]{7,}$/.test(parts[0]);
        const name = isFirstPhone ? (parts[1] || 'Customer') : parts[0];
        const rawPhone = isFirstPhone ? parts[0] : parts[1];
        const cleanPhone = rawPhone.replace(/[^\d+]/g, '');
        if (cleanPhone.replace(/\D/g, '').length >= 7) {
          parsed.push({
            name,
            phone: cleanPhone.startsWith('+') ? cleanPhone : (cleanPhone.length === 10 ? `+91${cleanPhone}` : `+${cleanPhone}`)
          });
        }
      } else if (parts.length === 1) {
        const cleanPhone = parts[0].replace(/[^\d+]/g, '');
        if (cleanPhone.replace(/\D/g, '').length >= 7) {
          parsed.push({
            name: 'Customer',
            phone: cleanPhone.startsWith('+') ? cleanPhone : (cleanPhone.length === 10 ? `+91${cleanPhone}` : `+${cleanPhone}`)
          });
        }
      }
    }
    if (parsed.length === 0) return;
    setBatchContacts(parsed.map(c => ({ ...c, status: 'queued' as const })));
    setCampaignAlert(null);
  };

  // ── 2 Concurrent Channels Worker Loop with Pause/Resume/Stop Controls ──
  const startCampaign = async () => {
    if (batchContacts.length === 0) return;
    campaignStopRef.current = false;
    campaignPauseRef.current = false;
    setCampaignRunning(true);
    setCampaignPaused(false);
    setCampaignAlert(null);

    const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

    // Worker function for a single concurrent slot (Slot 1 or Slot 2)
    const runSlotWorker = async (slotId: 1 | 2) => {
      while (!campaignStopRef.current) {
        // Handle Paused state: wait until resumed or stopped
        while (campaignPauseRef.current && !campaignStopRef.current) {
          await sleep(500);
        }
        if (campaignStopRef.current) break;

        // Atomically claim next queued contact
        let targetIdx = -1;
        let contactToDial: CampaignEntry | null = null;

        // Find next queued contact index
        const currentList = batchContactsRef.current;
        for (let i = 0; i < currentList.length; i++) {
          if (currentList[i].status === 'queued') {
            targetIdx = i;
            contactToDial = currentList[i];
            break;
          }
        }

        if (targetIdx === -1 || !contactToDial) {
          // No more queued contacts for this worker
          break;
        }

        // Mark contact as calling
        setBatchContacts(prev => prev.map((c, i) => i === targetIdx ? { ...c, status: 'calling' } : c));

        // Update active slot UI
        setActiveSlots(prev => ({
          ...prev,
          [slotId]: {
            slotId,
            contactName: contactToDial!.name,
            phoneNumber: contactToDial!.phone,
            status: 'calling',
            elapsedSeconds: 0,
          }
        }));

        try {
          const res = await fetch('/api/outbound-call', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              phoneNumber: contactToDial.phone,
              customerName: contactToDial.name,
              userEmail: currentUser?.email || 'test@gmail.com',
              voiceSpeed: 1.0
            })
          });

          const data = await res.json();

          // Auto-Pause Watchdog: Check for balance/quota/carrier limit errors
          const isAuthOrQuotaError = 
            res.status === 401 || 
            res.status === 402 || 
            res.status === 403 || 
            res.status === 429 ||
            (data.message && /balance|quota|credit|insufficient|limit exceeded|subscription|exhausted/i.test(data.message));

          if (isAuthOrQuotaError) {
            campaignPauseRef.current = true;
            setCampaignPaused(true);
            const alertMsg = `Campaign Auto-Paused: Carrier/API quota or balance issue (${data.message || 'Check LiveKit SIP balance'}). Please resolve and click Resume.`;
            setCampaignAlert(alertMsg);

            setBatchContacts(prev => prev.map((c, i) => i === targetIdx ? { ...c, status: 'error', error: data.message || 'Carrier Quota/Balance Error' } : c));
            setActiveSlots(prev => ({
              ...prev,
              [slotId]: {
                ...prev[slotId],
                status: 'error',
                error: data.message || 'Auto-paused'
              }
            }));
            break;
          }

          if (data.success) {
            setActiveSlots(prev => ({
              ...prev,
              [slotId]: {
                ...prev[slotId],
                status: 'connected',
                callSid: data.roomName
              }
            }));

            // Let the call proceed. In real telephony, calls take 15-40s.
            // Stagger next dial by 12 seconds per slot to maintain natural pacing
            await sleep(12000);

            setBatchContacts(prev => prev.map((c, i) => i === targetIdx ? { ...c, status: 'done', callSid: data.roomName } : c));
            setActiveSlots(prev => ({
              ...prev,
              [slotId]: {
                ...prev[slotId],
                status: 'completed'
              }
            }));
          } else {
            setBatchContacts(prev => prev.map((c, i) => i === targetIdx ? { ...c, status: 'error', error: data.message } : c));
            setActiveSlots(prev => ({
              ...prev,
              [slotId]: {
                ...prev[slotId],
                status: 'error',
                error: data.message
              }
            }));
            await sleep(3000);
          }
        } catch (err: any) {
          setBatchContacts(prev => prev.map((c, i) => i === targetIdx ? { ...c, status: 'error', error: err.message } : c));
          setActiveSlots(prev => ({
            ...prev,
            [slotId]: {
              ...prev[slotId],
              status: 'error',
              error: err.message
            }
          }));
          await sleep(3000);
        }

        // Reset slot to idle before next dial
        setActiveSlots(prev => ({
          ...prev,
          [slotId]: { slotId, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 }
        }));

        // 1.5s spacing between calls on this slot
        await sleep(1500);
      }

      // Slot idle when worker loop ends
      setActiveSlots(prev => ({
        ...prev,
        [slotId]: { slotId, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 }
      }));
    };

    // Run exactly 2 concurrent workers (Slot 1 and Slot 2)
    await Promise.all([runSlotWorker(1), runSlotWorker(2)]);

    if (!campaignPauseRef.current) {
      setCampaignRunning(false);
      setCampaignPaused(false);
    }
  };

  const pauseCampaign = () => {
    campaignPauseRef.current = true;
    setCampaignPaused(true);
  };

  const resumeCampaign = () => {
    campaignPauseRef.current = false;
    setCampaignPaused(false);
    setCampaignAlert(null);
    if (!campaignRunning) {
      startCampaign();
    }
  };

  const stopCampaign = () => {
    campaignStopRef.current = true;
    campaignPauseRef.current = false;
    setCampaignRunning(false);
    setCampaignPaused(false);
    // Revert in-flight calls to queued so user can restart or review
    setBatchContacts(prev => prev.map(c => c.status === 'calling' ? { ...c, status: 'queued' } : c));
    setActiveSlots({
      1: { slotId: 1, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 },
      2: { slotId: 2, contactName: '', phoneNumber: '', status: 'idle', elapsedSeconds: 0 },
    });
  };

  const clearQueue = () => {
    stopCampaign();
    setBatchContacts([]);
    setCampaignAlert(null);
  };

  const handleDeleteCall = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to remove this call log?')) return;

    try {
      const stored = localStorage.getItem('gayatri_permanent_history');
      if (stored) {
        const filtered = JSON.parse(stored).filter((c: any) => c.id !== id && c.callSid !== id);
        localStorage.setItem('gayatri_permanent_history', JSON.stringify(filtered));
      }
    } catch (e) {
      console.warn('Failed to delete from localStorage:', e);
    }

    setCallLogs(prev => prev.filter(c => c.id !== id));
    await deleteCallLog(id);
    await loadData();
  };

  // Filtered call logs (Strictly 3 categories)
  const filteredCalls = callLogs.filter(call => {
    const nameMatch = (call.customerName || call.leadName || '').toLowerCase().includes(searchQuery.toLowerCase());
    const phoneMatch = (call.customerPhone || call.leadPhone || '').toLowerCase().includes(searchQuery.toLowerCase());
    const queryMatches = nameMatch || phoneMatch;

    if (!queryMatches) return false;

    if (statusFilter === 'All') return true;
    const tag = getOutcomeTag(call).label;
    if (statusFilter === 'Interested') return tag === 'Interested';
    if (statusFilter === 'Site Visit') return tag === 'Site Visit';
    if (statusFilter === 'Not Interested') return tag === 'Not Interested';

    return true;
  });

  // Verbatim Script Parser with Turn & Timestamp support
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
      const tsMatch = line.match(/^\[([\d.]+(?:s|m)?)\]\s*(.+)$/i);
      let timestamp: string | undefined = undefined;
      let content = line;

      if (tsMatch) {
        timestamp = tsMatch[1];
        content = tsMatch[2].trim();
      }

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

  const handleCopyTranscript = () => {
    if (!selectedCall?.transcript) return;
    navigator.clipboard.writeText(selectedCall.transcript);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2500);
  };

  return (
    <div className="space-y-8 pb-12">
      
      {/* 1. 1-CLICK OUTBOUND VOICE AI DIALER */}
      <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 border border-blue-800/40 rounded-3xl p-6 sm:p-8 text-white shadow-2xl shadow-blue-950/40 relative overflow-hidden">
        <div className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-1/3 -mb-8 w-48 h-48 bg-indigo-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10 space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="max-w-xl space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs font-semibold">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Gayatri AI • Kusha Cloned Voice Engine (Speed Locked: 1.0x)</span>
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
                Instantly dial any customer phone number. Gayatri introduces <strong className="text-white">Sai Garden (Shilphata Highway, Opp. Xperia Mall)</strong>, handles inquiries with priority in Marathi (auto-switching to Hindi/English), and confirms site visits.
              </p>
            </div>

            {/* Dialing Form */}
            <form onSubmit={handleOutboundCall} className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3 bg-white/5 p-3.5 sm:p-4 rounded-2xl border border-white/10 backdrop-blur-md shadow-xl">
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

              <div className="flex flex-col sm:flex-row items-center gap-2">
                <button
                  type="submit"
                  disabled={isDialing || isTerminating}
                  className="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/30 flex items-center justify-center space-x-2 transition-all disabled:opacity-50 cursor-pointer"
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

                <button
                  type="button"
                  onClick={handleTerminateAllCalls}
                  disabled={isTerminating}
                  title="Immediately hang up and terminate active carrier phone calls"
                  className="w-full sm:w-auto px-4 py-2.5 bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-rose-600/30 flex items-center justify-center space-x-2 transition-all disabled:opacity-50 cursor-pointer"
                >
                  {isTerminating ? (
                    <>
                      <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Ending Calls...</span>
                    </>
                  ) : (
                    <>
                      <PhoneOff className="h-4 w-4" />
                      <span>Terminate All Calls</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
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

      {/* 2. BATCH CAMPAIGN DIALER (PERMANENT DEDICATED CARD — NOT A DROPDOWN) */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm p-6 sm:p-7 space-y-6">
        
        {/* Header & Controls Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center shrink-0">
              <FileSpreadsheet className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-black text-base text-slate-900 dark:text-white">
                  Batch Campaign Dialer
                </h3>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
                  2 Concurrent Calls
                </span>
                {batchContacts.length > 0 && (
                  <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-violet-100 dark:bg-violet-900/50 text-violet-700 dark:text-violet-300">
                    {batchContacts.length} Contacts
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-medium">
                Upload <span className="text-slate-700 dark:text-slate-200 font-semibold">.xlsx, .xls, or .csv</span>. Automatically searches columns for name & phone, dials 2 lines simultaneously with pause & resume.
              </p>
            </div>
          </div>

          {/* Action Buttons: Start, Pause, Resume, Stop, Clear */}
          <div className="flex flex-wrap items-center gap-2">
            {!campaignRunning && !campaignPaused && (
              <button
                onClick={startCampaign}
                disabled={batchContacts.filter(c => c.status === 'queued').length === 0}
                className="flex items-center space-x-1.5 px-4 py-2 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white font-bold text-xs rounded-xl shadow-md shadow-indigo-600/20 disabled:opacity-40 transition-all cursor-pointer"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>Start Campaign</span>
              </button>
            )}

            {campaignRunning && !campaignPaused && (
              <button
                onClick={pauseCampaign}
                className="flex items-center space-x-1.5 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-xl shadow-md shadow-amber-500/20 transition-all cursor-pointer"
              >
                <Pause className="h-3.5 w-3.5 fill-current" />
                <span>Pause</span>
              </button>
            )}

            {campaignPaused && (
              <button
                onClick={resumeCampaign}
                className="flex items-center space-x-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-xl shadow-md shadow-emerald-600/20 transition-all cursor-pointer"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>Resume Campaign</span>
              </button>
            )}

            {(campaignRunning || campaignPaused) && (
              <button
                onClick={stopCampaign}
                className="flex items-center space-x-1.5 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs rounded-xl shadow-md shadow-rose-600/20 transition-all cursor-pointer"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                <span>Stop</span>
              </button>
            )}

            {batchContacts.length > 0 && (
              <button
                onClick={clearQueue}
                className="px-3 py-2 text-xs font-semibold text-slate-500 hover:text-rose-500 dark:hover:text-rose-400 transition-colors cursor-pointer"
              >
                Clear Queue
              </button>
            )}
          </div>
        </div>

        {/* Auto-Pause or Carrier Alert Banner */}
        {campaignAlert && (
          <div className="p-3.5 rounded-2xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2.5">
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">{campaignAlert}</p>
            </div>
            <button
              onClick={() => setCampaignAlert(null)}
              className="text-amber-600 hover:text-amber-800 font-bold px-1"
            >
              ✕
            </button>
          </div>
        )}

        {/* 2 CONCURRENT ACTIVE LIVE CALL SLOTS MONITOR */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2].map((slotNum) => {
            const slot = activeSlots[slotNum as 1 | 2];
            const isBusy = slot.status === 'calling' || slot.status === 'connected';

            return (
              <div 
                key={slotNum}
                className={`p-4 rounded-2xl border transition-all ${
                  isBusy
                    ? 'bg-gradient-to-br from-blue-50/80 to-indigo-50/40 dark:from-slate-800/90 dark:to-blue-950/40 border-blue-200 dark:border-blue-800 shadow-md'
                    : 'bg-slate-50/50 dark:bg-slate-800/30 border-slate-200 dark:border-slate-800'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className="h-2 w-2 rounded-full bg-blue-600 animate-ping" />
                    <span className="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Channel #{slotNum} {isBusy ? '• Live On-Air' : '• Standby'}
                    </span>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    slot.status === 'connected' ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20' :
                    slot.status === 'calling' ? 'bg-amber-500/10 text-amber-600 border border-amber-500/20 animate-pulse' :
                    slot.status === 'error' ? 'bg-rose-500/10 text-rose-600' :
                    'bg-slate-200 dark:bg-slate-700 text-slate-500'
                  }`}>
                    {slot.status === 'connected' ? 'Speaking with Gayatri' :
                     slot.status === 'calling' ? 'Ringing Carrier...' :
                     slot.status === 'error' ? 'Call Error' : 'Idle'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-black text-slate-900 dark:text-white">
                      {slot.contactName || (isBusy ? 'Connecting Client...' : 'Ready for Next Call')}
                    </h4>
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5">
                      {slot.phoneNumber || 'Awaiting queue dispatch'}
                    </p>
                  </div>
                  {isBusy && (
                    <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-blue-600 text-white font-mono text-xs font-bold shadow-sm">
                      <Clock className="h-3 w-3" />
                      <span>{Math.floor(slot.elapsedSeconds / 60)}:{String(slot.elapsedSeconds % 60).padStart(2, '0')}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Upload & Manual Paste Inputs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          
          {/* File Upload (.xlsx, .xls, .csv) */}
          <div className="space-y-2">
            <p className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Upload className="h-3.5 w-3.5 text-indigo-500" />
              <span>Upload Spreadsheet (.xlsx, .xls, .csv)</span>
            </p>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-2xl p-5 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-indigo-500 dark:hover:border-indigo-400 transition-colors bg-slate-50/50 dark:bg-slate-800/40"
            >
              <FileSpreadsheet className="h-8 w-8 text-indigo-500" />
              <div className="text-center">
                <p className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  Click to select <span className="text-indigo-600 dark:text-indigo-400">Excel (.xlsx/.xls)</span> or CSV file
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Searches columns automatically for Name & Phone (ignores empty phone rows)
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv,.txt"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
          </div>

          {/* Quick Manual Paste Option */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <List className="h-3.5 w-3.5 text-indigo-500" />
                <span>Or Paste List Manually</span>
              </p>
              {manualList.trim() && (
                <button
                  onClick={handleManualListLoad}
                  className="text-xs font-bold px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
                >
                  Load List
                </button>
              )}
            </div>
            <textarea
              value={manualList}
              onChange={e => setManualList(e.target.value)}
              placeholder={"Name, Phone Number\nRaj, +918693081506\nPriya, 9876543210\n+918800001234"}
              rows={4}
              className="w-full text-xs rounded-2xl border border-slate-300 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 px-3 py-2.5 text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono resize-none"
            />
          </div>
        </div>

        {/* Batch Queue & Progress */}
        {batchContacts.length > 0 && (
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between text-xs">
              <p className="font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
                Call Queue ({batchContacts.length} Contacts)
              </p>
              <div className="flex items-center gap-3 text-[11px] font-semibold">
                <span className="text-emerald-600">✓ Done: {batchContacts.filter(c => c.status === 'done').length}</span>
                <span className="text-amber-500">📞 Calling: {batchContacts.filter(c => c.status === 'calling').length}</span>
                <span className="text-slate-400">⏳ Queued: {batchContacts.filter(c => c.status === 'queued').length}</span>
                <span className="text-rose-500">✗ Error: {batchContacts.filter(c => c.status === 'error').length}</span>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-indigo-500 to-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${(batchContacts.filter(c => c.status === 'done' || c.status === 'error').length / batchContacts.length) * 100}%` }}
              />
            </div>

            {/* Contact Rows List */}
            <div className="max-h-48 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800 bg-white dark:bg-slate-900/50">
              {batchContacts.map((c, i) => (
                <div key={i} className="flex items-center justify-between px-3.5 py-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                      c.status === 'done' ? 'bg-emerald-500' :
                      c.status === 'calling' ? 'bg-blue-500 animate-pulse' :
                      c.status === 'error' ? 'bg-rose-500' : 'bg-slate-300'
                    }`} />
                    <span className="font-semibold text-slate-800 dark:text-slate-200">{c.name}</span>
                    <span className="text-slate-400 font-mono text-[11px]">{c.phone}</span>
                  </div>
                  <span className={`font-bold text-[11px] ${
                    c.status === 'done' ? 'text-emerald-600' :
                    c.status === 'calling' ? 'text-blue-500 animate-pulse' :
                    c.status === 'error' ? 'text-rose-500' : 'text-slate-400'
                  }`}>
                    {c.status === 'done' ? '✓ Completed' : c.status === 'calling' ? 'Calling...' : c.status === 'error' ? `Error: ${c.error?.slice(0, 25) || 'Failed'}` : 'Queued'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 3. REAL-TIME CALL ANALYTICS (4 STRICT KPI METRIC CARDS) */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-1">
          <div>
            <h3 className="font-black text-sm text-slate-900 dark:text-white flex items-center space-x-2">
              <BarChart3 className="h-4 w-4 text-blue-600" />
              <span>Real-Time Call Analytics</span>
            </h3>
            <p className="text-[11px] text-slate-400 font-medium">
              Showing metrics for: <strong className="text-slate-700 dark:text-slate-200 capitalize">{analyticsPeriod === 'all' ? 'All Time' : analyticsPeriod === 'today' ? 'Today (Day-wise)' : analyticsPeriod === 'week' ? 'This Week' : analyticsPeriod === 'month' ? 'This Month' : 'This Year'}</strong> ({filteredCallsForAnalytics.length} total calls)
            </p>
          </div>

          {/* Time Period Filter Pills */}
          <div className="flex items-center gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
            {[
              { id: 'today', label: 'Today' },
              { id: 'week', label: 'This Week' },
              { id: 'month', label: 'This Month' },
              { id: 'year', label: 'Yearly' },
              { id: 'all', label: 'All Time' },
            ].map(p => {
              const active = analyticsPeriod === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setAnalyticsPeriod(p.id as any)}
                  className={`px-3 py-1 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                    active
                      ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 4 KPI METRICS CARDS (Total Calls, Interested, Site Visits, Not Interested) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          
          <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between group">
            <div>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total Calls</p>
              <h3 className="text-2xl font-black text-slate-900 dark:text-white mt-1">{periodStats.totalCalls}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Logged calls</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => handleDownloadPdf('All')}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                title="Download All Call Logs PDF"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                <PhoneCall className="h-4.5 w-4.5" />
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between group">
            <div>
              <p className="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold uppercase tracking-wider">Interested</p>
              <h3 className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">{periodStats.interested}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Positive & Future Plans</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => handleDownloadPdf('Interested')}
                className="p-1.5 rounded-xl text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/60 transition-colors"
                title="Download Interested Leads PDF"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <CheckCircle2 className="h-4.5 w-4.5" />
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between group">
            <div>
              <p className="text-[10px] text-blue-600 dark:text-blue-400 font-bold uppercase tracking-wider">Site Visits</p>
              <h3 className="text-2xl font-black text-blue-600 dark:text-blue-400 mt-1">{periodStats.siteVisits}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Confirmed appointments</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => handleDownloadPdf('Site Visit')}
                className="p-1.5 rounded-xl text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/60 transition-colors"
                title="Download Site Visits PDF"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                <Calendar className="h-4.5 w-4.5" />
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between group">
            <div>
              <p className="text-[10px] text-rose-500 font-bold uppercase tracking-wider">Not Interested</p>
              <h3 className="text-2xl font-black text-rose-500 mt-1">{periodStats.notInterested}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Declined / Opted Out</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => handleDownloadPdf('Not Interested')}
                className="p-1.5 rounded-xl text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/60 transition-colors"
                title="Download Not Interested PDF"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <div className="h-10 w-10 rounded-xl bg-rose-500/10 text-rose-500 flex items-center justify-center">
                <XCircle className="h-4.5 w-4.5" />
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* 4. CONFIRMED SITE VISIT SCHEDULE (CLEAN COLLAPSIBLE LIST SORTED CHRONOLOGICALLY) */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden">
        
        <button
          onClick={() => setIsVisitScheduleOpen(prev => !prev)}
          className="w-full flex items-center justify-between p-6 text-left hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
        >
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-2xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
              <CalendarDays className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-black text-base text-slate-900 dark:text-white">
                  Confirmed Site Visit Schedule
                </h3>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/60">
                  {siteVisits.length} Confirmed {siteVisits.length === 1 ? 'Visit' : 'Visits'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-medium">
                Arranged chronologically with nearest upcoming date at the top.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 text-slate-400">
            <span className="text-xs font-semibold">{isVisitScheduleOpen ? 'Hide' : 'View List'}</span>
            {isVisitScheduleOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </button>

        {isVisitScheduleOpen && (
          <div className="border-t border-slate-100 dark:border-slate-800 p-6">
            {siteVisits.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400">
                <Calendar className="h-8 w-8 mx-auto text-slate-300 dark:text-slate-600 mb-2" />
                <p className="font-bold text-slate-600 dark:text-slate-300">No site visits scheduled yet</p>
                <p className="mt-0.5">When callers confirm Saturday or Sunday visit slots with Gayatri, they will be listed here automatically.</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {siteVisits.map((visit) => (
                  <div key={visit.id} className="py-3.5 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2 flex-wrap">
                        <span className="px-2.5 py-0.5 rounded-md bg-blue-600 text-white text-xs font-bold font-mono">
                          {visit.displayDate}
                        </span>
                        <h4 className="font-bold text-sm text-slate-900 dark:text-white">
                          {visit.customerName}
                        </h4>
                        <span className="text-xs text-slate-400 font-mono">
                          {visit.customerPhone}
                        </span>
                        <span className="px-2 py-0.5 rounded-md bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 text-[11px] font-bold border border-indigo-200/60 dark:border-indigo-800/60">
                          {visit.flatType}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1 font-medium">
                        {visit.summary}
                      </p>
                    </div>

                    <div className="flex items-center space-x-2 self-end sm:self-center shrink-0">
                      <button
                        onClick={() => setSelectedCall(visit.originalCall)}
                        className="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-700 dark:text-slate-300 transition-colors flex items-center space-x-1"
                      >
                        <MessageSquare className="h-3.5 w-3.5" />
                        <span>View Script</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 5. GAYATRI CALL LOGS & PERMANENT INTELLIGENCE TABLE */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden">
        
        {/* Table Header Controls */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h3 className="font-black text-base text-slate-900 dark:text-white flex items-center space-x-2">
              <PhoneCall className="h-5 w-5 text-blue-600" />
              <span>Permanent Call Ledger & Complete Scripts</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5 font-medium">
              Every customer conversation is permanently preserved with word-for-word verbatim dialogue.
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

            {/* Strict 3 Outcome Filter Pills */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl text-xs">
              {(['All', 'Interested', 'Site Visit', 'Not Interested'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setStatusFilter(tab)}
                  className={`px-3 py-1 font-bold rounded-lg transition-all cursor-pointer ${
                    statusFilter === tab
                      ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Export PDF Dropdown */}
            <div className="relative" ref={pdfDropdownRef}>
              <button
                onClick={() => setPdfMenuOpen(!pdfMenuOpen)}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 text-white font-bold text-xs shadow-sm shadow-blue-600/20 transition-all cursor-pointer"
                title="Download Categorized PDF Reports"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Export PDF</span>
                <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${pdfMenuOpen ? 'rotate-180' : ''}`} />
              </button>

              {pdfMenuOpen && (
                <div className="absolute right-0 mt-2 w-64 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-30 py-2 text-xs divide-y divide-slate-100 dark:divide-slate-800 animate-in fade-in zoom-in-95 duration-100">
                  <div className="px-3.5 py-1.5 text-[10px] font-extrabold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                    <span>Download Category Report</span>
                    <span className="text-blue-600 dark:text-blue-400 font-bold">PDF</span>
                  </div>

                  <div className="py-1">
                    <button
                      onClick={() => handleDownloadPdf('Interested')}
                      className="w-full text-left px-3.5 py-2 hover:bg-emerald-50/80 dark:hover:bg-emerald-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                    >
                      <span className="flex items-center space-x-2">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                        <span>Interested Clients</span>
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-bold">
                        {stats.interested}
                      </span>
                    </button>

                    <button
                      onClick={() => handleDownloadPdf('Site Visit')}
                      className="w-full text-left px-3.5 py-2 hover:bg-blue-50/80 dark:hover:bg-blue-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                    >
                      <span className="flex items-center space-x-2">
                        <span className="h-2 w-2 rounded-full bg-blue-500" />
                        <span>Site Visits Scheduled</span>
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-bold">
                        {stats.siteVisits}
                      </span>
                    </button>

                    <button
                      onClick={() => handleDownloadPdf('Not Interested')}
                      className="w-full text-left px-3.5 py-2 hover:bg-rose-50/80 dark:hover:bg-rose-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                    >
                      <span className="flex items-center space-x-2">
                        <span className="h-2 w-2 rounded-full bg-rose-500" />
                        <span>Not Interested / DNC</span>
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 font-bold">
                        {stats.notInterested}
                      </span>
                    </button>
                  </div>

                  <div className="pt-1">
                    <button
                      onClick={() => handleDownloadPdf('All')}
                      className="w-full text-left px-3.5 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 flex items-center justify-between font-bold transition-colors cursor-pointer"
                    >
                      <span className="flex items-center space-x-2">
                        <List className="h-3.5 w-3.5 text-slate-400" />
                        <span>Complete All Call Logs</span>
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-bold">
                        {callLogs.length}
                      </span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Refresh Button */}
            <button
              onClick={handleRefresh}
              className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              title="Refresh Call Logs"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* Call Logs Feed / Table (No audio player, full script viewing) */}
        <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {loading ? (
            <div className="py-16 text-center text-xs text-slate-400">
              <div className="h-6 w-6 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin mx-auto mb-3" />
              Loading permanent call history...
            </div>
          ) : filteredCalls.length === 0 ? (
            <div className="py-16 text-center text-xs text-slate-400 space-y-2">
              <MessageSquare className="h-8 w-8 mx-auto text-slate-300 dark:text-slate-700" />
              <p className="font-bold text-slate-600 dark:text-slate-300 text-sm">No call logs found</p>
              <p>Place an outbound call or start a batch campaign to populate call records.</p>
            </div>
          ) : (
            filteredCalls.map((call) => {
              const tag = getOutcomeTag(call);
              const pickedInfo = getCallPickedInfo(call);
              const timeMs = getCallTimestampMs(call);
              const dateStr = timeMs > 0 ? new Date(timeMs).toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              }) : 'Recent';

              const durationFormatted = formatCallDuration(call);

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
                          {call.customerName || call.leadName || 'Valued Customer'}
                        </h4>
                        <span className="text-xs text-slate-400 font-mono font-medium">
                          {call.customerPhone || call.leadPhone || '+918693081506'}
                        </span>
                        
                        {/* Outcome Tag (Site Visit, Interested, Not Interested) */}
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${tag.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                          <span>{tag.label}</span>
                        </span>

                        {/* Picked Status */}
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${pickedInfo.bg} ${pickedInfo.border} ${pickedInfo.textColor}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${pickedInfo.dot}`} />
                          <span>{pickedInfo.label}</span>
                        </span>
                      </div>

                      {/* AI Summary / Notes */}
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1 font-medium">
                        {call.aiSummary || 'Outbound consultation regarding Sai Garden project (Opp. Xperia Mall).'}
                      </p>
                    </div>
                  </div>

                  {/* Right: Timing, Duration & View Full Script Button */}
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

                    {/* View Full Script Button */}
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

      {/* 6. VERBATIM SCRIPT MODAL (FULL SCRIPT VIEWER WITH COPY TRANSCRIPT BUTTON) */}
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
                      Conversation with {selectedCall.customerName || selectedCall.leadName || 'Customer'}
                    </h3>
                    {(() => {
                      const tag = getOutcomeTag(selectedCall);
                      const pTag = getCallPickedInfo(selectedCall);
                      return (
                        <div className="flex items-center space-x-1.5 flex-wrap gap-y-1">
                          <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${tag.bg}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                            <span>{tag.label}</span>
                          </span>
                          <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${pTag.bg} ${pTag.border} ${pTag.textColor}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${pTag.dot}`} />
                            <span>{pTag.label}</span>
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                  <p className="text-xs text-slate-400 font-medium">
                    Phone: <span className="font-mono text-slate-600 dark:text-slate-300">{selectedCall.customerPhone || selectedCall.leadPhone || '+918693081506'}</span> • Duration: <span className="font-semibold text-slate-700 dark:text-slate-200">{formatCallDuration(selectedCall)}</span>
                  </p>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleCopyTranscript}
                    className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors flex items-center space-x-1 text-xs font-semibold"
                    title="Copy Full Script to Clipboard"
                  >
                    {copySuccess ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                    <span>{copySuccess ? 'Copied' : 'Copy'}</span>
                  </button>

                  <button
                    onClick={() => setSelectedCall(null)}
                    className="p-2 rounded-xl text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>

              {/* AI Summary Banner */}
              <div className="px-6 py-3 bg-blue-50/50 dark:bg-blue-950/20 border-b border-blue-100 dark:border-blue-900/30 text-xs text-blue-800 dark:text-blue-300 font-medium">
                <span className="font-bold">AI Call Summary: </span>
                {selectedCall.aiSummary || 'Outbound consultation regarding Sai Garden project (Opp. Xperia Mall).'}
              </div>

              {/* Turn-by-Turn Verbatim Dialogue */}
              <div className="p-6 overflow-y-auto space-y-4 flex-1">
                {parseTranscript(selectedCall.transcript, selectedCall.customerName || selectedCall.leadName || 'Customer').map((turn, idx) => {
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
                  <span>Permanent Call Ledger • Verbatim Transcript</span>
                </span>
                <button
                  onClick={() => setSelectedCall(null)}
                  className="px-5 py-2 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-bold rounded-xl transition-all cursor-pointer"
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
