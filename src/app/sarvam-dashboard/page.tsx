'use client';

import { useState, useEffect } from 'react';
import CsvVerificationUploader from '@/components/sarvam/CsvVerificationUploader';
import LiveCallingCard from '@/components/sarvam/LiveCallingCard';
import PeriodFilterBar from '@/components/sarvam/PeriodFilterBar';
import RetainedCallCard from '@/components/sarvam/RetainedCallCard';
import { 
  SarvamCallRecord, 
  LiveCampaignProgress, 
  SarvamAnalyticsSummary, 
  TimeFilterPeriod, 
  CsvValidationResult 
} from '@/lib/sarvamTypes';
import { 
  Building2, 
  PhoneCall, 
  Calendar, 
  Users, 
  Flame, 
  ArrowUpRight, 
  CheckCircle, 
  ShieldCheck, 
  FileSpreadsheet,
  Download
} from 'lucide-react';
import Link from 'next/link';

export default function SarvamHomePage() {
  const [period, setPeriod] = useState<TimeFilterPeriod>('all');
  const [calls, setCalls] = useState<SarvamCallRecord[]>([]);
  const [analytics, setAnalytics] = useState<SarvamAnalyticsSummary | null>(null);
  const [campaign, setCampaign] = useState<LiveCampaignProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchDashboardData = async (filterPeriod: TimeFilterPeriod) => {
    setIsLoading(true);
    try {
      const res = await fetch(`/api/sarvam/calls?period=${filterPeriod}`);
      const data = await res.json();
      setCalls(data.calls || []);
      setAnalytics(data.analytics || null);
      setCampaign(data.liveCampaign || null);
    } catch (err) {
      console.error('Error loading Sarvam data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData(period);
  }, [period]);

  const handleCsvValidated = (result: CsvValidationResult) => {
    // When a new CSV is validated, we update the live sheet representation
    if (result.isValid && result.data.length > 0) {
      setCampaign(prev => ({
        campaignId: `camp-${Date.now()}`,
        campaignName: 'Sai Garden 1 & 2 BHK Outreach',
        totalContacts: result.data.length,
        completedCalls: 0,
        remainingCalls: result.data.length,
        ongoingCalls: 1,
        successfulCalls: 0,
        failedCalls: 0,
        interestedCount: 0,
        siteVisitCount: 0,
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        status: 'running',
        currentBatchFile: 'Verified_Cohort.csv'
      }));
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Hero Welcome Banner */}
      <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 rounded-3xl p-6 md:p-8 text-white shadow-xl relative overflow-hidden">
        <div className="relative z-10 max-w-3xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-400/30">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>MahaRERA: PR1330002501452 | Sai City Group</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-black tracking-tight leading-tight">
            Sai Garden — Sarvam AI Calling Command Center
          </h1>
          <p className="text-sm text-slate-300 leading-relaxed">
            Welcome to the dedicated calling automation and client acquisition engine for Sai Garden, Nilje, Dombivli East (opp. Xperia Mall). Manage contact sheets, track live call pacing, and access high-intent leads with full unmasked phone numbers.
          </p>
        </div>
      </div>

      {/* Live Calling Sheet Progress */}
      <LiveCallingCard
        campaign={campaign}
        onRefresh={() => fetchDashboardData(period)}
        isLoading={isLoading}
      />

      {/* CSV Uploader & Verification Tool */}
      <CsvVerificationUploader onValidated={handleCsvValidated} />

      {/* Basic Metrics Overview with Time Filter */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
              Project Performance & Call Outcomes
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Overview of retained high-intent prospects for Sai Garden
            </p>
          </div>
          <PeriodFilterBar currentPeriod={period} onPeriodChange={setPeriod} />
        </div>

        {/* 4 Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total Calls Processed</span>
              <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                <PhoneCall className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl font-black text-slate-900 dark:text-white">{analytics?.totalCalls || 0}</p>
            <span className="text-[11px] text-slate-400 font-medium">Auto-retrieving from Sarvam AI</span>
          </div>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-purple-600 uppercase tracking-wider">Site Visits Booked</span>
              <div className="w-8 h-8 rounded-lg bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center">
                <Calendar className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl font-black text-purple-600 dark:text-purple-400">{analytics?.siteVisitCount || 0}</p>
            <Link href="/sarvam-dashboard/site-visits" className="text-[11px] text-blue-600 dark:text-blue-400 font-semibold hover:underline flex items-center gap-1 mt-1">
              <span>View Site Visits</span>
              <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Interested Buyers</span>
              <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <Flame className="w-4 h-4" />
              </div>
            </div>
            <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400">{analytics?.interestedCount || 0}</p>
            <Link href="/sarvam-dashboard/interested" className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold hover:underline flex items-center gap-1 mt-1">
              <span>View Interested Leads</span>
              <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-amber-600 uppercase tracking-wider">BHK Distribution</span>
              <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                <Building2 className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div>
                <span className="text-[11px] text-slate-400">1 BHK</span>
                <p className="text-lg font-bold text-slate-900 dark:text-white">{analytics?.oneBhkCount || 0}</p>
              </div>
              <div className="h-6 w-px bg-slate-200 dark:bg-slate-700" />
              <div>
                <span className="text-[11px] text-slate-400">2 BHK</span>
                <p className="text-lg font-bold text-slate-900 dark:text-white">{analytics?.twoBhkCount || 0}</p>
              </div>
            </div>
            <span className="text-[11px] text-slate-400 font-medium">₹30L (1 BHK) | ₹45L (2 BHK)</span>
          </div>
        </div>
      </div>

      {/* Retained High-Intent Call Logs (Interested & Site Visit Only) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
              <span>Retained Prospect Calls</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                Full Phone Numbers & Audio
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Only high-intent prospects (Site Visit & Interested) are archived here with dialogue recordings.
            </p>
          </div>
        </div>

        {calls.length === 0 ? (
          <div className="p-8 text-center bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800">
            <p className="text-sm font-semibold text-slate-500">No calls found for the selected time period.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3.5">
            {calls.map(call => (
              <RetainedCallCard key={call.id} call={call} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
