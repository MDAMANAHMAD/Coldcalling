'use client';

import { useState } from 'react';
import { SarvamCallRecord } from '@/lib/sarvamTypes';
import { formatFullPhoneNumber } from '@/lib/sarvamCsv';
import { 
  Phone, 
  Calendar, 
  Clock, 
  Volume2, 
  FileText, 
  CheckCircle2, 
  Globe2,
  MessageSquare
} from 'lucide-react';

interface RetainedCallCardProps {
  call: SarvamCallRecord;
}

export default function RetainedCallCard({ call }: RetainedCallCardProps) {
  const [showTranscript, setShowTranscript] = useState(false);

  const isSiteVisit = call.outcome === 'Site Visit';
  const isInterested = call.outcome === 'Interested';
  const isConnected = call.outcome === 'Connected';
  const isNotInterested = call.outcome === 'Not Interested';

  const badgeColor = isSiteVisit
    ? 'bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
    : isInterested
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
    : isConnected
    ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
    : isNotInterested
    ? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
    : 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-200 dark:border-amber-800';

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        {/* Customer Information */}
        <div className="space-y-1.5 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-base font-bold text-slate-900 dark:text-white">
              {call.customerName || 'Valued Customer'}
            </h4>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${badgeColor}`}>
              {call.outcome}
            </span>
            {call.bhkPreference && (
              <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                {call.bhkPreference}
              </span>
            )}
            {call.language && (
              <span className="flex items-center gap-1 text-[11px] text-slate-400 font-medium">
                <Globe2 className="w-3 h-3" />
                <span>{call.language}</span>
              </span>
            )}
            {call.numMessages && (
              <span className="flex items-center gap-1 text-[11px] text-slate-400 font-medium">
                <MessageSquare className="w-3 h-3" />
                <span>{call.numMessages} msgs</span>
              </span>
            )}
          </div>

          {/* FULL UNMASKED PHONE NUMBER DISPLAY */}
          <div className="flex items-center gap-2 text-sm font-extrabold text-blue-600 dark:text-blue-400">
            <Phone className="w-4 h-4" />
            <span className="tracking-wide">{formatFullPhoneNumber(call.customerPhone)}</span>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 dark:text-slate-400 pt-1">
            <div className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" />
              <span>{new Date(call.callDate).toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-300">
              <Clock className="w-3.5 h-3.5" />
              <span>
                {call.durationSeconds >= 60 
                  ? `${Math.floor(call.durationSeconds / 60)}m ${Math.round(call.durationSeconds % 60)}s` 
                  : `${call.durationSeconds}s`}
              </span>
            </div>
            {isSiteVisit && call.siteVisitDay && (
              <div className="flex items-center gap-1 text-purple-600 dark:text-purple-400 font-semibold">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Site Visit: {call.siteVisitDay}</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons: Audio & Transcript */}
        <div className="flex items-center gap-2 self-start">
          <button
            onClick={() => setShowTranscript(!showTranscript)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
          >
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span>{showTranscript ? 'Hide Dialogue' : 'View Dialogue'}</span>
          </button>
        </div>
      </div>

      {/* Summary box */}
      {call.summary && (
        <div className="mt-3.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-850/60 border border-slate-100 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          <span className="font-semibold text-slate-800 dark:text-slate-200">AI Conversation Summary: </span>
          {call.summary}
        </div>
      )}

      {/* Audio Player if recording exists */}
      {call.recordingUrl && (
        <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2 mb-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
            <Volume2 className="w-3.5 h-3.5 text-blue-500" />
            <span>Call Audio Recording</span>
          </div>
          <audio controls className="w-full h-8" preload="none">
            <source src={call.recordingUrl} type="audio/wav" />
            <source src={call.recordingUrl} type="audio/mpeg" />
            Your browser does not support audio playback.
          </audio>
        </div>
      )}

      {/* Modal / Inline Full Transcript */}
      {showTranscript && (
        <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800 animate-in fade-in duration-200">
          <div className="flex items-center justify-between mb-2">
            <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Complete Conversation Dialogue
            </h5>
            <button
              onClick={() => setShowTranscript(false)}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              Close
            </button>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-900 text-slate-100 text-xs font-mono max-h-64 overflow-y-auto space-y-1.5 leading-relaxed whitespace-pre-wrap">
            {call.transcript || 'No dialogue transcript recorded for this call.'}
          </div>
        </div>
      )}
    </div>
  );
}
