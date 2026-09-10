#!/usr/bin/env python3
"""
Transcript and Question Analytics Inspector for Gayatri AI Real Estate Voice Agent
Usage:
    python scripts/view_transcripts.py                 # List recent calls & summary
    python scripts/view_transcripts.py --call 1        # View full turn-by-turn dialogue of call #1
    python scripts/view_transcripts.py --call <room>   # View full dialogue by room or call ID
    python scripts/view_transcripts.py --questions     # Question frequency & repeated objection analytics across 400+ calls
    python scripts/view_transcripts.py --outcome kalyan # Filter by outcome
    python scripts/view_transcripts.py --search budget # Search dialogue for keyword
"""

import os
import sys
import json
import glob
import argparse
from datetime import datetime
from collections import Counter

# Safe encoding for Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ANSI Colors (disabled if non-tty or not supported)
USE_COLOR = sys.stdout.isatty() or os.name == 'posix' or 'WT_SESSION' in os.environ or 'TERM' in os.environ
CYAN = '\033[96m' if USE_COLOR else ''
YELLOW = '\033[93m' if USE_COLOR else ''
GREEN = '\033[92m' if USE_COLOR else ''
RED = '\033[91m' if USE_COLOR else ''
MAGENTA = '\033[95m' if USE_COLOR else ''
BOLD = '\033[1m' if USE_COLOR else ''
DIM = '\033[2m' if USE_COLOR else ''
RESET = '\033[0m' if USE_COLOR else ''

def load_all_records():
    records = []
    seen_ids = set()

    # 1. Check bookings/call_transcripts.jsonl
    jsonl_path = os.path.join('bookings', 'call_transcripts.jsonl')
    if os.path.exists(jsonl_path):
        with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cid = data.get('room_name') or data.get('id')
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        records.append(data)
                except Exception:
                    pass

    # 2. Check bookings/transcripts/*.json
    transcripts_dir = os.path.join('bookings', 'transcripts')
    if os.path.exists(transcripts_dir):
        for fpath in glob.glob(os.path.join(transcripts_dir, '*.json')):
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    data = json.load(f)
                    cid = data.get('room_name') or data.get('id')
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        records.append(data)
            except Exception:
                pass

    # 3. Fallback to db.json callLogs
    if os.path.exists('db.json'):
        try:
            with open('db.json', 'r', encoding='utf-8', errors='replace') as f:
                db_data = json.load(f)
                for log in db_data.get('callLogs', []):
                    cid = log.get('callSid') or log.get('id')
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        # Format into compatible record
                        turns = []
                        raw_transcript = log.get('transcript', '')
                        for line in raw_transcript.split('\n'):
                            line = line.strip()
                            if not line:
                                continue
                            if ':' in line:
                                spk, text = line.split(':', 1)
                                turns.append({'speaker': spk.strip(), 'text': text.strip()})
                            else:
                                turns.append({'speaker': 'Unknown', 'text': line})
                        records.append({
                            'room_name': cid,
                            'customer_name': log.get('customerName') or log.get('leadId', 'Unknown'),
                            'customer_phone': log.get('customerPhone', ''),
                            'call_duration_seconds': log.get('durationSeconds', 0),
                            'started_at': log.get('calledAt', ''),
                            'call_outcome': log.get('outcome') or log.get('sentiment', 'Unknown'),
                            'detected_questions': log.get('detectedQuestions', []),
                            'total_turns': len(turns),
                            'turns': turns,
                            'ai_summary': log.get('aiSummary', '')
                        })
        except Exception:
            pass

    # Sort descending by timestamp
    records.sort(key=lambda r: str(r.get('started_at') or ''), reverse=True)
    return records

