'use client';

import { useEffect } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Application Error Boundary caught error:', error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 text-center space-y-4 shadow-2xl">
        <div className="h-14 w-14 rounded-2xl bg-rose-500/10 text-rose-400 mx-auto flex items-center justify-center">
          <AlertCircle className="h-7 w-7" />
        </div>
        <h2 className="text-lg font-black text-white">Something went wrong</h2>
        <p className="text-xs text-slate-400 leading-relaxed">
          The dashboard encountered an unexpected error. You can refresh or try loading again.
        </p>
        {error?.message && (
          <div className="text-[11px] text-rose-400/80 bg-rose-950/40 p-3 rounded-xl border border-rose-900/50 font-mono text-left break-all max-h-32 overflow-y-auto">
            {error.message}
          </div>
        )}
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => reset()}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs rounded-xl shadow-lg flex items-center space-x-2 transition-all cursor-pointer"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Try Again</span>
          </button>
          <button
            onClick={() => window.location.reload()}
            className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs rounded-xl transition-all cursor-pointer"
          >
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
}
