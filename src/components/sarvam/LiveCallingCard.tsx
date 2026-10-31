'use client';

import { LiveCampaignProgress } from '@/lib/sarvamTypes';
import { Activity, PhoneCall, CheckCircle, Clock, AlertCircle, RefreshCw } from 'lucide-react';

interface LiveCallingCardProps {
  campaign: LiveCampaignProgress | null;
  onRefresh?: () => void;
  isLoading?: boolean;
}

export default function LiveCallingCard({ campaign, onRefresh, isLoading = false }: LiveCallingCardProps) {
  if (!campaign) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400">
              <PhoneCall className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">No Active Calling Sheet</h3>
              <p className="text-xs text-slate-400">Upload a verified Sarvam CSV cohort to begin live outbound calls.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const completionPercent = campaign.totalContacts > 0
    ? Math.min(100, Math.round((campaign.completedCalls / campaign.totalContacts) * 100))
    : 0;

  return (
    <div className="bg-gradient-to-br from-white to-slate-50/50 dark:from-slate-900 dark:to-slate-900/80 border border-blue-200/60 dark:border-blue-900/40 rounded-2xl p-5 shadow-sm">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-11 h-11 rounded-xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <Activity className="w-6 h-6 animate-pulse" />
            </div>
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                Live Calling Sheet Progress
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800">
                {campaign.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Current Campaign: <span className="font-semibold text-slate-700 dark:text-slate-300">{campaign.campaignName}</span>
              {campaign.currentBatchFile && ` (${campaign.currentBatchFile})`}
            </p>
          </div>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="self-start md:self-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Sync Live</span>
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="space-y-1.5 mb-5">
        <div className="flex justify-between text-xs font-semibold">
          <span className="text-slate-600 dark:text-slate-400">Completion Rate</span>
          <span className="text-blue-600 dark:text-blue-400">{completionPercent}% ({campaign.completedCalls} / {campaign.totalContacts} Contacts)</span>
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
        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
            <span>Completed</span>
          </div>
          <p className="text-xl font-bold text-slate-900 dark:text-white">{campaign.completedCalls}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <Clock className="w-3.5 h-3.5 text-amber-500" />
            <span>Remaining</span>
          </div>
          <p className="text-xl font-bold text-slate-900 dark:text-white">{campaign.remainingCalls}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <PhoneCall className="w-3.5 h-3.5 text-blue-500" />
            <span>Interested</span>
          </div>
          <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{campaign.interestedCount}</p>
        </div>

        <div className="bg-white dark:bg-slate-800/80 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/60">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium mb-1">
            <AlertCircle className="w-3.5 h-3.5 text-purple-500" />
            <span>Site Visits</span>
          </div>
          <p className="text-xl font-bold text-purple-600 dark:text-purple-400">{campaign.siteVisitCount}</p>
        </div>
      </div>
    </div>
  );
}
