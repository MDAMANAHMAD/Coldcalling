import { CallLog } from './types';

/**
 * Normalizes date strings and extracts accurate UTC epoch milliseconds from
 * either the 13-digit timestamp embedded in callSid (e.g. call-raj-1790412459500)
 * or the calledAt ISO string (ensuring UTC 'Z' is honored).
 */
export function getCallTimestampMs(call: Partial<CallLog> & { id?: string }): number {
  if (call.callSid) {
    const match = call.callSid.match(/(\d{13})/);
    if (match) {
      const ms = Number(match[1]);
      if (!isNaN(ms) && ms > 1600000000000) return ms;
    }
  }

  if (call.calledAt) {
    let str = String(call.calledAt).trim();
    // If string looks like ISO without timezone offset or Z, append Z so JS treats as UTC
    if (!str.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(str)) {
      str += 'Z';
    }
    const t = new Date(str).getTime();
    if (!isNaN(t)) return t;
  }

  if (call.id) {
    const match = call.id.match(/(\d{13})/);
    if (match) {
      const ms = Number(match[1]);
      if (!isNaN(ms) && ms > 1600000000000) return ms;
    }
  }

  return 0;
}

export type PickedStatus = 'picked' | 'not_picked' | 'ringing';

export interface PickedBadgeInfo {
  status: PickedStatus;
  isPicked: boolean;
  label: string;
  bg: string;
  dot: string;
  border: string;
  textColor: string;
}

/**
 * Accurately determines whether an outbound or inbound call was picked up / answered.
 */
export function getCallPickedInfo(call: Partial<CallLog>): PickedBadgeInfo {
  const duration = Number(call.durationSeconds || 0);
  const outcome = (call.outcome || '').toLowerCase();
  const summary = (call.aiSummary || '').toLowerCase();
  const transcript = (call.transcript || '').toLowerCase();

  const timestampMs = getCallTimestampMs(call);
  const ageSeconds = timestampMs > 0 ? (Date.now() - timestampMs) / 1000 : 999;

  // Active ringing state: newly placed call under 90s still in progress
  const isActivelyRinging = 
    ageSeconds < 90 && 
    duration === 0 && 
    (outcome.includes('calling') || outcome.includes('ringing') || summary.includes('phone ringing'));

  if (isActivelyRinging) {
    return {
      status: 'ringing',
      isPicked: false,
      label: 'Ringing...',
      bg: 'bg-amber-50 dark:bg-amber-950/40',
      dot: 'bg-amber-500 animate-pulse',
      border: 'border-amber-200 dark:border-amber-800',
      textColor: 'text-amber-700 dark:text-amber-300'
    };
  }

  // Answered / Picked Up: Has actual duration > 0 OR multiple dialogue turns
  const hasSpokenDialogue = 
    transcript.includes('gayatri:') && 
    (transcript.includes('raj:') || transcript.includes('suraj:') || transcript.includes('customer:') || transcript.includes('akshay:') || transcript.includes('client:'));

  if (duration > 0 || hasSpokenDialogue) {
    return {
      status: 'picked',
      isPicked: true,
      label: 'Picked Up',
      bg: 'bg-emerald-50 dark:bg-emerald-950/40',
      dot: 'bg-emerald-500',
      border: 'border-emerald-200 dark:border-emerald-800',
      textColor: 'text-emerald-700 dark:text-emerald-300'
    };
  }

  // Unanswered / Not Picked Up / Missed
  return {
    status: 'not_picked',
    isPicked: false,
    label: 'Not Picked Up',
    bg: 'bg-rose-50 dark:bg-rose-950/40',
    dot: 'bg-rose-500',
    border: 'border-rose-200 dark:border-rose-800',
    textColor: 'text-rose-700 dark:text-rose-300'
  };
}

/**
 * Returns clean human-readable duration
 */
export function formatCallDuration(call: Partial<CallLog>): string {
  const duration = Number(call.durationSeconds || 0);
  const pickedInfo = getCallPickedInfo(call);

  if (pickedInfo.status === 'ringing') {
    return 'Ringing...';
  }

  if (duration > 0) {
    const mins = Math.floor(duration / 60);
    const secs = duration % 60;
    return `${mins}m ${secs}s`;
  }

  return '0s (Not Answered)';
}
