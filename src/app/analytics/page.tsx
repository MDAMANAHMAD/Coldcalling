'use client';

import { useState, useEffect } from 'react';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import { SarvamAnalyticsSummary, TimeFilterPeriod } from '@/lib/sarvamTypes';
import { 
  BarChart3, 
  TrendingUp, 
  Clock, 
  Building, 
  Target
} from 'lucide-react';

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [analytics, setAnalytics] = useState<SarvamAnalyticsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/calls?period=${period}`);
        const data = await res.json();
        setAnalytics(data.analytics || null);
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [period]);

  const totalCalls = analytics?.totalCalls || 0;
  const connectionRate = analytics?.connectionRate || 0;
  const interestedRate = analytics?.interestedRate || 0;
  const siteVisitRate = analytics?.siteVisitRate || 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <span>Sai Garden Telephony Analytics</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Real-time conversion & conversation metrics for Sai Garden Dombivli East
          </p>
        </div>
        <PeriodFilterBar currentPeriod={period} onPeriodChange={setPeriod} />
      </div>

      {/* Conversion Funnel */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
        <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-600" />
          <span>Outbound Conversion Funnel</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/60">
            <span className="text-xs font-semibold text-slate-500">1. Total Calls Made</span>
            <p className="text-2xl font-black text-slate-900 dark:text-white mt-1">{totalCalls}</p>
            <span className="text-[11px] text-slate-400 font-medium">100% Outreach Base</span>
          </div>

          <div className="p-4 rounded-2xl bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-800/40">
            <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">2. Calls Connected</span>
            <p className="text-2xl font-black text-blue-700 dark:text-blue-400 mt-1">{connectionRate}%</p>
            <span className="text-[11px] text-blue-500 font-medium">Telephony Picked Up</span>
          </div>

          <div className="p-4 rounded-2xl bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200/60 dark:border-emerald-800/40">
            <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">3. Positive Intent</span>
            <p className="text-2xl font-black text-emerald-700 dark:text-emerald-400 mt-1">{analytics?.interestedCount || 0}</p>
            <span className="text-[11px] text-emerald-600 font-medium">{interestedRate}% of calls engaged</span>
          </div>

          <div className="p-4 rounded-2xl bg-purple-50/60 dark:bg-purple-950/20 border border-purple-200/60 dark:border-purple-800/40">
            <span className="text-xs font-semibold text-purple-600 dark:text-purple-400">4. Confirmed Site Visits</span>
            <p className="text-2xl font-black text-purple-700 dark:text-purple-400 mt-1">{analytics?.siteVisitCount || 0}</p>
            <span className="text-[11px] text-purple-600 font-medium">{siteVisitRate}% Appointment Conversion</span>
          </div>
        </div>
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
                <span className="text-blue-600 dark:text-blue-400">{analytics?.twoBhkCount || 0} Inquiries</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 rounded-full"
                  style={{
                    width: `${totalCalls > 0 ? ((analytics?.twoBhkCount || 0) / totalCalls) * 100 : 0}%`
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-bold mb-1">
                <span className="text-slate-700 dark:text-slate-300">1 BHK Compact Luxury (₹35 Lakh+)</span>
                <span className="text-emerald-600 dark:text-emerald-400">{analytics?.oneBhkCount || 0} Inquiries</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{
                    width: `${totalCalls > 0 ? ((analytics?.oneBhkCount || 0) / totalCalls) * 100 : 0}%`
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Daily Trends Table */}
      {analytics?.dailyTrends && analytics.dailyTrends.length > 0 && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
          <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-600" />
            <span>Daily Call Pacing & Lead Acquisition</span>
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 font-bold uppercase tracking-wider">
                <tr>
                  <th className="p-3">Date</th>
                  <th className="p-3">Total Calls</th>
                  <th className="p-3">Interested Buyers</th>
                  <th className="p-3">Site Visits Booked</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {analytics.dailyTrends.map(day => (
                  <tr key={day.date} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                    <td className="p-3 font-semibold text-slate-900 dark:text-white">{day.date}</td>
                    <td className="p-3 font-bold">{day.calls}</td>
                    <td className="p-3 font-bold text-emerald-600 dark:text-emerald-400">{day.interested}</td>
                    <td className="p-3 font-bold text-purple-600 dark:text-purple-400">{day.siteVisits}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
