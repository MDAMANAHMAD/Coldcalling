'use client';

import React, { useState } from 'react';
import { CampaignSettings } from '@/lib/sarvamTypes';
import { 
  X, 
  Settings2, 
  PhoneCall, 
  Clock, 
  Calendar, 
  Sliders, 
  ShieldCheck, 
  Play, 
  Sparkles,
  PhoneForwarded,
  Check
} from 'lucide-react';

interface CampaignConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLaunch: (settings: CampaignSettings) => void;
  totalContacts?: number;
}

const DEFAULT_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const DAY_ABBR = [
  { full: 'Monday', label: 'M' },
  { full: 'Tuesday', label: 'T' },
  { full: 'Wednesday', label: 'W' },
  { full: 'Thursday', label: 'T' },
  { full: 'Friday', label: 'F' },
  { full: 'Saturday', label: 'S' },
  { full: 'Sunday', label: 'S' }
];

export default function CampaignConfigModal({ isOpen, onClose, onLaunch, totalContacts = 0 }: CampaignConfigModalProps) {
  const [activeTab, setActiveTab] = useState<'agent' | 'schedule' | 'advanced'>('agent');
  
  // Settings with exact Sarvam defaults
  const [campaignName, setCampaignName] = useState(`Sai Garden Outreach - ${new Date().toLocaleDateString('en-GB')}`);
  const [cps, setCps] = useState<number>(0.5);
  const [startDateType, setStartDateType] = useState<'now' | 'custom'>('now');
  const [endDateType, setEndDateType] = useState<'today' | 'custom'>('today');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [allowedStartTime, setAllowedStartTime] = useState('09:00');
  const [allowedEndTime, setAllowedEndTime] = useState('18:00');
  const [allowedDays, setAllowedDays] = useState<string[]>(DEFAULT_DAYS);
  const [retryEnabled, setRetryEnabled] = useState(false);
  const [maxRetries, setMaxRetries] = useState(2);
  const [retryInterval, setRetryInterval] = useState(15);
  
  // Test dial states
  const [testNumber, setTestNumber] = useState('');
  const [testDialing, setTestDialing] = useState(false);
  const [testDialSuccess, setTestDialSuccess] = useState<string | null>(null);
  const [testDialError, setTestDialError] = useState<string | null>(null);

  if (!isOpen) return null;

  const toggleDay = (day: string) => {
    if (allowedDays.includes(day)) {
      if (allowedDays.length > 1) {
        setAllowedDays(allowedDays.filter(d => d !== day));
      }
    } else {
      setAllowedDays([...allowedDays, day]);
    }
  };

  const handleTestDial = async () => {
    if (!testNumber) {
      setTestDialError('Please enter a phone number to test');
      return;
    }
    setTestDialing(true);
    setTestDialSuccess(null);
    setTestDialError(null);

    try {
      const res = await fetch('/api/campaign/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'test-dial',
          testPhoneNumber: testNumber,
          settings: {
            agentId: 'Gayatari-0922c4e8-551f',
            agentVersion: 2,
            connectionId: 'Vobiz-MD-s--9a5a5823-1853',
            fromNumber: '+918071580297'
          }
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setTestDialSuccess(`Dial initiated! Attempt ID: ${data.attempt_id}`);
      } else {
        setTestDialError(data.error || 'Failed to place test call');
      }
    } catch (e: any) {
      setTestDialError(e.message || 'Error executing test dial');
    } finally {
      setTestDialing(false);
    }
  };

  const handleLaunch = () => {
    const settings: CampaignSettings = {
      campaignName,
      appType: 'agent',
      agentId: 'Gayatari-0922c4e8-551f',
      agentVersion: 2,
      connectionId: 'Vobiz-MD-s--9a5a5823-1853',
      fromNumber: '+918071580297',
      attemptsPerSecond: cps,
      allowedStartTime,
      allowedEndTime,
      allowedDays,
      startDateType,
      endDateType,
      customStartDate,
      customEndDate,
      retryEnabled,
      maxRetries,
      retryIntervalMinutes: retryInterval,
      phoneRotation: false
    };

    onLaunch(settings);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <Settings2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-slate-900 dark:text-white">
                Outbound Campaign Configuration
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Configure telephony pacing, dialing schedule, and verified connection
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-100 dark:border-slate-800 px-6 pt-2 bg-slate-50/50 dark:bg-slate-850/50">
          <button
            onClick={() => setActiveTab('agent')}
            className={`pb-3 px-3 text-xs font-bold transition-all relative ${
              activeTab === 'agent'
                ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            1. Agent & Caller
          </button>
          <button
            onClick={() => setActiveTab('schedule')}
            className={`pb-3 px-3 text-xs font-bold transition-all relative ${
              activeTab === 'schedule'
                ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            2. Schedule & Pacing
          </button>
          <button
            onClick={() => setActiveTab('advanced')}
            className={`pb-3 px-3 text-xs font-bold transition-all relative ${
              activeTab === 'advanced'
                ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            3. Retries & Test Dial
          </button>
        </div>

        {/* Content Area */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {activeTab === 'agent' && (
            <div className="space-y-4 animate-in fade-in">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                  Campaign Name *
                </label>
                <input
                  type="text"
                  value={campaignName}
                  onChange={e => setCampaignName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[11px] font-bold text-slate-400 uppercase">App-Type</span>
                  <p className="text-sm font-bold text-slate-800 dark:text-slate-200 mt-0.5">Voice Agent</p>
                </div>
                <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[11px] font-bold text-slate-400 uppercase">Selected Agent</span>
                  <p className="text-sm font-bold text-blue-600 dark:text-blue-400 mt-0.5">Gayatari (v2)</p>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-900/40 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-900 dark:text-blue-200">Verified Telephony Trunk</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                    Connected
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300 pt-1">
                  <span>Connection:</span>
                  <span className="font-bold">Vobiz MD&apos;s Organisation connection</span>
                </div>
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                  <span>Outbound Caller Number:</span>
                  <span className="font-mono font-bold text-slate-900 dark:text-white">+918071580297</span>
                </div>
              </div>

              {totalContacts > 0 && (
                <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800 text-xs text-slate-600 dark:text-slate-300 flex items-center justify-between font-semibold">
                  <span>Target Cohort Contacts:</span>
                  <span className="font-extrabold text-blue-600 dark:text-blue-400">{totalContacts} verified numbers</span>
                </div>
              )}
            </div>
          )}

          {activeTab === 'schedule' && (
            <div className="space-y-4 animate-in fade-in">
              {/* Campaign Period */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">
                  Campaign Period
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-2">
                    <span className="text-[11px] font-bold text-slate-500">Start Time</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setStartDateType('now')}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                          startDateType === 'now'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        Now
                      </button>
                      <button
                        type="button"
                        onClick={() => setStartDateType('custom')}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                          startDateType === 'custom'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        Custom
                      </button>
                    </div>
                  </div>

                  <div className="p-3 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-2">
                    <span className="text-[11px] font-bold text-slate-500">End Time</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setEndDateType('today')}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                          endDateType === 'today'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        Today
                      </button>
                      <button
                        type="button"
                        onClick={() => setEndDateType('custom')}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                          endDateType === 'custom'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        Custom
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Attempts per second (CPS) */}
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Attempts Per Second (CPS) *
                  </label>
                  <span className="text-xs font-bold text-blue-600 dark:text-blue-400">{cps} calls/sec</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[0.2, 0.5, 1.0, 2.0].map(val => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setCps(val)}
                      className={`py-2 text-xs font-extrabold rounded-xl border transition-all ${
                        cps === val
                          ? 'border-blue-600 bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 shadow-sm'
                          : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                      }`}
                    >
                      {val} {val === 0.5 ? '(Default)' : ''}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">Default 0.5 calls/sec prevents telecom throttling</p>
              </div>

              {/* Allowed Days */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                  Allowed Days *
                </label>
                <div className="flex items-center gap-2">
                  {DAY_ABBR.map((item, idx) => {
                    const isSelected = allowedDays.includes(item.full);
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => toggleDay(item.full)}
                        className={`w-9 h-9 rounded-full text-xs font-extrabold flex items-center justify-center transition-all ${
                          isSelected
                            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-400 hover:bg-slate-200'
                        }`}
                        title={item.full}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Calling Window */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                  Calls Allowed Between *
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="time"
                    value={allowedStartTime}
                    onChange={e => setAllowedStartTime(e.target.value)}
                    className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold bg-white dark:bg-slate-800"
                  />
                  <span className="text-xs text-slate-400 font-bold">to</span>
                  <input
                    type="time"
                    value={allowedEndTime}
                    onChange={e => setAllowedEndTime(e.target.value)}
                    className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold bg-white dark:bg-slate-800"
                  />
                  <span className="text-[11px] text-slate-400">(Default: 09:00 AM - 06:00 PM)</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="space-y-4 animate-in fade-in">
              {/* Retry Configuration */}
              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-extrabold text-slate-900 dark:text-white">Retry Configuration</p>
                    <p className="text-[11px] text-slate-400">Retry contacts if line is busy or unanswered</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setRetryEnabled(!retryEnabled)}
                    className={`w-11 h-6 rounded-full transition-colors relative p-0.5 ${
                      retryEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'
                    }`}
                  >
                    <div
                      className={`w-5 h-5 rounded-full bg-white transition-transform ${
                        retryEnabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {retryEnabled && (
                  <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-200 dark:border-slate-700">
                    <div>
                      <span className="text-[11px] font-bold text-slate-500">Max Retries</span>
                      <select
                        value={maxRetries}
                        onChange={e => setMaxRetries(Number(e.target.value))}
                        className="w-full mt-1 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold"
                      >
                        <option value={1}>1 Retry</option>
                        <option value={2}>2 Retries (Default)</option>
                        <option value={3}>3 Retries</option>
                      </select>
                    </div>
                    <div>
                      <span className="text-[11px] font-bold text-slate-500">Retry Interval</span>
                      <select
                        value={retryInterval}
                        onChange={e => setRetryInterval(Number(e.target.value))}
                        className="w-full mt-1 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold"
                      >
                        <option value={5}>5 Minutes</option>
                        <option value={15}>15 Minutes (Default)</option>
                        <option value={30}>30 Minutes</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Instant Test Dial */}
              <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-50/60 to-blue-50/40 dark:from-indigo-950/20 dark:to-blue-950/20 border border-indigo-200/60 dark:border-indigo-900/40 space-y-3">
                <div className="flex items-center gap-2">
                  <PhoneForwarded className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                  <span className="text-xs font-extrabold text-indigo-950 dark:text-indigo-200">
                    Test Dial (Recommended before Launch)
                  </span>
                </div>
                <p className="text-[11px] text-slate-600 dark:text-slate-400">
                  Receive an instant test call on your mobile to verify Gayatri&apos;s greeting and audio flow.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="tel"
                    placeholder="+919876543210"
                    value={testNumber}
                    onChange={e => setTestNumber(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold text-slate-900 dark:text-white"
                  />
                  <button
                    type="button"
                    onClick={handleTestDial}
                    disabled={testDialing}
                    className="px-3.5 py-2 text-xs font-bold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-all disabled:opacity-50"
                  >
                    {testDialing ? 'Calling...' : 'Dial Now'}
                  </button>
                </div>

                {testDialSuccess && (
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 text-[11px] font-bold flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5" />
                    <span>{testDialSuccess}</span>
                  </div>
                )}
                {testDialError && (
                  <div className="p-2 rounded-lg bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 text-[11px] font-bold">
                    {testDialError}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-850/50 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span>Sai Garden Telephony Protocol</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-bold rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleLaunch}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white shadow-md hover:shadow-lg transition-all"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Launch Campaign</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
