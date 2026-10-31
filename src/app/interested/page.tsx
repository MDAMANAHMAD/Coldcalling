'use client';

import { useState, useEffect } from 'react';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import RetainedCallCard from '@/components/sarvam/RetainedCallCard';
import { SarvamCallRecord, TimeFilterPeriod } from '@/lib/sarvamTypes';
import { exportToCsv, exportToPdf } from '@/lib/sarvamExport';
import { HeartHandshake, FileSpreadsheet, FileDown, Flame } from 'lucide-react';

export default function InterestedPage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [calls, setCalls] = useState<SarvamCallRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/calls?period=${period}&category=Interested`);
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
            <HeartHandshake className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            <span>Interested Prospective Buyers</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Prospects who expressed intent, requested WhatsApp floor plans/brochure, or asked about pricing & down payment.
          </p>
        </div>

        {/* Download Buttons with unmasked phone numbers */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => exportToCsv(calls, 'Interested')}
            disabled={calls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 shadow-sm transition-all disabled:opacity-50"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
            <span>Download CSV (Full Numbers)</span>
          </button>

          <button
            onClick={() => exportToPdf(calls, 'Interested', period)}
            disabled={calls.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all disabled:opacity-50"
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
          Showing {calls.length} Interested Prospects
        </span>
      </div>

      {/* List of Interested Calls */}
      {calls.length === 0 ? (
        <div className="p-12 text-center bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800">
          <Flame className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
          <p className="text-sm font-bold text-slate-700 dark:text-slate-300">No Interested Prospects Found</p>
          <p className="text-xs text-slate-400 mt-1">High-intent callers who request brochure details will appear here automatically.</p>
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
