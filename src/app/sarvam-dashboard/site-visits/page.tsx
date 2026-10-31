'use client';

import { useState, useEffect } from 'react';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import RetainedCallCard from '@/components/sarvam/RetainedCallCard';
import { SarvamCallRecord, TimeFilterPeriod } from '@/lib/sarvamTypes';
import { exportToCsv, exportToPdf } from '@/lib/sarvamExport';
import { CalendarCheck, FileSpreadsheet, FileDown, Clock, ShieldCheck, MapPin } from 'lucide-react';

export default function SarvamSiteVisitsPage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [calls, setCalls] = useState<SarvamCallRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/sarvam/calls?period=${period}&category=Site Visit`);
        const data = await res.json();
        setCalls(data.calls || []);
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [period]);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Title & Action Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
            <CalendarCheck className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <span>Site Visit Scheduled Appointments</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Prospects who confirmed an on-site visit to Sai Garden Sales Lounge, Lodha Heaven, Nilje, Dombivli East.
          </p>
        </div>

        {/* Download Buttons with unmasked phone numbers */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => exportToCsv(calls, 'Site_Visit')}
            disabled={calls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 shadow-sm transition-all disabled:opacity-50"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
            <span>Download CSV (Full Numbers)</span>
          </button>

          <button
            onClick={() => exportToPdf(calls, 'Site Visit', period)}
            disabled={calls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all disabled:opacity-50"
          >
            <FileDown className="w-4 h-4" />
            <span>Download PDF (Full Numbers)</span>
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center justify-between">
        <PeriodFilterBar currentPeriod={period} onPeriodChange={setPeriod} />
        <span className="text-xs font-semibold text-slate-500">
          Showing {calls.length} Confirmed Appointments
        </span>
      </div>

      {/* Property Location Card */}
      <div className="bg-gradient-to-r from-purple-900/90 to-indigo-950 p-4 rounded-2xl text-white flex items-center gap-3 border border-purple-500/20">
        <div className="w-9 h-9 rounded-xl bg-purple-500/20 flex items-center justify-center text-purple-300">
          <MapPin className="w-5 h-5" />
        </div>
        <div>
          <h4 className="text-xs font-bold">Site Visit Location: Sai Garden</h4>
          <p className="text-[11px] text-purple-200">
            Opposite Xperia Mall, Lodha Heaven, Nilje, Kalyan-Shilphata Road, Dombivli East (PIN: 421204).
          </p>
        </div>
      </div>

      {/* List of Site Visit Calls */}
      {calls.length === 0 ? (
        <div className="p-12 text-center bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800">
          <CalendarCheck className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
          <p className="text-sm font-bold text-slate-700 dark:text-slate-300">No Site Visits Found</p>
          <p className="text-xs text-slate-400 mt-1">There are no site visit appointments in this selected time range.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {calls.map(call => (
            <RetainedCallCard key={call.id} call={call} />
          ))}
        </div>
      )}
    </div>
  );
}
