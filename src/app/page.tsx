'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
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
  Tag, 
  Volume2, 
  ArrowRight,
  TrendingUp,
  Trash2,
  Download,
  Upload,
  List,
  Play,
  Square,
  FileText,
  ChevronDown,
  BarChart3,
  CalendarDays,
  MapPin,
  ExternalLink
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import * as XLSX from 'xlsx';
import { exportLeadsToPdf, PdfReportCategory } from '@/lib/pdfExport';
import { exportLeadsToXlsx, XlsxReportCategory } from '@/lib/xlsxExport';

// Helper to determine status tag styling and label with strict precedence
export const getOutcomeTag = (call: CallLog) => {
  const outcome = (call.outcome || '').toLowerCase();
  const summary = (call.aiSummary || '').toLowerCase();
  const transcript = (call.transcript || '').toLowerCase();

  // 1. Not Interested (Top priority: Check if customer expressed disinterest or declined)
  const isNotInterested = 
    outcome.includes('not interested') || 
    summary.includes('not interested') ||
    summary.includes('declined') ||
    summary.includes('rejected') ||
    summary.includes('nahi chahiye') ||
    call.sentiment === 'negative';

  if (isNotInterested) {
    return {
      label: 'Not Interested',
      bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
      dot: 'bg-rose-500',
      icon: XCircle
    };
  }

  // 2. Future Plan / Need Afterwards (Busy, call later, after 2-3 months, next year)
  const isFuturePlan = 
    outcome.includes('future plan') ||
    outcome.includes('need afterwards') ||
    outcome.includes('afterwards') ||
    summary.includes('call later') ||
    summary.includes('after 2') ||
    summary.includes('after 3') ||
    summary.includes('next year') ||
    summary.includes('baad mein') ||
    summary.includes('follow up later');

  if (isFuturePlan) {
    return {
      label: 'Future Plan / Need Afterwards',
      bg: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
      dot: 'bg-amber-500',
      icon: Clock
    };
  }

  // 3. Location Mismatch (Kalyan)
  if (outcome.includes('location mismatch') || outcome.includes('kalyan') || summary.includes('kalyan')) {
    return {
      label: 'Location Mismatch',
      bg: 'bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800',
      dot: 'bg-purple-500',
      icon: AlertCircle
    };
  }

  // 4. Site Visit Scheduled (Must be an actual confirmation)
  const isSiteVisit = 
    outcome.includes('site visit scheduled') || 
    (outcome.includes('site visit') && !outcome.includes('not') && !outcome.includes('dropped')) ||
    summary.includes('confirmed site visit') ||
    summary.includes('scheduled site visit') ||
    summary.includes('site visit confirmed') ||
    transcript.includes('site visit confirm');

  if (isSiteVisit) {
    return {
      label: 'Site Visit Scheduled',
      bg: 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
      dot: 'bg-blue-500',
      icon: Calendar
    };
  }

  // 5. Interested (Customer interested in flats, pricing, WhatsApp details)
  const isInterested = 
    outcome === 'interested' || 
    (outcome.includes('interested') && !outcome.includes('not')) ||
    summary.includes('showed interest') ||
    summary.includes('expressed interest') ||
    (call.sentiment === 'positive' && !outcome.includes('not'));

  if (isInterested) {
    return {
      label: 'Interested',
      bg: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
      dot: 'bg-emerald-500',
      icon: CheckCircle2
    };
  }

  // 6. Not Picked Up / Missed (Customer didn't answer or hung up before pickup)
  if (
    outcome.includes('not picked') || 
    outcome.includes('unanswered') || 
    outcome.includes('missed') ||
    (Number(call.durationSeconds || 0) === 0 && !outcome.includes('calling') && !outcome.includes('ringing'))
  ) {
    return {
      label: 'Not Picked Up / Missed',
      bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
      dot: 'bg-rose-500',
      icon: PhoneOff
    };
  }

  // 7. Ringing / Calling
  if (outcome.includes('calling') || outcome.includes('ringing')) {
    return {
      label: 'Ringing / Calling',
      bg: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
      dot: 'bg-amber-500 animate-pulse',
      icon: Clock
    };
  }

  // 8. Short / Dropped (Connected, but call ended after 1-2 quick greetings)
  if (outcome.includes('dropped') || outcome.includes('short')) {
    return {
      label: 'Short / Dropped',
      bg: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700',
      dot: 'bg-slate-400',
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

export default function ColdCallingHomePage() {
  const [callLogs, setCallLogs] = useState<(CallLog & { leadName: string; leadPhone?: string })[]>([]);
  const [stats, setStats] = useState({ totalCalls: 0, siteVisits: 0, interested: 0, notInterested: 0, futurePlan: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Dynamic Voice Speed State & Persistence
  const [voiceSpeed, setVoiceSpeed] = useState<number>(1.05);
  const [isSavingSpeed, setIsSavingSpeed] = useState<boolean>(false);

  // Analytics Period Filter State
  const [analyticsPeriod, setAnalyticsPeriod] = useState<'all' | 'today' | 'week' | 'month' | 'year'>('all');

  // 1-Click Dialing Form State
  const [dialName, setDialName] = useState('Raj');
  const [dialPhone, setDialPhone] = useState('+918693081506');
  const [isDialing, setIsDialing] = useState(false);
  const [isTerminating, setIsTerminating] = useState(false);
  const [dialResult, setDialResult] = useState<{ success: boolean; message: string } | null>(null);

  // ── Batch Campaign State ──
  type CampaignContact = { name: string; phone: string };
  type CampaignEntry = CampaignContact & { status: 'queued' | 'calling' | 'done' | 'error'; error?: string };
  const [batchContacts, setBatchContacts] = useState<CampaignEntry[]>([]);
  const [campaignRunning, setCampaignRunning] = useState(false);
  const [campaignStopped, setCampaignStopped] = useState(false);
  const [manualList, setManualList] = useState('');
  const [showBatchPanel, setShowBatchPanel] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const campaignStopRef = useRef(false);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Interested' | 'Future Plan' | 'Site Visit' | 'Not Interested'>('All');
  const [pickedFilter, setPickedFilter] = useState<'All' | 'Picked Up' | 'Not Picked Up'>('All');

  // Site Visit Schedule Filter State
  const [visitTimeFilter, setVisitTimeFilter] = useState<'all' | 'today' | 'week' | 'month'>('all');

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

  // Export Dropdown State (PDF & XLSX)
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target as Node)) {
        setExportMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Load persisted voice speed on mount
  useEffect(() => {
    try {
      const localSpeed = localStorage.getItem('gayatri_voice_speed');
      if (localSpeed) {
        const val = parseFloat(localSpeed);
        if (!isNaN(val) && val >= 0.6 && val <= 1.6) {
          setVoiceSpeed(val);
        }
      }
    } catch {}

    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data?.success && data.settings?.voiceSpeed) {
          const sp = Number(data.settings.voiceSpeed);
          if (!isNaN(sp) && sp >= 0.6 && sp <= 1.6) {
            setVoiceSpeed(sp);
            try { localStorage.setItem('gayatri_voice_speed', String(sp)); } catch {}
          }
        }
      })
      .catch(err => console.debug('Could not fetch voice settings:', err));
  }, []);

  const handleUpdateVoiceSpeed = async (newSpeed: number) => {
    const rounded = Math.round(newSpeed * 100) / 100;
    setVoiceSpeed(rounded);
    try {
      localStorage.setItem('gayatri_voice_speed', String(rounded));
    } catch {}

    try {
      setIsSavingSpeed(true);
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voiceSpeed: rounded }),
      });
    } catch (e) {
      console.warn('Could not save voice speed to server:', e);
    } finally {
      setIsSavingSpeed(false);
    }
  };

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

  const periodStats = useMemo(() => {
    const totalCalls = filteredCallsForAnalytics.length;
    let siteVisits = 0;
    let interested = 0;
    let notInterested = 0;
    let futurePlan = 0;

    for (const call of filteredCallsForAnalytics) {
      const tag = getOutcomeTag(call).label;
      if (tag === 'Site Visit Scheduled') {
        siteVisits++;
      } else if (tag === 'Interested') {
        interested++;
      } else if (tag === 'Not Interested') {
        notInterested++;
      } else if (tag === 'Future Plan / Need Afterwards') {
        futurePlan++;
      }
    }

    return {
      totalCalls,
      siteVisits,
      interested,
      notInterested,
      futurePlan
    };
  }, [filteredCallsForAnalytics]);

  // Extract confirmed site visits for the Google Calendar schedule segment
  const siteVisits = useMemo(() => {
    const visits: {
      id: string;
      customerName: string;
      customerPhone: string;
      day: string;
      time: string;
      flatType: string;
      status: string;
      googleCalendarUrl: string;
      recordingUrl?: string;
      callSid?: string;
      createdAt?: string;
      summary: string;
      originalCall: (CallLog & { leadName: string; leadPhone?: string });
    }[] = [];

    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const dayOfWeek = now.getDay();
    const diffToMonday = (dayOfWeek === 0 ? -6 : 1) - dayOfWeek;
    const weekStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diffToMonday).getTime();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();

    const visitCalls = callLogs.filter(c => {
      const tag = getOutcomeTag(c);
      const isVisit = tag.label === 'Site Visit Scheduled' || 
             (c.aiSummary && c.aiSummary.toLowerCase().includes('site visit')) ||
             (c.transcript && c.transcript.toLowerCase().includes('site visit'));
      if (!isVisit) return false;

      const callMs = getCallTimestampMs(c);
      if (visitTimeFilter === 'today') return callMs >= todayStart;
      if (visitTimeFilter === 'week') return callMs >= weekStart;
      if (visitTimeFilter === 'month') return callMs >= monthStart;
      return true;
    });

    for (const c of visitCalls) {
      const text = ((c.aiSummary || '') + ' ' + (c.transcript || '')).toLowerCase();
      
      let day = 'Saturday';
      if (text.includes('sunday') || text.includes('ravivar') || text.includes('raviwar') || text.includes('रविवार')) day = 'Sunday';
      else if (text.includes('saturday') || text.includes('shanivar') || text.includes('shaniwar') || text.includes('शनिवार')) day = 'Saturday';
      else if (text.includes('friday') || text.includes('shukravar') || text.includes('शुक्रवार')) day = 'Friday';
      else if (text.includes('tomorrow') || text.includes('kal')) day = 'Tomorrow';

      let time = '11:00 AM';
      if (text.includes('4 pm') || text.includes('4 baje') || text.includes('4:00') || text.includes('shaam') || text.includes('संध्याकाळी') || text.includes('evening')) {
        time = '4:00 PM';
      } else if (text.includes('3 pm') || text.includes('3 baje')) {
        time = '3:00 PM';
      } else if (text.includes('11') || text.includes('subah') || text.includes('सकाळी') || text.includes('morning')) {
        time = '11:00 AM';
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

      const gTitle = encodeURIComponent(`Site Visit: ${name} (${flatType}) - Sai Garden`);
      const gDetails = encodeURIComponent(`Client: ${name}\nPhone: ${phone}\nFlat Type: ${flatType}\nProject: Sai Garden, Shilphata-Manpada Highway, Opp. Xperia Mall\nAI Summary: ${summary}`);
      const gLoc = encodeURIComponent('Sai Garden, Shilphata-Manpada Highway, Opposite Xperia Mall, Nilje, Dombivli');
      const gCalUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${gTitle}&details=${gDetails}&location=${gLoc}`;

      visits.push({
        id: c.callSid || c.id || String(Math.random()),
        customerName: name,
        customerPhone: phone,
        day,
        time,
        flatType,
        status: 'Confirmed',
        googleCalendarUrl: gCalUrl,
        recordingUrl: c.recordingUrl,
        callSid: c.callSid,
        createdAt: (c as any).createdAt || c.calledAt || (c as any).timestamp || new Date().toISOString(),
        summary,
        originalCall: c
      });
    }

    return visits;
  }, [callLogs, visitTimeFilter]);

  const handleDownloadPdf = (category: PdfReportCategory) => {
    setExportMenuOpen(false);
    exportLeadsToPdf({
      category,
      calls: filteredCallsForAnalytics,
      getOutcomeTag,
      userEmail: currentUser?.email || 'test@gmail.com',
    });
  };

  const handleDownloadXlsx = (category: XlsxReportCategory) => {
    setExportMenuOpen(false);
    exportLeadsToXlsx({
      category,
      calls: filteredCallsForAnalytics,
      getOutcomeTag,
      userEmail: currentUser?.email || 'test@gmail.com',
    });
  };

  const loadData = async () => {
    try {
      // 1. Fetch server logs from database (Server Action + direct API endpoint)
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

      // Helper to read deleted call IDs blacklist
      const getDeletedIds = (): Set<string> => {
        try {
          const raw = localStorage.getItem('gayatri_deleted_call_ids');
          if (raw) return new Set(JSON.parse(raw));
        } catch {}
        return new Set();
      };
      const deletedIds = getDeletedIds();

      // 2. Read preserved call history from browser storage (purging corrupted fake templates)
      let permanentHistory: (CallLog & { leadName: string; leadPhone?: string })[] = [];
      try {
        const stored = localStorage.getItem('gayatri_permanent_history');
        if (stored) {
          permanentHistory = JSON.parse(stored).filter((item: any) => {
            if (!item) return false;
            const sid = item.callSid || item.id || '';
            if (deletedIds.has(item.id) || (item.callSid && deletedIds.has(item.callSid))) return false;
            const name = (item.customerName || item.leadName || '').toLowerCase();
            const sidLower = sid.toLowerCase();
            if (sidLower.includes('probe') || name.includes('probe') || sidLower === 'gayatri-persistent-storage') return false;
            // Purge any corrupted dummy entries containing the fake fallback template
            if (item.transcript && (item.transcript.includes('Haan boliye') || item.transcript.includes('Sai Complex Dombivli East se. Humare paas premium one BHK'))) return false;
            if (item.aiSummary && item.aiSummary.includes('Conversation recorded and filed.')) return false;
            return true;
          });
        }
      } catch (err) {
        console.warn('Could not read permanent call history:', err);
      }

      // 3. Merge server and local history
      const map = new Map<string, CallLog & { leadName: string; leadPhone?: string }>();

      // First, seed with all authoritative server logs
      const nowMs = Date.now();
      for (const item of serverLogs) {
        if (!item || item.callSid === 'gayatri-persistent-storage') continue;
        if (deletedIds.has(item.id) || (item.callSid && deletedIds.has(item.callSid))) continue;
        const name = (item.customerName || item.leadName || '').toLowerCase();
        const sid = (item.callSid || item.id || '').toLowerCase();
        if (sid.includes('probe') || name.includes('probe')) continue;
        // Purge dummy corrupted records from server logs as well
        if (item.transcript && item.transcript.includes('Haan boliye')) continue;
        if (item.aiSummary && item.aiSummary.includes('Conversation recorded and filed.')) continue;

        const key = item.callSid || item.id;
        if (!item.recordingUrl && item.callSid && !item.callSid.includes('probe')) {
          item.recordingUrl = `/api/recordings/${item.callSid}.mp3`;
        }
        map.set(key, item);
      }

      // Second, augment with local items from permanent history (RETAIN ALL CALLS: Never discard older calls)
      for (const localItem of permanentHistory) {
        if (!localItem || localItem.callSid === 'gayatri-persistent-storage') continue;
        const key = localItem.callSid || localItem.id;
        if (deletedIds.has(localItem.id) || (localItem.callSid && deletedIds.has(localItem.callSid))) continue;
        const existing = map.get(key);

        if (existing) {
          // Preserve local audio if server doesn't have one
          if (localItem.recordingUrl?.startsWith('data:') && !existing.recordingUrl?.startsWith('data:')) {
            existing.recordingUrl = localItem.recordingUrl;
          }
        } else {
          // Retain all historical calls permanently so no call is ever missing
          map.set(key, localItem);
        }
      }

      // Third, check if any in-flight calls timed out (> 75 seconds)
      for (const [key, item] of map.entries()) {
        const isCallingState = item.outcome === 'Ringing / Calling' || item.outcome === 'Calling...';
        if (isCallingState) {
          const itemTime = getCallTimestampMs(item);
          const callAgeSeconds = itemTime > 0 ? (nowMs - itemTime) / 1000 : 999;
          if (callAgeSeconds > 75) {
            item.outcome = 'Not Picked Up';
            item.durationSeconds = item.durationSeconds || 0;
            if (!item.transcript || item.transcript.includes('[Call In Progress]') || item.transcript.includes('[Call initiated')) {
              item.transcript = '[Call was disconnected or unanswered before conversation started]';
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

      // Persist the clean, validated call history to localStorage for instant offline warm-up
      try {
        localStorage.setItem('gayatri_permanent_history', JSON.stringify(merged));
        localStorage.removeItem('gayatri_live_call_logs'); // clean up legacy key
      } catch (err) {
        console.warn('Could not persist permanent call history:', err);
      }

      setCallLogs(merged);

      // Also keep modal in sync in real-time if active
      if (selectedCall) {
        const updated = merged.find(c => (c.callSid && c.callSid === selectedCall.callSid) || c.id === selectedCall.id);
        if (updated && (
          updated.transcript !== selectedCall.transcript || 
          updated.outcome !== selectedCall.outcome || 
          updated.aiSummary !== selectedCall.aiSummary ||
          updated.recordingUrl !== selectedCall.recordingUrl
        )) {
          setSelectedCall(updated);
        }
      }

      // 4. Calculate mathematically precise KPIs using strict outcome detection
      const totalCalls = merged.length;
      let siteVisits = 0;
      let interested = 0;
      let notInterested = 0;
      let futurePlan = 0;

      for (const call of merged) {
        const tag = getOutcomeTag(call).label;
        if (tag === 'Site Visit Scheduled') {
          siteVisits++;
        } else if (tag === 'Interested') {
          interested++;
        } else if (tag === 'Not Interested') {
          notInterested++;
        } else if (tag === 'Future Plan / Need Afterwards') {
          futurePlan++;
        }
      }

      setStats({
        totalCalls,
        siteVisits,
        interested,
        notInterested,
        futurePlan
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

    // Auto-poll for background updates every 4 seconds for instant cross-device sync
    const interval = setInterval(() => {
      loadData();
    }, 4000);

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
          userEmail: currentUser?.email || 'test@gmail.com',
          voiceSpeed: voiceSpeed
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
          const stored = localStorage.getItem('gayatri_permanent_history') || localStorage.getItem('gayatri_live_call_logs');
          const existing = stored ? JSON.parse(stored) : [];
          existing.unshift(newLiveLog);
          localStorage.setItem('gayatri_permanent_history', JSON.stringify(existing));
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
          message: data.message || `Terminated ${data.count} active call(s).`
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

  // ── Clean Phone Number Helper ──
  // Strips noise, trailing decimals (.0), formatting, and normalizes to standard +91 or +<country>
  const cleanPhoneNumber = (val: any): string | null => {
    if (val === null || val === undefined) return null;
    let str = String(val).trim();
    if (!str) return null;

    // Handle float / scientific notation from spreadsheets (e.g. 9876543210.0 or 9.87654321E+09)
    if (/^\d+\.0+$/.test(str)) {
      str = str.split('.')[0];
    } else if (/e\+/i.test(str)) {
      const num = Number(str);
      if (!isNaN(num)) str = Math.floor(num).toString();
    }

    // Remove common punctuation/spacing
    str = str.replace(/[\s\-\(\)\.,]/g, '');

    const hasPlus = str.startsWith('+');
    const digits = str.replace(/\D/g, '');

    if (!digits || digits.length < 8) return null;

    // Indian standard phone normalization
    if (digits.length === 10) {
      return `+91${digits}`;
    }
    if (digits.length === 11 && digits.startsWith('0')) {
      return `+91${digits.slice(1)}`;
    }
    if (digits.length === 12 && digits.startsWith('91')) {
      return `+${digits}`;
    }
    if (hasPlus) {
      return `+${digits}`;
    }
    if (digits.length >= 10 && digits.length <= 15) {
      return `+${digits}`;
    }
    return null;
  };

  // ── Universal Spreadsheet & CSV Parser (.xlsx, .xls, .csv, .txt) ──
  // Deep scans every row and cell across all sheets. If only numbers exist, assigns C1, C2, C3...
  const parseSpreadsheetOrText = (data: ArrayBuffer | string): { name: string; phone: string }[] => {
    const contacts: { name: string; phone: string }[] = [];
    const seenPhones = new Set<string>();
    let customerIndex = 1;

    try {
      let workbook: XLSX.WorkBook;
      if (typeof data === 'string') {
        workbook = XLSX.read(data, { type: 'string' });
      } else {
        workbook = XLSX.read(new Uint8Array(data), { type: 'array' });
      }

      for (const sheetName of workbook.SheetNames) {
        const sheet = workbook.Sheets[sheetName];
        if (!sheet) continue;
        const rows: any[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });

        for (const row of rows) {
          if (!Array.isArray(row) || row.length === 0) continue;

          // Check for pure header rows
          const rowStr = row.map(c => String(c).toLowerCase()).join(' ');
          if (rowStr.includes('sr no') && rowStr.includes('phone') && !row.some(c => cleanPhoneNumber(c))) {
            continue;
          }

          let foundPhone: string | null = null;
          let candidateName = '';

          for (const cell of row) {
            const cleaned = cleanPhoneNumber(cell);
            if (cleaned && !foundPhone) {
              foundPhone = cleaned;
            } else {
              const cellStr = String(cell).trim();
              if (
                cellStr.length >= 2 &&
                /[a-zA-Z\u0900-\u097F]/.test(cellStr) &&
                !/^(name|phone|mobile|contact|customer|sr|s\.no|sr\.|no|number|date|address|city|email|remark|status)$/i.test(cellStr)
              ) {
                if (!candidateName) {
                  candidateName = cellStr;
                }
              }
            }
          }

          if (foundPhone && !seenPhones.has(foundPhone)) {
            seenPhones.add(foundPhone);
            const finalName = candidateName || `C${customerIndex++}`;
            contacts.push({ name: finalName, phone: foundPhone });
          }
        }
      }
    } catch (err) {
      console.error('Error parsing spreadsheet:', err);
    }

    return contacts;
  };

  const parseManualLines = (raw: string): { name: string; phone: string }[] => {
    const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    const contacts: { name: string; phone: string }[] = [];
    const seen = new Set<string>();
    let cIndex = 1;

    for (const line of lines) {
      if (/^(name|phone|contact|number)/i.test(line)) continue;
      const parts = line.split(/,/).map(p => p.trim().replace(/^["']|["']$/g, ''));
      let phone: string | null = null;
      let name = '';

      if (parts.length >= 2) {
        const phone1 = cleanPhoneNumber(parts[0]);
        const phone2 = cleanPhoneNumber(parts[1]);
        if (phone1) {
          phone = phone1;
          name = parts[1];
        } else if (phone2) {
          phone = phone2;
          name = parts[0];
        }
      } else if (parts.length === 1) {
        phone = cleanPhoneNumber(parts[0]);
      }

      if (phone && !seen.has(phone)) {
        seen.add(phone);
        contacts.push({ name: name || `C${cIndex++}`, phone });
      }
    }
    return contacts;
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const buffer = ev.target?.result as ArrayBuffer;
      const parsed = parseSpreadsheetOrText(buffer);
      if (parsed.length > 0) {
        setBatchContacts(parsed.map(c => ({ ...c, status: 'queued' as const })));
      }
    };
    reader.readAsArrayBuffer(file);
    e.target.value = ''; // Allow re-selecting the same file if needed
  };

  const handleManualListLoad = () => {
    const parsed = parseManualLines(manualList);
    if (parsed.length === 0) return;
    setBatchContacts(parsed.map(c => ({ ...c, status: 'queued' as const })));
  };

  const startCampaign = async () => {
    if (batchContacts.length === 0) return;
    campaignStopRef.current = false;
    setCampaignRunning(true);
    setCampaignStopped(false);

    const MAX_CONCURRENT = 2; // Optimal concurrency for carrier routing
    let activeCount = 0;
    let contactIdx = 0;
    const contacts = [...batchContacts];

    const dialNext = async (idx: number) => {
      if (campaignStopRef.current) return;
      const contact = contacts[idx];
      setBatchContacts(prev => prev.map((c, i) => i === idx ? { ...c, status: 'calling' } : c));

      try {
        const res = await fetch('/api/outbound-call', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            phoneNumber: contact.phone,
            customerName: contact.name,
            userEmail: currentUser?.email || 'test@gmail.com',
            voiceSpeed: voiceSpeed
          })
        });
        const data = await res.json();
        if (data.success) {
          setBatchContacts(prev => prev.map((c, i) => i === idx ? { ...c, status: 'done' } : c));
        } else {
          setBatchContacts(prev => prev.map((c, i) => i === idx ? { ...c, status: 'error', error: data.message } : c));
        }
      } catch (err: any) {
        setBatchContacts(prev => prev.map((c, i) => i === idx ? { ...c, status: 'error', error: err.message } : c));
      }

      activeCount--;
      if (!campaignStopRef.current && contactIdx < contacts.length) {
        const nextIdx = contactIdx++;
        activeCount++;
        setTimeout(() => dialNext(nextIdx), 2000);
      } else if (activeCount === 0) {
        setCampaignRunning(false);
      }
    };

    while (contactIdx < contacts.length && activeCount < MAX_CONCURRENT) {
      const idx = contactIdx++;
      activeCount++;
      await new Promise(r => setTimeout(r, 600));
      dialNext(idx);
    }
  };

  const stopCampaign = () => {
    campaignStopRef.current = true;
    setCampaignRunning(false);
    setCampaignStopped(true);
    setBatchContacts(prev => prev.map(c => c.status === 'calling' ? { ...c, status: 'queued' } : c));
  };

  const handleDeleteCall = async (id: string, e: React.MouseEvent, callSid?: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to permanently delete this call log?')) return;

    // 1. Add to local deleted blacklist so polling never resurrects it
    try {
      const raw = localStorage.getItem('gayatri_deleted_call_ids');
      const delSet = new Set<string>(raw ? JSON.parse(raw) : []);
      delSet.add(id);
      if (callSid) delSet.add(callSid);
      localStorage.setItem('gayatri_deleted_call_ids', JSON.stringify(Array.from(delSet)));
    } catch {}

    // 2. Remove from localStorage permanent history
    try {
      const stored = localStorage.getItem('gayatri_permanent_history');
      if (stored) {
        const filtered = JSON.parse(stored).filter((c: any) => 
          c.id !== id && c.callSid !== id && (!callSid || (c.id !== callSid && c.callSid !== callSid))
        );
        localStorage.setItem('gayatri_permanent_history', JSON.stringify(filtered));
      }
    } catch (e) {
      console.warn('Failed to delete from localStorage:', e);
    }

    // 3. Optimistic UI removal
    setCallLogs(prev => prev.filter(c => c.id !== id && (!callSid || c.callSid !== callSid)));
    if (selectedCall?.id === id || (callSid && selectedCall?.callSid === callSid)) {
      setSelectedCall(null);
    }

    // 4. Delete on server (db.json + LiveKit room metadata)
    try {
      await deleteCallLog(id);
      if (callSid && callSid !== id) {
        await deleteCallLog(callSid);
      }
    } catch (delErr) {
      console.warn('Error calling deleteCallLog server action:', delErr);
    }
  };

  // Filtered call logs with search, outcome, and Picked / Not Picked filters
  const filteredCalls = callLogs.filter(call => {
    const nameMatch = (call.customerName || call.leadName || '').toLowerCase().includes(searchQuery.toLowerCase());
    const phoneMatch = (call.customerPhone || call.leadPhone || '').toLowerCase().includes(searchQuery.toLowerCase());
    const queryMatches = nameMatch || phoneMatch;

    if (!queryMatches) return false;

    // Picked Up vs Not Picked Up filter
    if (pickedFilter !== 'All') {
      const pickedInfo = getCallPickedInfo(call);
      if (pickedFilter === 'Picked Up' && !pickedInfo.isPicked) return false;
      if (pickedFilter === 'Not Picked Up' && pickedInfo.isPicked) return false;
    }

    if (statusFilter === 'All') return true;
    const tag = getOutcomeTag(call).label;
    if (statusFilter === 'Interested') return tag === 'Interested';
    if (statusFilter === 'Future Plan') return tag === 'Future Plan / Need Afterwards';
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

        <div className="relative z-10 space-y-6">
          {/* Top Row: Description on Left, Dial Form on Right */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
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
                Instantly dial any customer phone number. Gayatri introduces <strong className="text-white">Sai Garden (Shilphata Highway, Opp. Xperia Mall)</strong>, handles inquiries with #1 priority in pure Marathi (with auto-switch to Hindi or English), and books confirmed site visits. All call transcripts are saved under <span className="text-emerald-400 font-semibold">{currentUser?.email || 'test@gmail.com'}</span>.
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
                  title="Immediately hang up and terminate all active carrier phone calls"
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

          {/* Full-Width Voice Speed Control Bar */}
          <div className="pt-4 border-t border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs bg-white/[0.03] p-3.5 rounded-2xl border border-white/5">
            <div className="flex flex-wrap items-center gap-3 text-slate-300 font-medium">
              <div className="flex items-center space-x-2 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20 text-emerald-300">
                <Volume2 className="h-4 w-4 text-emerald-400" />
                <span className="font-bold">Gayatri Voice Speed:</span>
                <span className="font-mono font-black text-white px-2 py-0.5 rounded bg-emerald-500/30 text-xs">
                  {voiceSpeed.toFixed(2)}x
                </span>
              </div>
              <span className="text-xs text-slate-400">
                {voiceSpeed < 0.95 ? '(Relaxed & Clear)' : voiceSpeed <= 1.05 ? '(Natural Rhythm — Recommended)' : '(Fast)'}
              </span>
              {isSavingSpeed && (
                <span className="text-[11px] text-teal-300 animate-pulse font-semibold">● Saved to Cloud</span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <input
                type="range"
                min="0.80"
                max="1.20"
                step="0.02"
                value={voiceSpeed}
                onChange={(e) => handleUpdateVoiceSpeed(parseFloat(e.target.value))}
                className="w-36 accent-emerald-400 cursor-pointer h-1.5 bg-white/20 rounded-lg appearance-none"
                title="Adjust Gayatri speaking speed (0.80x to 1.20x)"
              />
              <div className="flex items-center space-x-1.5">
                {[
                  { speed: 0.85, label: '0.85x' },
                  { speed: 0.90, label: '0.90x' },
                  { speed: 0.94, label: '0.94x' },
                  { speed: 1.00, label: '1.0x' },
                  { speed: 1.05, label: '1.05x' },
                  { speed: 1.10, label: '1.1x' },
                ].map(p => (
                  <button
                    key={p.speed}
                    type="button"
                    onClick={() => handleUpdateVoiceSpeed(p.speed)}
                    className={`px-2.5 py-1 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                      Math.abs(voiceSpeed - p.speed) < 0.01
                        ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/30'
                        : 'bg-white/10 hover:bg-white/20 text-slate-300'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
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

      {/* 1b. BATCH CAMPAIGN DIALER */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden">
        <button
          onClick={() => setShowBatchPanel(p => !p)}
          className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
        >
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-xl bg-violet-500/10 flex items-center justify-center">
              <List className="h-5 w-5 text-violet-600 dark:text-violet-400" />
            </div>
            <div>
              <p className="font-bold text-sm text-slate-900 dark:text-white">Batch Campaign Dialer</p>
              <p className="text-[11px] text-slate-400 font-medium">Upload a CSV or paste numbers to dial up to 4 calls simultaneously</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {batchContacts.length > 0 && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300">
                {batchContacts.length} contacts
              </span>
            )}
            <span className="text-slate-400 text-lg">{showBatchPanel ? '▲' : '▼'}</span>
          </div>
        </button>

        {showBatchPanel && (
          <div className="border-t border-slate-200 dark:border-slate-800 p-6 space-y-5">
            {/* Input Area */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Spreadsheet / CSV Upload */}
              <div className="space-y-2">
                <p className="text-xs font-bold text-slate-600 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5" /> Upload Excel (.xlsx/.xls) or CSV
                </p>
                <div
                  className="border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-5 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-violet-400 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-7 w-7 text-slate-400" />
                  <p className="text-xs text-slate-500 text-center">
                    Click to upload <span className="font-semibold text-violet-600">.xlsx, .xls, or .csv</span><br />
                    <span className="text-[11px] text-slate-400">Scans all rows & columns • Unnamed contacts auto-named C1, C2...</span>
                  </p>
                  <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv,.txt" className="hidden" onChange={handleFileUpload} />
                </div>
              </div>

              {/* Manual Paste */}
              <div className="space-y-2">
                <p className="text-xs font-bold text-slate-600 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <List className="h-3.5 w-3.5" /> Paste Numbers Manually
                </p>
                <textarea
                  value={manualList}
                  onChange={e => setManualList(e.target.value)}
                  placeholder={"Raj, +918693081506\nPriya, +919876543210\n+918800001234"}
                  rows={5}
                  className="w-full text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2.5 text-slate-700 dark:text-slate-300 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-400 resize-none font-mono"
                />
                <button
                  onClick={handleManualListLoad}
                  disabled={!manualList.trim()}
                  className="text-xs font-bold px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg disabled:opacity-40 transition-colors"
                >
                  Load {manualList.trim() ? `(${parseManualLines(manualList).length} contacts)` : ''}
                </button>
              </div>
            </div>

            {/* Contact Queue */}
            {batchContacts.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
                    Call Queue — {batchContacts.length} contacts
                  </p>
                  <div className="flex items-center gap-2 text-[11px] font-semibold">
                    <span className="text-slate-500">✓ Done: {batchContacts.filter(c => c.status === 'done').length}</span>
                    <span className="text-amber-500">📞 Calling: {batchContacts.filter(c => c.status === 'calling').length}</span>
                    <span className="text-slate-400">⏳ Queued: {batchContacts.filter(c => c.status === 'queued').length}</span>
                    <span className="text-rose-500">✗ Error: {batchContacts.filter(c => c.status === 'error').length}</span>
                  </div>
                </div>
                <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800">
                  {batchContacts.map((c, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                          c.status === 'done' ? 'bg-emerald-500' :
                          c.status === 'calling' ? 'bg-amber-400 animate-pulse' :
                          c.status === 'error' ? 'bg-rose-500' : 'bg-slate-300'
                        }`} />
                        <span className="font-medium text-slate-700 dark:text-slate-300">{c.name}</span>
                        <span className="text-slate-400 font-mono">{c.phone}</span>
                      </div>
                      <span className={`font-semibold ${
                        c.status === 'done' ? 'text-emerald-600' :
                        c.status === 'calling' ? 'text-amber-500' :
                        c.status === 'error' ? 'text-rose-500' : 'text-slate-400'
                      }`}>
                        {c.status === 'done' ? '✓ Called' : c.status === 'calling' ? '📞 Calling…' : c.status === 'error' ? `✗ ${c.error?.slice(0, 30) ?? 'Error'}` : 'Queued'}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-violet-500 to-indigo-500 h-2 rounded-full transition-all"
                    style={{ width: `${(batchContacts.filter(c => c.status === 'done' || c.status === 'error').length / batchContacts.length) * 100}%` }}
                  />
                </div>

                {/* Campaign Controls */}
                <div className="flex items-center gap-3 pt-1">
                  {!campaignRunning ? (
                    <button
                      onClick={startCampaign}
                      disabled={batchContacts.filter(c => c.status === 'queued').length === 0}
                      className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-bold text-xs rounded-xl shadow-lg disabled:opacity-40 transition-all"
                    >
                      <Play className="h-3.5 w-3.5" />
                      {campaignStopped ? 'Resume Campaign' : 'Start Campaign'}
                    </button>
                  ) : (
                    <button
                      onClick={stopCampaign}
                      className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white font-bold text-xs rounded-xl shadow-lg transition-all"
                    >
                      <Square className="h-3.5 w-3.5" />
                      Stop Campaign
                    </button>
                  )}
                  <button
                    onClick={() => { setBatchContacts([]); setCampaignRunning(false); setCampaignStopped(false); }}
                    className="text-xs text-slate-500 hover:text-rose-500 font-medium transition-colors"
                  >
                    Clear Queue
                  </button>
                  {campaignStopped && (
                    <span className="text-xs text-amber-600 font-semibold">⚠️ Campaign paused</span>
                  )}
                  {!campaignRunning && !campaignStopped && batchContacts.every(c => c.status === 'done' || c.status === 'error') && batchContacts.length > 0 && (
                    <span className="text-xs text-emerald-600 font-semibold">✓ Campaign complete!</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. ANALYTICS & KPI METRICS */}
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

        {/* 5 KPI METRICS CARDS */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          
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
              <span className="text-[10px] text-slate-400 font-medium">High positive intent</span>
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
              <span className="text-[10px] text-slate-400 font-medium">Appointments</span>
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
              <p className="text-[10px] text-amber-600 dark:text-amber-400 font-bold uppercase tracking-wider">Future Plan</p>
              <h3 className="text-2xl font-black text-amber-600 dark:text-amber-400 mt-1">{periodStats.futurePlan}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Follow-up needed</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => handleDownloadPdf('Future Plan')}
                className="p-1.5 rounded-xl text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/60 transition-colors"
                title="Download Future Plan Leads PDF"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <div className="h-10 w-10 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                <Clock className="h-4.5 w-4.5" />
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between group">
            <div>
              <p className="text-[10px] text-rose-500 font-bold uppercase tracking-wider">Not Interested</p>
              <h3 className="text-2xl font-black text-rose-500 mt-1">{periodStats.notInterested}</h3>
              <span className="text-[10px] text-slate-400 font-medium">Opted out / DNC</span>
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

      {/* 2.5 SITE VISIT SCHEDULE & GOOGLE CALENDAR SEGMENT */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-sm overflow-hidden p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-5 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center space-x-3">
            <div className="h-11 w-11 rounded-2xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
              <CalendarDays className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-black text-base text-slate-900 dark:text-white">
                  Sai Garden Site Visit Schedule
                </h3>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
                  {siteVisits.length} Confirmed Visit{siteVisits.length === 1 ? '' : 's'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-medium flex items-center gap-1.5">
                <MapPin className="h-3 w-3 text-slate-400" />
                <span>Opp. Xperia Mall, Shilphata-Manpada Highway • Sync directly to Google Calendar</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            {/* Filter pills for Site Visit Schedule */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-800 p-1 rounded-xl text-xs">
              {[
                { id: 'all', label: 'All' },
                { id: 'today', label: 'Today' },
                { id: 'week', label: 'This Week' },
                { id: 'month', label: 'This Month' },
              ].map(f => (
                <button
                  key={f.id}
                  onClick={() => setVisitTimeFilter(f.id as any)}
                  className={`px-2.5 py-1 font-bold rounded-lg transition-all cursor-pointer ${
                    visitTimeFilter === f.id
                      ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <a
              href="https://calendar.google.com/calendar/u/0/r"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700/80 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-bold transition-all shadow-sm"
              title="Open Google Calendar in a new tab"
            >
              <Calendar className="h-3.5 w-3.5 text-blue-500" />
              <span>Open Google Calendar</span>
              <ExternalLink className="h-3 w-3 text-slate-400 ml-0.5" />
            </a>
          </div>
        </div>

        {/* Schedule Grid: Core slots & Booked Visits */}
        {siteVisits.length === 0 ? (
          <div className="py-8 text-center">
            <div className="h-12 w-12 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto mb-3">
              <Calendar className="h-6 w-6" />
            </div>
            <h4 className="text-sm font-bold text-slate-700 dark:text-slate-300">
              No Site Visits Scheduled In This Filter Range
            </h4>
            <p className="text-xs text-slate-400 max-w-md mx-auto mt-1 font-medium">
              Gayatri AI automatically negotiates preferred slots (Saturday/Sunday 11 AM or 4 PM) with interested callers. Once confirmed, visits appear here with 1-click Google Calendar sync.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-5">
            {siteVisits.map((visit) => (
              <div 
                key={visit.id}
                className="p-4 rounded-2xl border border-indigo-100 dark:border-indigo-950/60 bg-gradient-to-br from-indigo-50/40 via-white to-blue-50/20 dark:from-slate-900 dark:via-slate-900/90 dark:to-indigo-950/20 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2.5">
                    <div>
                      <h4 className="text-sm font-black text-slate-900 dark:text-white flex items-center gap-1.5">
                        <User className="h-3.5 w-3.5 text-indigo-500" />
                        <span>{visit.customerName}</span>
                      </h4>
                      {visit.customerPhone && (
                        <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 mt-0.5">
                          {visit.customerPhone}
                        </p>
                      )}
                    </div>
                    <span className="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      {visit.status}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 mb-3">
                    <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-black bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20">
                      <Clock className="h-3 w-3 text-indigo-500" />
                      <span>{visit.day} • {visit.time}</span>
                    </span>
                    <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-500/20">
                      <Building2 className="h-3 w-3 text-blue-500" />
                      <span>{visit.flatType}</span>
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 font-medium mb-3 bg-white/60 dark:bg-slate-800/60 p-2 rounded-xl border border-slate-100 dark:border-slate-800">
                    {visit.summary}
                  </p>
                </div>

                <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800/80">
                  <a
                    href={visit.googleCalendarUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-all"
                    title="Add directly to your Google Calendar"
                  >
                    <Calendar className="h-3.5 w-3.5" />
                    <span>Add to Google Cal</span>
                  </a>

                  <button
                    onClick={() => setSelectedCall(visit.originalCall)}
                    className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-xl text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  >
                    <MessageSquare className="h-3 w-3" />
                    <span>Transcript</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
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

            {/* Picked Up / Not Picked Up Filter Pills */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl text-xs">
              {(['All', 'Picked Up', 'Not Picked Up'] as const).map((tab) => {
                const count = tab === 'All' 
                  ? callLogs.length 
                  : tab === 'Picked Up' 
                    ? callLogs.filter(c => getCallPickedInfo(c).isPicked).length 
                    : callLogs.filter(c => !getCallPickedInfo(c).isPicked).length;
                return (
                  <button
                    key={tab}
                    onClick={() => setPickedFilter(tab)}
                    className={`px-2.5 py-1 font-bold rounded-lg transition-all flex items-center space-x-1 cursor-pointer ${
                      pickedFilter === tab
                        ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                        : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    }`}
                  >
                    <span>{tab}</span>
                    <span className="text-[10px] opacity-70">({count})</span>
                  </button>
                );
              })}
            </div>

            {/* Filter Pills */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl text-xs">
              {(['All', 'Interested', 'Future Plan', 'Site Visit', 'Not Interested'] as const).map((tab) => (
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

            {/* Export Reports Dropdown (PDF & Excel XLSX) */}
            <div className="relative" ref={exportDropdownRef}>
              <button
                onClick={() => setExportMenuOpen(!exportMenuOpen)}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 text-white font-bold text-xs shadow-sm shadow-blue-600/20 transition-all cursor-pointer"
                title="Download Reports as PDF or Excel (.xlsx)"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Export</span>
                <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${exportMenuOpen ? 'rotate-180' : ''}`} />
              </button>

              {exportMenuOpen && (
                <div className="absolute right-0 mt-2 w-72 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-30 py-2 text-xs divide-y divide-slate-100 dark:divide-slate-800 animate-in fade-in zoom-in-95 duration-100 max-h-[85vh] overflow-y-auto">
                  {/* Excel (.xlsx) Section */}
                  <div>
                    <div className="px-3.5 py-1.5 text-[10px] font-extrabold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider flex items-center justify-between bg-emerald-50/50 dark:bg-emerald-950/20">
                      <span>Export Excel (.xlsx)</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/60 font-bold">EXCEL</span>
                    </div>
                    <div className="py-1">
                      <button
                        onClick={() => handleDownloadXlsx('Interested')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-emerald-50/80 dark:hover:bg-emerald-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-emerald-500" />
                          <span>Interested Leads (.xlsx)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.interested}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadXlsx('Site Visit')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-blue-50/80 dark:hover:bg-blue-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-blue-500" />
                          <span>Site Visits Scheduled (.xlsx)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.siteVisits}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadXlsx('Future Plan')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-amber-50/80 dark:hover:bg-amber-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-amber-500" />
                          <span>Future Plan / Follow-up (.xlsx)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.futurePlan || 0}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadXlsx('Not Interested')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-rose-50/80 dark:hover:bg-rose-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-rose-500" />
                          <span>Not Interested Leads (.xlsx)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.notInterested}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadXlsx('All')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-100 flex items-center justify-between font-bold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <List className="h-3.5 w-3.5 text-emerald-600" />
                          <span>Complete All Call Logs (.xlsx)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{callLogs.length}</span>
                      </button>
                    </div>
                  </div>

                  {/* PDF Section */}
                  <div>
                    <div className="px-3.5 py-1.5 text-[10px] font-extrabold text-blue-600 dark:text-blue-400 uppercase tracking-wider flex items-center justify-between bg-blue-50/50 dark:bg-blue-950/20">
                      <span>Export PDF Reports</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/60 font-bold">PDF</span>
                    </div>
                    <div className="py-1">
                      <button
                        onClick={() => handleDownloadPdf('Interested')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-emerald-50/80 dark:hover:bg-emerald-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-emerald-500" />
                          <span>Interested Clients (PDF)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.interested}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadPdf('Site Visit')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-blue-50/80 dark:hover:bg-blue-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-blue-500" />
                          <span>Site Visits Scheduled (PDF)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.siteVisits}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadPdf('Future Plan')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-amber-50/80 dark:hover:bg-amber-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-amber-500" />
                          <span>Future Plan / Follow-up (PDF)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.futurePlan || 0}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadPdf('Not Interested')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-rose-50/80 dark:hover:bg-rose-950/40 text-slate-700 dark:text-slate-200 flex items-center justify-between font-semibold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <span className="h-2 w-2 rounded-full bg-rose-500" />
                          <span>Not Interested Leads (PDF)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{stats.notInterested}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadPdf('All')}
                        className="w-full text-left px-3.5 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-100 flex items-center justify-between font-bold transition-colors cursor-pointer"
                      >
                        <span className="flex items-center space-x-2">
                          <List className="h-3.5 w-3.5 text-blue-600" />
                          <span>Complete All Call Logs (PDF)</span>
                        </span>
                        <span className="text-[10px] text-slate-400 font-bold">{callLogs.length}</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
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
                        <span className="text-xs text-slate-400 font-medium">
                          {call.customerPhone || call.leadPhone || '+918693081506'}
                        </span>
                        
                        {/* Account Badge */}
                        <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 font-mono font-medium border border-slate-200/60 dark:border-slate-700/60">
                          {call.userEmail || currentUser?.email || 'test@gmail.com'}
                        </span>

                        {/* Picked Up Status Tag */}
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${pickedInfo.bg} ${pickedInfo.border} ${pickedInfo.textColor}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${pickedInfo.dot}`} />
                          <span>{pickedInfo.label}</span>
                        </span>

                        {/* Outcome Tag */}
                        <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${tag.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                          <span>{tag.label}</span>
                        </span>

                        {/* Sentiment Tag */}
                        {(() => {
                          const sTag = getSentimentTag(call);
                          return (
                            <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${sTag.bg}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${sTag.dot}`} />
                              <span>{sTag.emoji} {sTag.label}</span>
                            </span>
                          );
                        })()}

                        {/* Audio Recording Badge: ONLY show if call was picked up with audio */}
                        {pickedInfo.isPicked && Number(call.durationSeconds || 0) > 0 && (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
                            <Volume2 className="h-3 w-3" />
                            <span>Audio</span>
                          </span>
                        )}
                      </div>

                      {/* AI Summary / Notes */}
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1 font-medium">
                        {call.aiSummary || 'Outbound consultation regarding Sai Garden project (Opp. Xperia Mall).'}
                      </p>
                    </div>
                  </div>

                  {/* Right: Timing, Duration, Quick Listen & View Script Button */}
                  <div className="flex items-center space-x-3 self-end md:self-center shrink-0">
                    <div className="text-right">
                      <div className="flex items-center space-x-1 text-xs font-semibold text-slate-700 dark:text-slate-300 justify-end">
                        <Clock className="h-3.5 w-3.5 text-slate-400" />
                        <span>{durationFormatted}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-medium">
                        {dateStr}
                      </span>
                    </div>

                    {/* Quick Audio Play Button on Row */}
                    {(call.recordingUrl || Number(call.durationSeconds || 0) > 0) && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCall(call);
                        }}
                        className="px-2.5 py-2 bg-indigo-50 dark:bg-indigo-950/50 hover:bg-indigo-600 hover:text-white text-indigo-600 dark:text-indigo-400 rounded-xl text-xs font-bold border border-indigo-200/60 dark:border-indigo-800/60 flex items-center space-x-1 transition-all cursor-pointer"
                        title="Listen to call recording"
                      >
                        <Volume2 className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Listen</span>
                      </button>
                    )}

                    {/* View Script Button */}
                    <button
                      onClick={() => setSelectedCall(call)}
                      className="px-3.5 py-2 bg-blue-50 dark:bg-blue-950/50 hover:bg-blue-600 hover:text-white text-blue-600 dark:text-blue-400 rounded-xl text-xs font-bold border border-blue-200/60 dark:border-blue-800/60 flex items-center space-x-1.5 transition-all group-hover:bg-blue-600 group-hover:text-white cursor-pointer"
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      <span>View Full Script</span>
                    </button>

                    {/* Delete button */}
                    <button
                      onClick={(e) => handleDeleteCall(call.id, e, call.callSid)}
                      className="p-2 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors cursor-pointer"
                      title="Permanently delete call log"
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
                      Conversation with {selectedCall.customerName || selectedCall.leadName || 'Customer'}
                    </h3>
                    {(() => {
                      const tag = getOutcomeTag(selectedCall);
                      const sTag = getSentimentTag(selectedCall);
                      const pTag = getCallPickedInfo(selectedCall);
                      return (
                        <div className="flex items-center space-x-1.5 flex-wrap gap-y-1">
                          <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${pTag.bg} ${pTag.border} ${pTag.textColor}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${pTag.dot}`} />
                            <span>{pTag.label}</span>
                          </span>
                          <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${tag.bg}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${tag.dot}`} />
                            <span>{tag.label}</span>
                          </span>
                          <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${sTag.bg}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${sTag.dot}`} />
                            <span>{sTag.emoji} {sTag.label}</span>
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                  <p className="text-xs text-slate-400 font-medium">
                    Phone: {selectedCall.customerPhone || selectedCall.leadPhone || '+918693081506'} • Duration: <span className="font-semibold text-slate-700 dark:text-slate-200">{formatCallDuration(selectedCall)}</span> • Account: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{selectedCall.userEmail || currentUser?.email || 'test@gmail.com'}</span>
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
              <div className="px-6 py-3 bg-blue-50/50 dark:bg-blue-950/20 border-b border-blue-100 dark:border-blue-900/30 text-xs text-blue-800 dark:text-blue-300 font-medium flex items-center justify-between">
                <div>
                  <span className="font-bold">AI Call Summary: </span>
                  {selectedCall.aiSummary || 'Outbound consultation regarding Sai Garden project (Opp. Xperia Mall).'}
                </div>
                {(() => {
                  const sTag = getSentimentTag(selectedCall);
                  return (
                    <span className={`shrink-0 ml-3 inline-flex items-center space-x-1 px-2 py-0.5 rounded-md text-[10px] font-bold border ${sTag.bg}`}>
                      <span>{sTag.emoji} {sTag.label} Sentiment</span>
                    </span>
                  );
                })()}
              </div>

              {/* Call Audio Player */}
              {(() => {
                const hasAudio = Boolean(selectedCall.recordingUrl) || Number(selectedCall.durationSeconds || 0) > 0;
                const audioUrl = selectedCall.recordingUrl || `/api/recordings/${selectedCall.callSid}.mp3`;

                if (!hasAudio) {
                  return (
                    <div className="px-6 py-2.5 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700/60 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span className="flex items-center space-x-2">
                        <PhoneOff className="h-4 w-4 text-rose-500" />
                        <span>No audio recording available for this call attempt.</span>
                      </span>
                    </div>
                  );
                }

                return (
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
                    <div className="flex-1 max-w-sm flex items-center gap-2">
                      <audio 
                        key={audioUrl}
                        controls 
                        className="w-full h-8 rounded-lg accent-blue-600" 
                        src={audioUrl} 
                        preload="metadata"
                      >
                        Your browser does not support audio playback.
                      </audio>
                      <a
                        href={audioUrl}
                        download={`${selectedCall.callSid || 'recording'}.mp3`}
                        className="p-1.5 rounded-lg bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors shrink-0"
                        title="Download MP3"
                      >
                        <Download className="h-4 w-4" />
                      </a>
                    </div>
                  </div>
                );
              })()}

              {/* Modal Body: Turn-by-Turn Dialogue */}
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
