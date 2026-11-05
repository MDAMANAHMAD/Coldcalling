'use client';

import { useState, useEffect, useCallback } from 'react';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import { SarvamAnalyticsSummary, TimeFilterPeriod } from '@/lib/sarvamTypes';
import { 
  BarChart3, 
  TrendingUp, 
  Clock, 
  Building, 
  Target,
  RefreshCw,
  PhoneCall,
  CheckCircle2,
  CalendarCheck,
  Sparkles,
  Info
} from 'lucide-react';

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [analytics, setAnalytics] = useState<SarvamAnalyticsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date>(new Date());

  const loadData = useCallback(async (currentPeriod: TimeFilterPeriod, isManualRefresh = false) => {
    if (isManualRefresh) setIsRefreshing(true);
    else setIsLoading(true);

    try {
      const res = await fetch(`/api/calls?period=${currentPeriod}`);
      const data = await res.json();
      setAnalytics(data.analytics || null);
      setLastRefreshedAt(new Date());
    } catch (e) {
      console.error('Failed to load analytics data:', e);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData(period, false);
  }, [period, loadData]);

  const totalCalls = analytics?.totalCalls || 0;
  const connectionRate = analytics?.connectionRate || 0;
  const interestedRate = analytics?.interestedRate || 0;
  const siteVisitRate = analytics?.siteVisitRate || 0;
  const connectedCallsCount = analytics?.connectedCallsCount ?? (totalCalls > 0 ? Math.round((connectionRate * totalCalls) / 100) : 0);

  const totalBhkInquiries = (analytics?.twoBhkCount || 0) + (analytics?.oneBhkCount || 0);
  const twoBhkPct = totalBhkInquiries > 0 ? Math.round(((analytics?.twoBhkCount || 0) / totalBhkInquiries) * 100) : 0;
  const oneBhkPct = totalBhkInquiries > 0 ? Math.round(((analytics?.oneBhkCount || 0) / totalBhkInquiries) * 100) : 0;

  const formatDisplayDate = (dateStr: string) => {
    try {
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' });
      }
      return dateStr;
    } catch {
      return dateStr;
    }
  };

  const periodLabelMap: Record<TimeFilterPeriod, string> = {
    today: 'Today',
    yesterday: 'Yesterday',
    last_7_days: 'Last 7 Days',
    last_30_days: 'Last 30 Days',
    all: 'All Time'
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <span>Sai Garden Telephony Analytics</span>
            <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 ml-2">
              Showing: {periodLabelMap[period]}
            </span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Real-time conversion & conversation metrics for Sai Garden Dombivli East • Last synced: {lastRefreshedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => loadData(period, true)}
            disabled={isRefreshing || isLoading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/80 transition shadow-sm disabled:opacity-50"
            title="Refresh latest interactions from telephony platform"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-blue-600 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>{isRefreshing ? 'Syncing...' : 'Sync'}</span>
          </button>
          <PeriodFilterBar currentPeriod={period} onPeriodChange={setPeriod} />
        </div>
      </div>

      {/* Outbound Conversion Funnel */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
        <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-600" />
          <span>Outbound Conversion Funnel</span>
          <span className="text-[10px] font-semibold text-slate-400">({periodLabelMap[period]})</span>
        </h3>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-pulse">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-28 rounded-2xl bg-slate-100 dark:bg-slate-800" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/60 transition-all hover:border-slate-300">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">1. Total Calls Made</span>
                <PhoneCall className="w-4 h-4 text-slate-400" />
              </div>
              <p className="text-2xl font-black text-slate-900 dark:text-white mt-1">{totalCalls}</p>
              <span className="text-[11px] text-slate-400 font-medium">100% Outreach Base</span>
            </div>

            <div className="p-4 rounded-2xl bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-800/40 transition-all hover:border-blue-300">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">2. Calls Connected</span>
                <CheckCircle2 className="w-4 h-4 text-blue-500" />
              </div>
              <p className="text-2xl font-black text-blue-700 dark:text-blue-400 mt-1">{connectionRate}%</p>
              <span className="text-[11px] text-blue-500 font-medium">{connectedCallsCount} of {totalCalls} Connected</span>
            </div>

            <div className="p-4 rounded-2xl bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200/60 dark:border-emerald-800/40 transition-all hover:border-emerald-300">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">3. Positive Intent</span>
                <Sparkles className="w-4 h-4 text-emerald-500" />
              </div>
              <p className="text-2xl font-black text-emerald-700 dark:text-emerald-400 mt-1">{analytics?.interestedCount || 0}</p>
              <span className="text-[11px] text-emerald-600 font-medium">{interestedRate}% of calls engaged</span>
            </div>

            <div className="p-4 rounded-2xl bg-purple-50/60 dark:bg-purple-950/20 border border-purple-200/60 dark:border-purple-800/40 transition-all hover:border-purple-300">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-purple-600 dark:text-purple-400">4. Confirmed Site Visits</span>
                <CalendarCheck className="w-4 h-4 text-purple-500" />
              </div>
              <p className="text-2xl font-black text-purple-700 dark:text-purple-400 mt-1">{analytics?.siteVisitCount || 0}</p>
              <span className="text-[11px] text-purple-600 font-medium">{siteVisitRate}% Appointment Conversion</span>
            </div>
          </div>
        )}
      </div>

      {/* Deep Metric Grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Call Duration */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-2">
            <Clock className="w-4 h-4 text-indigo-600" />
            <span>Call Engagement & Duration</span>
          </h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60">
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Average Call Duration</span>
              <span className="text-sm font-extrabold text-blue-600 dark:text-blue-400">
                {analytics?.avgDurationSeconds ? `${Math.floor(analytics.avgDurationSeconds / 60)}m ${analytics.avgDurationSeconds % 60}s` : '0m 0s'}
              </span>
            </div>

            <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60">
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Total Talk Time</span>
              <span className="text-sm font-extrabold text-slate-900 dark:text-white">
                {analytics?.totalDurationSeconds ? `${Math.round(analytics.totalDurationSeconds / 60)} Minutes` : '0 Minutes'}
              </span>
            </div>

            <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60">
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Voice Response Latency</span>
              <span className="text-sm font-extrabold text-emerald-600 dark:text-emerald-400">&lt; 0.9s Sub-second</span>
            </div>
          </div>
        </div>

        {/* Property Configuration Preference */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-2">
            <Building className="w-4 h-4 text-blue-600" />
            <span>Buyer Configuration Preference</span>
          </h3>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs font-bold mb-1">
                <span className="text-slate-700 dark:text-slate-300">2 BHK Luxury Homes (₹45 Lakh+)</span>
                <span className="text-blue-600 dark:text-blue-400">
                  {analytics?.twoBhkCount || 0} Inquiries {totalBhkInquiries > 0 ? `(${twoBhkPct}%)` : ''}
                </span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 rounded-full transition-all duration-500"
                  style={{
                    width: `${twoBhkPct}%`
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-bold mb-1">
                <span className="text-slate-700 dark:text-slate-300">1 BHK Compact Luxury (₹30 Lakh+)</span>
                <span className="text-emerald-600 dark:text-emerald-400">
                  {analytics?.oneBhkCount || 0} Inquiries {totalBhkInquiries > 0 ? `(${oneBhkPct}%)` : ''}
                </span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                  style={{
                    width: `${oneBhkPct}%`
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Daily Trends Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
        <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-emerald-600" />
          <span>Daily Call Pacing & Lead Acquisition</span>
          <span className="text-[10px] font-semibold text-slate-400">({periodLabelMap[period]} • Sorted Newest to Oldest)</span>
        </h3>

        {isLoading ? (
          <div className="space-y-2 animate-pulse py-4">
            <div className="h-10 bg-slate-100 dark:bg-slate-800 rounded-xl" />
            <div className="h-10 bg-slate-100 dark:bg-slate-800 rounded-xl" />
            <div className="h-10 bg-slate-100 dark:bg-slate-800 rounded-xl" />
          </div>
        ) : analytics?.dailyTrends && analytics.dailyTrends.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 font-bold uppercase tracking-wider">
                <tr>
                  <th className="p-3">Date</th>
                  <th className="p-3">Total Calls</th>
                  <th className="p-3">Interested Buyers</th>
                  <th className="p-3">Site Visits Booked</th>
                  <th className="p-3">Engagement Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {analytics.dailyTrends.map(day => {
                  const engagementRate = day.calls > 0 ? Math.round(((day.interested + day.siteVisits) / day.calls) * 100) : 0;
                  return (
                    <tr key={day.date} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                      <td className="p-3 font-semibold text-slate-900 dark:text-white">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-slate-400 text-[11px]">{day.date}</span>
                          <span className="font-bold text-slate-800 dark:text-slate-200">({formatDisplayDate(day.date)})</span>
                        </div>
                      </td>
                      <td className="p-3 font-bold text-slate-900 dark:text-white">{day.calls}</td>
                      <td className="p-3 font-bold text-emerald-600 dark:text-emerald-400">{day.interested}</td>
                      <td className="p-3 font-bold text-purple-600 dark:text-purple-400">{day.siteVisits}</td>
                      <td className="p-3 font-bold text-blue-600 dark:text-blue-400">{engagementRate}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-10 text-center flex flex-col items-center justify-center gap-2 text-slate-400">
            <Info className="w-8 h-8 text-slate-300 dark:text-slate-600" />
            <p className="text-sm font-semibold text-slate-600 dark:text-slate-400">
              No calls recorded for {periodLabelMap[period].toLowerCase()}
            </p>
            <p className="text-xs text-slate-400">
              When new calls are placed in this period, real-time pacing and leads will appear here automatically.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