def print_summary_table(records, filter_outcome=None, search_query=None):
    if not records:
        print(f'{YELLOW}No call transcripts found in bookings/call_transcripts.jsonl or db.json.{RESET}')
        print(f'{DIM}Transcripts are automatically logged whenever a live outbound call terminates.{RESET}')
        return

    filtered = []
    for r in records:
        if filter_outcome:
            out = (r.get('call_outcome') or '').lower()
            if filter_outcome.lower() not in out:
                continue
        if search_query:
            query_lower = search_query.lower()
            all_text = ' '.join([t.get('text', '') for t in r.get('turns', [])]).lower()
            all_text += ' ' + str(r.get('customer_name') or '').lower()
            all_text += ' ' + str(r.get('call_outcome') or '').lower()
            if query_lower not in all_text:
                continue
        filtered.append(r)

    if not filtered:
        print(f'{YELLOW}No calls matched your filter.{RESET}')
        return

    print(f'\n{BOLD}===================================================================================================={RESET}')
    print(f'{BOLD}   CALL LOGS & TRANSCRIPTS ({len(filtered)} calls){RESET}')
    print(f'{BOLD}===================================================================================================={RESET}')
    print(f'{BOLD}{"#":<4} {"Time (UTC)":<17} {"Caller":<15} {"Duration":<10} {"Outcome":<24} {"Detected Questions / Inquiries"}{RESET}')
    print(f'{DIM}----------------------------------------------------------------------------------------------------{RESET}')

    for i, r in enumerate(filtered, 1):
        ts = str(r.get('started_at', ''))[:16].replace('T', ' ')
        caller = str(r.get('customer_name') or 'Unknown')[:14]
        dur = f"{r.get('call_duration_seconds', 0)}s"
        outcome = str(r.get('call_outcome') or 'Undecided')
        
        # Color code outcome
        if 'Visit' in outcome:
            colored_outcome = f'{GREEN}{outcome[:23]:<24}{RESET}'
        elif 'Kalyan' in outcome or 'Mismatch' in outcome:
            colored_outcome = f'{MAGENTA}{outcome[:23]:<24}{RESET}'
        elif 'Not Interested' in outcome:
            colored_outcome = f'{RED}{outcome[:23]:<24}{RESET}'
        else:
            colored_outcome = f'{CYAN}{outcome[:23]:<24}{RESET}'

        questions = r.get('detected_questions', [])
        q_str = ', '.join(questions) if questions else f'{DIM}General Conversation{RESET}'
        if len(q_str) > 40:
            q_str = q_str[:37] + '...'

        print(f'{i:<4} {ts:<17} {caller:<15} {dur:<10} {colored_outcome} {q_str}')

    print(f'{DIM}----------------------------------------------------------------------------------------------------{RESET}')
    print(f'{DIM}View turn-by-turn dialogue: python scripts/view_transcripts.py --call <# or RoomName>{RESET}')
    print(f'{DIM}Analyze questions (for 400+ calls): python scripts/view_transcripts.py --questions{RESET}\n')

def print_call_details(records, target):
    record = None
    # Check if target is integer index
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(records):
            record = records[idx - 1]
    
    if not record:
        for r in records:
            if target.lower() in str(r.get('room_name') or '').lower() or target.lower() in str(r.get('customer_name') or '').lower():
                record = r
                break

    if not record:
        print(f'{RED}Call not found: {target}{RESET}')
        return

    print(f'\n{BOLD}===================================================================================================={RESET}')
    print(f'{BOLD}   CALL DETAILS: {record.get("room_name")}{RESET}')
    print(f'{BOLD}===================================================================================================={RESET}')
    print(f'{BOLD}Caller:{RESET} {record.get("customer_name")} ({record.get("customer_phone") or "N/A"})')
    print(f'{BOLD}Started At:{RESET} {record.get("started_at")} | {BOLD}Duration:{RESET} {record.get("call_duration_seconds")}s')
    print(f'{BOLD}Outcome:{RESET} {record.get("call_outcome")}')
    print(f'{BOLD}Questions / Topics Inquired:{RESET} {record.get("detected_questions") or ["General"]}')
    if record.get('ai_summary'):
        print(f'{BOLD}AI Summary:{RESET} {record.get("ai_summary")}')
    print(f'{DIM}----------------------------------------------------------------------------------------------------{RESET}')
    print(f'{BOLD}TURN-BY-TURN DIALOGUE TRANSCRIPT ({len(record.get("turns", []))} turns):{RESET}\n')

    for turn in record.get('turns', []):
        spk = turn.get('speaker', '')
        text = turn.get('text', '')
        ts = turn.get('timestamp')
        ts_str = f'{DIM}[{ts:.1f}s]{RESET} ' if ts is not None else ''

        if 'Gayatri' in spk or 'Agent' in spk:
            print(f'{ts_str}{CYAN}{BOLD}[Gayatri]:{RESET} {text}')
        elif 'Customer' in spk or 'User' in spk or 'Caller' in spk:
            print(f'{ts_str}{YELLOW}{BOLD}[Customer]:{RESET} {text}')
        else:
            print(f'{ts_str}{GREEN}{BOLD}[{spk}]:{RESET} {text}')

    print(f'\n{BOLD}===================================================================================================={RESET}\n')

