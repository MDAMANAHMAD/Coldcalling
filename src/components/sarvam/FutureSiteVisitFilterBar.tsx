'use client';

import { Calendar, Sparkles } from 'lucide-react';

export type FutureFilterPeriod = 'all_upcoming' | 'this_weekend' | 'next_7_days' | 'next_30_days' | 'all';

interface FutureSiteVisitFilterBarProps {
  currentPeriod: FutureFilterPeriod;
  onPeriodChange: (period: FutureFilterPeriod) => void;
}

const FILTER_OPTIONS: { id: FutureFilterPeriod; label: string }[] = [
  { id: 'all_upcoming', label: 'All Upcoming Visits' },
  { id: 'this_weekend', label: 'This Weekend (Sat/Sun)' },
  { id: 'next_7_days', label: 'Next 7 Days' },
  { id: 'next_30_days', label: 'Next 30 Days' },
  { id: 'all', label: 'All Visits' }
];

export default function FutureSiteVisitFilterBar({ currentPeriod, onPeriodChange }: FutureSiteVisitFilterBarProps) {
  return (
    <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-800/80 rounded-2xl overflow-x-auto max-w-full">
      <div className="hidden sm:flex items-center gap-1 pl-2.5 pr-1 text-slate-500 text-xs font-bold">
        <Calendar className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
        <span className="text-[11px] uppercase tracking-wider">Visit Schedule:</span>
      </div>

      {FILTER_OPTIONS.map(opt => {
        const isActive = currentPeriod === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onPeriodChange(opt.id)}
            className={`px-3 py-1.5 text-xs font-bold rounded-xl transition-all whitespace-nowrap ${
              isActive
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-slate-700/50'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
