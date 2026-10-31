'use client';

import { useState } from 'react';
import { LiveCampaignProgress } from '@/lib/sarvamTypes';
import { 
  Activity, 
  PhoneCall, 
  CheckCircle, 
  Clock, 
  AlertCircle, 
  RefreshCw, 
  Play, 
  Pause, 
  Square,
  Settings,
  Calendar,
  Zap
} from 'lucide-react';

interface LiveCallingCardProps {
  campaign: LiveCampaignProgress | null;
  onRefresh?: () => void;
  isLoading?: boolean;
  onAction?: (action: 'start' | 'pause' | 'stop') => void;
  onOpenSettings?: () => void;
}

export default function LiveCallingCard({ campaign, onRefresh, isLoading = false, onAction, onOpenSettings }: LiveCallingCardProps) {
  const [actionLoading, setActionLoading] = useState(false);

  const handleControl = async (act: 'start' | 'pause' | 'stop') => {
    if (onAction) {
      onAction(act);
      return;
    }
    setActionLoading(true);
    try {
      await fetch('/api/campaign/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: act })
      });
      if (onRefresh) onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const status = campaign?.status || 'idle';
  const isRunning = status === 'running' || status === 'active';
  const isPaused = status === 'paused';
  const isCompleted = status === 'completed';

  const totalContacts = campaign?.totalContacts || 0;
  const completedCalls = campaign?.completedCalls || 0;
  const remainingCalls = campaign?.remainingCalls || 0;
  const completionPercent = totalContacts > 0 ? Math.min(100, Math.round((completedCalls / totalContacts) * 100)) : 0;

  return (
    <div className="bg-gradient-to-br from-white to-slate-50/50 dark:from-slate-900 dark:to-slate-900/80 border border-blue-200/60 dark:border-blue-900/40 rounded-3xl p-6 shadow-sm space-y-5">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="relative">
            <div className="w-12 h-12 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <Activity className={`w-6 h-6 ${isRunning ? 'animate-pulse text-emerald-500' : ''}`} />
            </div>
            {isRunning && (
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500"></span>
              </span>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                Calling Sheet Controller & Live Progress
              </h3>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider border ${
                  isRunning
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800'
                    : isPaused
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400 border-amber-300 dark:border-amber-800'
                    : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700'
                }`}
              >
                {status}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Campaign: <span className="font-semibold text-slate-700 dark:text-slate-300">{campaign?.campaignName || 'Sai Garden Calling Sheet'}</span>
              {campaign?.currentBatchFile && ` — Batch: ${campaign.currentBatchFile}`}
            </p>
          </div>
        </div>

        {/* Action Controls: Start, Pause, Stop, Settings & Sync */}
        <div className="flex items-center gap-2 flex-wrap">
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors border border-slate-200 dark:border-slate-700"
              title="Campaign Scheduling & Call Configuration"
            >
              <Settings className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
              <span>Call Settings</span>
            </button>
          )}

          {!isRunning ? (
            <button
              onClick={() => handleControl('start')}
              disabled={actionLoading || totalContacts === 0}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Start Calling</span>
            </button>
          ) : (
            <button
              onClick={() => handleControl('pause')}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-amber-500 hover:bg-amber-600 text-white shadow-sm transition-all"
            >
              <Pause className="w-3.5 h-3.5 fill-current" />
              <span>Pause Calling</span>
            </button>
          )}

          <button
            onClick={() => handleControl('stop')}
            disabled={actionLoading || status === 'idle' || isCompleted}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-rose-600 hover:bg-rose-700 text-white shadow-sm transition-all disabled:opacity-50"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>Stop</span>
          </button>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Sync</span>
            </button>
          )}
        </div>
      </div>

      {/* Quick Settings Pill Summary */}
      <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 font-medium">
          <Zap className="w-3 h-3 text-blue-500" />
          <span>Pacing: <strong>0.5 CPS (1 call / 2s)</strong></span>
        </span>
        <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 font-medium">
          <Clock className="w-3 h-3 text-indigo-500" />
          <span>Calling Window: <strong>09:00 AM - 06:00 PM</strong></span>
        </span>
        <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 font-medium">
          <Calendar className="w-3 h-3 text-emerald-500" />
          <span>Schedule: <strong>All Days Active</strong></span>
        </span>
        <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 font-medium">
          <PhoneCall className="w-3 h-3 text-purple-500" />
          <span>Caller Trunk: <strong>+918071580297</strong></span>
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-semibold">
          <span className="text-slate-600 dark:text-slate-400">Sheet Progress & Pacing</span>
          <span className="text-blue-600 dark:text-blue-400 font-bold">{completionPercent}% ({completedCalls} / {totalContacts} Contacts)</span>
        </div>
        <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden p-0.5 border border-slate-200 dark:border-slate-700">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-500"
            style={{ width: `${completionPercent}%` }}
          />
        </div>
      </div>

      {/* Metric Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-2xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
            <span>Completed</span>
          </div>
          <p className="text-xl font-bold text-slate-900 dark:text-white">{completedCalls}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-2xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <Clock className="w-3.5 h-3.5 text-amber-500" />
            <span>Remaining</span>
          </div>
          <p className="text-xl font-bold text-slate-900 dark:text-white">{remainingCalls}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-2xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <PhoneCall className="w-3.5 h-3.5 text-blue-500" />
            <span>Interested</span>
          </div>
          <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{campaign?.interestedCount || 0}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-2xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <AlertCircle className="w-3.5 h-3.5 text-purple-500" />
            <span>Site Visits</span>
          </div>
          <p className="text-xl font-bold text-purple-600 dark:text-purple-400">{campaign?.siteVisitCount || 0}</p>
        </div>
      </div>
    </div>
  );
}
