'use client';

import { useState, useRef } from 'react';
import { CsvValidationResult } from '@/lib/sarvamTypes';
import { UploadCloud, CheckCircle2, AlertTriangle, FileDown, RefreshCw, Sparkles, Play, Settings } from 'lucide-react';

interface CsvVerificationUploaderProps {
  onValidated: (result: CsvValidationResult, fileName: string) => void;
  onStartCampaignImmediately?: (result: CsvValidationResult, fileName: string) => void;
  onOpenCampaignConfig?: (result: CsvValidationResult, fileName: string) => void;
}

export default function CsvVerificationUploader({ 
  onValidated, 
  onStartCampaignImmediately,
  onOpenCampaignConfig 
}: CsvVerificationUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [result, setResult] = useState<CsvValidationResult | null>(null);
  const [fileName, setFileName] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = async (file: File) => {
    if (!file) return;
    setFileName(file.name);
    setIsVerifying(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/csv-fix', {
        method: 'POST',
        body: formData
      });

      const validation: CsvValidationResult = await res.json();
      setResult(validation);
      onValidated(validation, file.name);
    } catch (err) {
      console.error('Failed to process CSV:', err);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  };

  const handleDownloadFixedCsv = () => {
    if (!result?.cleanedCsvContent) return;
    const blob = new Blob([result.cleanedCsvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `Sai_Garden_Verified_${fileName || 'cohort.csv'}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Upload Calling Sheet (CSV)</span>
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
            Auto Format Verification & Healing
          </span>
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Upload any contact list. Our engine automatically verifies headers, extracts 10-digit Indian phone numbers, repairs inverted fields, and validates the calling sheet.
        </p>
      </div>

      {/* Drag & Drop Area */}
      <div
        onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/20'
            : 'border-slate-200 dark:border-slate-800 hover:border-blue-400 dark:hover:border-blue-600 bg-slate-50/40 dark:bg-slate-850/40'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt"
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) processFile(f);
          }}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
            {isVerifying ? (
              <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
            ) : (
              <UploadCloud className="w-6 h-6" />
            )}
          </div>
          <div>
            <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
              {isVerifying ? 'Verifying & Healing CSV Format...' : fileName ? fileName : 'Click to Browse or Drag & Drop CSV'}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              Supports CSVs, Excel contact exports, and comma-delimited text files
            </p>
          </div>
        </div>
      </div>

      {/* Verification Results Panel */}
      {result && (
        <div className="mt-5 pt-5 border-t border-slate-100 dark:border-slate-800 space-y-4 animate-in fade-in">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {result.isValid ? (
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs font-bold">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>CSV Verified & Ready for Calling</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 text-xs font-bold">
                  <AlertTriangle className="w-4 h-4" />
                  <span>CSV Required Attention</span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {onOpenCampaignConfig && result.isValid && (
                <button
                  onClick={() => onOpenCampaignConfig(result, fileName)}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 shadow-sm transition-all"
                >
                  <Settings className="w-3.5 h-3.5" />
                  <span>Configure & Launch Campaign</span>
                </button>
              )}

              {onStartCampaignImmediately && result.isValid && (
                <button
                  onClick={() => onStartCampaignImmediately(result, fileName)}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-extrabold rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Instant Start</span>
                </button>
              )}

              <button
                onClick={handleDownloadFixedCsv}
                className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all"
              >
                <FileDown className="w-3.5 h-3.5" />
                <span>Download Cleaned CSV</span>
              </button>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
              <span className="text-[11px] text-slate-500 font-medium">Total Contacts</span>
              <p className="text-lg font-extrabold text-slate-900 dark:text-white">{result.totalRows}</p>
            </div>
            <div className="p-3 rounded-2xl bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200/60 dark:border-emerald-800/40">
              <span className="text-[11px] text-emerald-700 dark:text-emerald-400 font-medium">Valid Phone Numbers</span>
              <p className="text-lg font-extrabold text-emerald-700 dark:text-emerald-400">{result.validRows}</p>
            </div>
            <div className="p-3 rounded-2xl bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-800/40">
              <span className="text-[11px] text-blue-700 dark:text-blue-400 font-medium">Auto-Repaired</span>
              <p className="text-lg font-extrabold text-blue-700 dark:text-blue-400">{result.fixedRows}</p>
            </div>
            <div className="p-3 rounded-2xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40">
              <span className="text-[11px] text-amber-700 dark:text-amber-400 font-medium">Skipped (Invalid)</span>
              <p className="text-lg font-extrabold text-amber-700 dark:text-amber-400">{result.invalidRows}</p>
            </div>
          </div>

          {/* Warnings / Healing Notices */}
          {result.warnings.length > 0 && (
            <div className="p-3 rounded-2xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-900/40 text-xs text-blue-800 dark:text-blue-300 space-y-1">
              <div className="flex items-center gap-1.5 font-bold">
                <Sparkles className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                <span>Format Healing & Standardization Applied:</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[11px] text-slate-600 dark:text-slate-400">
                {result.warnings.slice(0, 3).map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
                {result.warnings.length > 3 && (
                  <li>...and {result.warnings.length - 3} other row adjustments</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
