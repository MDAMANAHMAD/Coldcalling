'use client';

import { TimeFilterPeriod } from '@/lib/sarvamTypes';
import { Calendar, Filter } from 'lucide-react';

interface PeriodFilterBarProps {
  currentPeriod: TimeFilterPeriod;
  onPeriodChange: (p: TimeFilterPeriod) => void;
  className?: string;
}

export default function PeriodFilterBar({ currentPeriod, onPeriodChange, className = '' }: PeriodFilterBarProps) {
  const options: { id: TimeFilterPeriod; label: string }[] = [
    { id: 'today', label: 'Today' },
    { id: 'yesterday', label: 'Yesterday' },
    { id: 'last_7_days', label: 'Last 7 Days' },
    { id: 'last_30_days', label: 'Last 30 Days' },
    { id: 'all', label: 'All Time' }
  ];

  return (
    <div className={`flex flex-wrap items-center gap-2 bg-slate-100 dark:bg-slate-800/80 p-1.5 rounded-xl border border-slate-200/80 dark:border-slate-700/60 ${className}`}>
      <div className="flex items-center gap-1.5 px-2.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
        <Filter className="w-3.5 h-3.5" />
        <span>Time Period:</span>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {options.map(opt => {
          const isActive = currentPeriod === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => onPeriodChange(opt.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-blue-600 text-white shadow-sm font-semibold'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
