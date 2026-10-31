'use client';

import { useState, useEffect, useMemo } from 'react';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import { SarvamCallRecord, TimeFilterPeriod } from '@/lib/sarvamTypes';
import { formatFullPhoneNumber } from '@/lib/sarvamCsv';
import { exportToCsv, exportToPdf } from '@/lib/sarvamExport';
import { 
  PhoneCall, 
  Search, 
  FileSpreadsheet, 
  FileDown, 
  Volume2, 
  Globe2, 
  Clock, 
  Calendar,
  CheckCircle2,
  CalendarCheck,
  Flame,
  AlertCircle
} from 'lucide-react';

export default function CallLogsPage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [outcomeTab, setOutcomeTab] = useState<'all' | 'connected' | 'site_visit' | 'interested' | 'other'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [calls, setCalls] = useState<SarvamCallRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/calls?period=${period}`);
        const data = await res.json();
        setCalls(data.calls || []);
      } catch (err) {
        console.error('Error fetching call logs:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [period]);

  const filteredCalls = useMemo(() => {
    let list = calls;

    if (outcomeTab === 'connected') {
      list = list.filter(c => c.outcome === 'Connected');
    } else if (outcomeTab === 'site_visit') {
      list = list.filter(c => c.outcome === 'Site Visit');
    } else if (outcomeTab === 'interested') {
      list = list.filter(c => c.outcome === 'Interested');
    } else if (outcomeTab === 'other') {
      list = list.filter(c => c.outcome === 'Not Interested' || c.outcome === 'No Answer' || c.outcome === 'Other');
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(c => 
        (c.customerPhone && c.customerPhone.toLowerCase().includes(q)) ||
        (c.customerName && c.customerName.toLowerCase().includes(q))
      );
    }

    return list;
  }, [calls, outcomeTab, searchQuery]);

  const siteVisitCount = calls.filter(c => c.outcome === 'Site Visit').length;
  const interestedCount = calls.filter(c => c.outcome === 'Interested').length;
  const connectedCount = calls.filter(c => c.outcome === 'Connected').length;
  const otherCount = calls.filter(c => c.outcome === 'Not Interested' || c.outcome === 'No Answer' || c.outcome === 'Other').length;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
            <PhoneCall className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <span>All Outbound Call Logs</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Complete archive of all {calls.length} calls made by Gayatri with unmasked phone numbers, duration, and audio playback.
          </p>
        </div>

        {/* Download Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => exportToCsv(filteredCalls, 'All')}
            disabled={filteredCalls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 shadow-sm transition-all disabled:opacity-50"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
            <span>Download CSV (Full Numbers)</span>
          </button>

          <button
            onClick={() => exportToPdf(filteredCalls, 'All', period)}
            disabled={filteredCalls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all disabled:opacity-50"
          >
            <FileDown className="w-4 h-4" />
            <span>Download PDF</span>
          </button>
        </div>
      </div>

      {/* Time Period Filter Bar & Stats */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <PeriodFilterBar currentPeriod={period} onPeriodChange={setPeriod} />
        <span className="text-xs font-semibold text-slate-500">
          Showing <strong>{filteredCalls.length}</strong> of {calls.length} Total Records
        </span>
      </div>

      {/* Tabs & Search Controls */}
      <div className="bg-white dark:bg-slate-900 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
        {/* Outcome Category Tabs */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setOutcomeTab('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              outcomeTab === 'all'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
            }`}
          >
            All Calls ({calls.length})
          </button>
          <button
            onClick={() => setOutcomeTab('connected')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              outcomeTab === 'connected'
                ? 'bg-blue-500 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
            }`}
          >
            Connected ({connectedCount})
          </button>
          <button
            onClick={() => setOutcomeTab('site_visit')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              outcomeTab === 'site_visit'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
            }`}
          >
            Site Visits ({siteVisitCount})
          </button>
          <button
            onClick={() => setOutcomeTab('interested')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              outcomeTab === 'interested'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
            }`}
          >
            Interested ({interestedCount})
          </button>
          <button
            onClick={() => setOutcomeTab('other')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              outcomeTab === 'other'
                ? 'bg-slate-700 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
            }`}
          >
            Others / Declined ({otherCount})
          </button>
        </div>

        {/* Search Box */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by phone number..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 w-full sm:w-56"
          />
        </div>
      </div>

      {/* Clean Basic Details Table */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 dark:bg-slate-850 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="py-3 px-4 w-12 text-center">#</th>
                <th className="py-3 px-4">Customer Phone (Full)</th>
                <th className="py-3 px-4">Customer Name</th>
                <th className="py-3 px-4 text-center">Outcome</th>
                <th className="py-3 px-4 text-center">Duration</th>
                <th className="py-3 px-4">Date & Time</th>
                <th className="py-3 px-4 text-center">Language</th>
                <th className="py-3 px-4 text-center">Recording</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {filteredCalls.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400 font-medium">
                    {isLoading ? 'Loading call records...' : 'No calls found matching your filters.'}
                  </td>
                </tr>
              ) : (
                filteredCalls.map((call, idx) => {
                  const isSiteVisit = call.outcome === 'Site Visit';
                  const isInterested = call.outcome === 'Interested';
                  const isConnected = call.outcome === 'Connected';

                  const badgeClass = isSiteVisit
                    ? 'bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
                    : isInterested
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                    : isConnected
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                    : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700';

                  const isAudioOpen = activeAudioId === call.id;

                  return (
                    <tr key={call.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-850/50 transition-colors">
                      {/* Row # */}
                      <td className="py-3.5 px-4 text-center text-slate-400 font-medium font-mono text-[11px]">
                        {idx + 1}
                      </td>

                      {/* Phone Number (Strictly Unmasked) */}
                      <td className="py-3.5 px-4 font-mono font-extrabold text-blue-600 dark:text-blue-400 tracking-wide text-xs">
                        {formatFullPhoneNumber(call.customerPhone)}
                      </td>

                      {/* Customer Name */}
                      <td className="py-3.5 px-4 font-bold text-slate-800 dark:text-slate-200">
                        {call.customerName || 'Valued Client'}
                        {call.bhkPreference && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold">
                            {call.bhkPreference}
                          </span>
                        )}
                      </td>

                      {/* Outcome / Status Badge */}
                      <td className="py-3.5 px-4 text-center">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold ${badgeClass}`}>
                          {call.outcome}
                        </span>
                      </td>

                      {/* Duration */}
                      <td className="py-3.5 px-4 text-center font-semibold text-slate-700 dark:text-slate-300 whitespace-nowrap">
                        {call.durationSeconds >= 60
                          ? `${Math.floor(call.durationSeconds / 60)}m ${Math.round(call.durationSeconds % 60)}s`
                          : `${call.durationSeconds}s`}
                      </td>

                      {/* Date & Time */}
                      <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap text-[11px]">
                        {new Date(call.callDate).toLocaleString('en-IN', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </td>

                      {/* Language */}
                      <td className="py-3.5 px-4 text-center text-slate-500 dark:text-slate-400 text-[11px]">
                        {call.language || 'Hindi'}
                      </td>

                      {/* Inline Audio Player Trigger */}
                      <td className="py-3.5 px-4 text-center">
                        {call.recordingUrl ? (
                          <div className="flex items-center justify-center">
                            <button
                              onClick={() => setActiveAudioId(isAudioOpen ? null : call.id)}
                              className={`p-1.5 rounded-lg transition-colors flex items-center gap-1 ${
                                isAudioOpen
                                  ? 'bg-blue-600 text-white'
                                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200'
                              }`}
                              title="Listen to call audio"
                            >
                              <Volume2 className="w-3.5 h-3.5" />
                              <span className="text-[10px] font-bold">{isAudioOpen ? 'Close' : 'Listen'}</span>
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-300 dark:text-slate-600 text-[10px]">—</span>
                        )}

                        {/* Inline Audio Player Popup/Drop */}
                        {isAudioOpen && call.recordingUrl && (
                          <div className="mt-2 p-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-md animate-in fade-in">
                            <audio controls autoPlay className="w-48 h-7" preload="auto">
                              <source src={call.recordingUrl} type="audio/wav" />
                              Your browser does not support audio playback.
                            </audio>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