def print_question_analytics(records):
    total_calls = len(records)
    if total_calls == 0:
        print(f'{YELLOW}No call records to analyze.{RESET}')
        return

    q_counter = Counter()
    outcome_counter = Counter()
    total_duration = 0

    for r in records:
        total_duration += r.get('call_duration_seconds', 0)
        outcome = r.get('call_outcome') or 'Undecided / Other'
        outcome_counter[outcome] += 1

        for q in r.get('detected_questions', []):
            q_counter[q] += 1

    avg_dur = round(total_duration / total_calls, 1) if total_calls else 0

    print(f'\n{BOLD}+==============================================================================================+{RESET}')
    print(f'{BOLD}|   AI REAL ESTATE INTELLIGENCE: CALL & QUESTION ANALYTICS REPORT                              |{RESET}')
    print(f'{BOLD}+==============================================================================================+{RESET}')
    print(f'Total Calls Analyzed: {BOLD}{total_calls}{RESET} | Avg Call Duration: {BOLD}{avg_dur}s\n')

    print(f'{BOLD}[*] CALL OUTCOMES BREAKDOWN:{RESET}')
    print(f'{DIM}--------------------------------------------------------------------------{RESET}')
    for out, cnt in outcome_counter.most_common():
        pct = (cnt / total_calls) * 100
        bar = '=' * int(pct / 4)
        print(f'  {out:<30} {cnt:>3} calls ({pct:5.1f}%) {CYAN}{bar}{RESET}')

    print(f'\n{BOLD}[?] MOST FREQUENT QUESTIONS & OBJECTIONS ASKED BY CALLERS:{RESET}')
    print(f'{DIM}(Use these insights to tune and refine Gayatri\'s dialogue prompts){RESET}')
    print(f'{DIM}--------------------------------------------------------------------------{RESET}')
    if not q_counter:
        print(f'  {DIM}No specific repeated question topics tagged yet.{RESET}')
    else:
        for q, cnt in q_counter.most_common():
            pct = (cnt / total_calls) * 100
            bar = '=' * int(pct / 4)
            print(f'  {q:<30} {cnt:>3} calls ({pct:5.1f}%) {YELLOW}{bar}{RESET}')

    print(f'\n{BOLD}[!] SCRIPT REFINEMENT RECOMMENDATIONS:{RESET}')
    print(f'{DIM}--------------------------------------------------------------------------{RESET}')
    if q_counter.get('Kalyan Location Inquiry', 0) > 0:
        k_pct = (q_counter['Kalyan Location Inquiry'] / total_calls) * 100
        print(f'  - {BOLD}Kalyan Demand ({k_pct:.1f}%){RESET}: Callers frequently ask for Kalyan.')
        print(f'    Ensure Gayatri clarifies 15-min proximity to Dombivli East without sounding dismissive.')
    if q_counter.get('Pricing & Budget Inquiry', 0) > 0:
        p_pct = (q_counter['Pricing & Budget Inquiry'] / total_calls) * 100
        print(f'  - {BOLD}Pricing Inquiries ({p_pct:.1f}%){RESET}: Callers ask for total package / all-inclusive pricing.')
        print(f'    Ensure Gayatri quotes 36 Lakh starting and offers site visit for payment breakdown.')
    if q_counter.get('Station / Metro Connectivity', 0) > 0:
        print(f'  - {BOLD}Connectivity Focus{RESET}: Callers care about station distance.')
        print(f'    Emphasize 7 mins from Dombivli station and fast frequency.')
    print(f'\n{BOLD}========================================================================{RESET}\n')

def main():
    parser = argparse.ArgumentParser(description='View Gayatri Call Transcripts & Question Analytics')
    parser.add_argument('--call', '-c', help='View specific call by index (1, 2, ...) or room name')
    parser.add_argument('--questions', '-q', '--analytics', action='store_true', help='Show question frequency analytics across all calls')
    parser.add_argument('--outcome', '-o', help='Filter calls by outcome (e.g. kalyan, visit, price)')
    parser.add_argument('--search', '-s', help='Search transcripts for specific text')
    
    args = parser.parse_args()
    records = load_all_records()

    if args.questions:
        print_question_analytics(records)
    elif args.call:
        print_call_details(records, args.call)
    else:
        print_summary_table(records, filter_outcome=args.outcome, search_query=args.search)

if __name__ == '__main__':
    main()
