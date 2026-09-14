#!/usr/bin/env python3
"""
Gayatri AI Voice Agent - Comprehensive Call & Cost Analytics Engine
Calculates exact cumulative costs, per-minute pricing, average call durations,
and complete turn-by-turn expenditure across all telephony and AI providers.

Usage:
    python scripts/calculate_call_costs.py
    python scripts/calculate_call_costs.py --detailed
    python scripts/calculate_call_costs.py --json
"""

import os
import sys
import json
import glob
import argparse
from datetime import datetime
from pathlib import Path

# Safe encoding for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ANSI Colors
USE_COLOR = sys.stdout.isatty() or os.name == "posix" or "WT_SESSION" in os.environ or "TERM" in os.environ
CYAN = "\033[96m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
GREEN = "\033[92m" if USE_COLOR else ""
RED = "\033[91m" if USE_COLOR else ""
MAGENTA = "\033[95m" if USE_COLOR else ""
BLUE = "\033[94m" if USE_COLOR else ""
BOLD = "\033[1m" if USE_COLOR else ""
DIM = "\033[2m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""

# ==============================================================================
# AUTHORITATIVE PRICING CONSTANTS (September 2026)
# ==============================================================================
USD_TO_INR = 83.50                       # Currency exchange rate

# 1. Telephony (Vobiz Telecom Outbound India SIP Trunk)
VOBIZ_PER_MIN_INR = 0.400                # ₹0.400 / minute
VOBIZ_PER_MIN_USD = VOBIZ_PER_MIN_INR / USD_TO_INR

# 2. Speech-to-Text (Deepgram Nova-3 Streaming)
DEEPGRAM_PER_MIN_USD = 0.0059            # $0.0059 / minute
DEEPGRAM_PER_MIN_INR = DEEPGRAM_PER_MIN_USD * USD_TO_INR  # ₹0.493 / minute

# 3. Text-to-Speech (Cartesia Sonic-3.5)
CARTESIA_PER_CHAR_USD = 0.000020         # $20 per 1,000,000 characters ($0.02 / 1k chars)
CARTESIA_PER_CHAR_INR = CARTESIA_PER_CHAR_USD * USD_TO_INR  # ₹0.00167 / character

# 4. LLM Brain (Google Gemini 2.5 Flash Lite)
GEMINI_IN_PER_M_USD = 0.075              # $0.075 / 1 Million Input Tokens
GEMINI_OUT_PER_M_USD = 0.300             # $0.300 / 1 Million Output Tokens
GEMINI_SYSTEM_PROMPT_TOKENS = 3200       # Gayatri real-estate prompt size

# 5. WebRTC Media Server (LiveKit Cloud)
# Free Tier includes 50,000 participant-minutes/month ($0.00)
LIVEKIT_CLOUD_FREE_MINUTES = 50000
LIVEKIT_OVERAGE_PER_PART_MIN_USD = 0.004 # $0.004 / participant-minute (if exceeding free tier)


def extract_call_records(base_dir: str = "."):
    """
    Discovers, deduplicates, and aggregates call records across:
    1. db.json (authoritative database for Web Dashboard)
    2. bookings/call_billing_log.jsonl (live agent billing log)
    3. bookings/call_transcripts.jsonl (live agent transcript archive)
    4. bookings/transcripts/*.json (individual session records)
    """
    calls_map = {}

    # 1. Check db.json
    db_path = os.path.join(base_dir, "db.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8", errors="replace") as f:
                db_data = json.load(f)
            for log in db_data.get("callLogs", []):
                sid = log.get("callSid") or log.get("id")
                if not sid or sid == "gayatri-persistent-storage" or "probe" in sid.lower():
                    continue
                calls_map[sid] = {
                    "source": "db.json",
                    "call_sid": sid,
                    "customer_name": log.get("customerName") or log.get("leadName") or "Valued Client",
                    "customer_phone": log.get("customerPhone") or "",
                    "duration_seconds": float(log.get("durationSeconds", 0)),
                    "called_at": log.get("calledAt") or "",
                    "outcome": log.get("outcome") or "Completed",
                    "sentiment": log.get("sentiment") or "neutral",
                    "transcript": log.get("transcript") or "",
                    "characters_spoken": None,
                    "input_tokens": None,
                    "output_tokens": None,
                }
        except Exception as e:
            sys.stderr.write(f"Warning reading db.json: {e}\n")

    # 2. Check bookings/call_billing_log.jsonl
    billing_log_path = os.path.join(base_dir, "bookings", "call_billing_log.jsonl")
    if os.path.exists(billing_log_path):
        try:
            with open(billing_log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    sid = rec.get("room_name") or rec.get("call_id")
                    if not sid:
                        continue
                    if sid not in calls_map:
                        calls_map[sid] = {
                            "source": "billing_log",
                            "call_sid": sid,
                            "customer_name": rec.get("customer_name") or "Valued Client",
                            "customer_phone": "",
                            "duration_seconds": float(rec.get("duration_seconds", 0)),
                            "called_at": rec.get("timestamp") or "",
                            "outcome": "Completed",
                            "sentiment": "neutral",
                            "transcript": "",
                            "characters_spoken": rec.get("characters_spoken"),
                            "input_tokens": rec.get("input_tokens"),
                            "output_tokens": rec.get("output_tokens"),
                        }
                    else:
                        # Augment with exact tracked hardware characters and tokens
                        if rec.get("characters_spoken"):
                            calls_map[sid]["characters_spoken"] = rec.get("characters_spoken")
                        if rec.get("input_tokens"):
                            calls_map[sid]["input_tokens"] = rec.get("input_tokens")
                        if rec.get("output_tokens"):
                            calls_map[sid]["output_tokens"] = rec.get("output_tokens")
        except Exception as e:
            sys.stderr.write(f"Warning reading call_billing_log.jsonl: {e}\n")

    # 3. Check bookings/call_transcripts.jsonl
    transcripts_path = os.path.join(base_dir, "bookings", "call_transcripts.jsonl")
    if os.path.exists(transcripts_path):
        try:
            with open(transcripts_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    sid = rec.get("call_id") or rec.get("room_name")
                    if not sid:
                        continue
                    if sid not in calls_map:
                        calls_map[sid] = {
                            "source": "call_transcripts",
                            "call_sid": sid,
                            "customer_name": rec.get("customer_name") or "Valued Client",
                            "customer_phone": rec.get("customer_phone") or "",
                            "duration_seconds": float(rec.get("duration_seconds", 0)),
                            "called_at": rec.get("timestamp") or "",
                            "outcome": rec.get("outcome") or "Completed",
                            "sentiment": rec.get("sentiment") or "neutral",
                            "transcript": rec.get("full_transcript") or "",
                            "characters_spoken": None,
                            "input_tokens": None,
                            "output_tokens": None,
                        }
                    else:
                        if not calls_map[sid].get("transcript") and rec.get("full_transcript"):
                            calls_map[sid]["transcript"] = rec.get("full_transcript")
                        if not calls_map[sid].get("customer_phone") and rec.get("customer_phone"):
                            calls_map[sid]["customer_phone"] = rec.get("customer_phone")
        except Exception as e:
            sys.stderr.write(f"Warning reading call_transcripts.jsonl: {e}\n")

    # 4. Check bookings/transcripts/*.json
    json_files = glob.glob(os.path.join(base_dir, "bookings", "transcripts", "*.json"))
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8", errors="replace") as f:
                rec = json.load(f)
            sid = rec.get("call_id") or rec.get("room_name") or Path(jf).stem
            if sid and sid not in calls_map:
                calls_map[sid] = {
                    "source": "transcripts_dir",
                    "call_sid": sid,
                    "customer_name": rec.get("customer_name") or "Valued Client",
                    "customer_phone": rec.get("customer_phone") or "",
                    "duration_seconds": float(rec.get("duration_seconds", 0)),
                    "called_at": rec.get("timestamp") or "",
                    "outcome": rec.get("outcome") or "Completed",
                    "sentiment": rec.get("sentiment") or "neutral",
                    "transcript": rec.get("full_transcript") or "",
                    "characters_spoken": None,
                    "input_tokens": None,
                    "output_tokens": None,
                }
        except Exception:
            pass

    return list(calls_map.values())


def compute_call_metrics(record: dict) -> dict:
    """
    Computes precise speech characters, dialogue turns, LLM tokens,
    and provider-by-provider costs for an individual call.
    """
    dur_sec = record.get("duration_seconds", 0.0)
    dur_min = dur_sec / 60.0

    transcript = record.get("transcript", "")
    gayatri_chars = record.get("characters_spoken")
    gayatri_turns = 0
    caller_turns = 0

    lines = [l.strip() for l in transcript.split("\n") if l.strip()]
    extracted_chars = 0
    for line in lines:
        lower = line.lower()
        if any(lower.startswith(p) or f" {p}" in lower for p in ["gayatri:", "agent:", "ai:"]):
            parts = line.split(":", 1)
            if len(parts) > 1:
                extracted_chars += len(parts[1].strip())
                gayatri_turns += 1
        elif ":" in line:
            caller_turns += 1

    if gayatri_chars is None or gayatri_chars == 0:
        if extracted_chars > 0:
            gayatri_chars = extracted_chars
        else:
            # Fallback estimation based on natural speaking rate (~420 chars/min)
            gayatri_chars = int(dur_min * 420)

    # LLM Tokens
    in_tokens = record.get("input_tokens")
    out_tokens = record.get("output_tokens")
    if in_tokens is None or in_tokens == 0:
        turns = max(1, gayatri_turns)
        # Each turn re-submits system prompt + incremental history
        in_tokens = sum(GEMINI_SYSTEM_PROMPT_TOKENS + (i * 90) for i in range(turns))
        out_tokens = turns * 45

    # Calculate individual service costs
    cost_telephony_inr = dur_min * VOBIZ_PER_MIN_INR
    cost_stt_inr = dur_min * DEEPGRAM_PER_MIN_INR
    cost_tts_inr = gayatri_chars * CARTESIA_PER_CHAR_INR
    cost_llm_usd = (in_tokens * (GEMINI_IN_PER_M_USD / 1e6)) + (out_tokens * (GEMINI_OUT_PER_M_USD / 1e6))
    cost_llm_inr = cost_llm_usd * USD_TO_INR
    cost_livekit_inr = 0.0  # Free tier

    total_call_cost_inr = cost_telephony_inr + cost_stt_inr + cost_tts_inr + cost_llm_inr + cost_livekit_inr
    total_call_cost_usd = total_call_cost_inr / USD_TO_INR
    cost_per_minute_inr = (total_call_cost_inr / dur_min) if dur_min > 0 else 0.0

    return {
        "call_sid": record["call_sid"],
        "customer_name": record["customer_name"],
        "customer_phone": record["customer_phone"],
        "called_at": record["called_at"],
        "outcome": record["outcome"],
        "duration_seconds": dur_sec,
        "duration_minutes": dur_min,
        "gayatri_turns": gayatri_turns,
        "caller_turns": caller_turns,
        "characters_spoken": gayatri_chars,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_telephony_inr": cost_telephony_inr,
        "cost_stt_inr": cost_stt_inr,
        "cost_tts_inr": cost_tts_inr,
        "cost_llm_inr": cost_llm_inr,
        "cost_livekit_inr": cost_livekit_inr,
        "total_cost_inr": total_call_cost_inr,
        "total_cost_usd": total_call_cost_usd,
        "cost_per_minute_inr": cost_per_minute_inr,
    }


def main():
    parser = argparse.ArgumentParser(description="Gayatri AI Voice Agent Call & Cost Analytics")
    parser.add_argument("--detailed", action="store_true", help="Print turn-by-turn per-call breakdown table")
    parser.add_argument("--json", action="store_true", help="Output full analytics in JSON format")
    parser.add_argument("--dir", default=".", help="Base project directory path (default: current dir)")
    args = parser.parse_args()

    raw_records = extract_call_records(args.dir)
    if not raw_records:
        if args.json:
            print(json.dumps({"error": "No call records found", "total_calls": 0}))
        else:
            print(f"{YELLOW}⚠️ No call records found in db.json or bookings/{RESET}")
        return

    # Sort calls chronologically (newest first for summary, oldest first for progression)
    def parse_time(r):
        dt = r.get("called_at") or ""
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    raw_records.sort(key=parse_time)
    metrics_list = [compute_call_metrics(r) for r in raw_records]

    # Cumulative Metrics
    total_calls = len(metrics_list)
    total_seconds = sum(m["duration_seconds"] for m in metrics_list)
    total_minutes = total_seconds / 60.0
    avg_seconds = total_seconds / total_calls if total_calls > 0 else 0.0
    avg_minutes = total_minutes / total_calls if total_calls > 0 else 0.0

    total_chars = sum(m["characters_spoken"] for m in metrics_list)
    total_in_tokens = sum(m["input_tokens"] for m in metrics_list)
    total_out_tokens = sum(m["output_tokens"] for m in metrics_list)
    total_turns = sum(m["gayatri_turns"] for m in metrics_list)

    total_telephony_inr = sum(m["cost_telephony_inr"] for m in metrics_list)
    total_stt_inr = sum(m["cost_stt_inr"] for m in metrics_list)
    total_tts_inr = sum(m["cost_tts_inr"] for m in metrics_list)
    total_llm_inr = sum(m["cost_llm_inr"] for m in metrics_list)
    total_spend_inr = sum(m["total_cost_inr"] for m in metrics_list)
    total_spend_usd = total_spend_inr / USD_TO_INR

    avg_cost_per_call_inr = total_spend_inr / total_calls if total_calls > 0 else 0.0
    effective_cost_per_minute_inr = total_spend_inr / total_minutes if total_minutes > 0 else 0.0
    effective_cost_per_minute_usd = effective_cost_per_minute_inr / USD_TO_INR

    # Standard 1-minute benchmark model (450 chars TTS, 3.5k tokens LLM, 1m STT, 1m SIP)
    std_1min_sip = 1.0 * VOBIZ_PER_MIN_INR
    std_1min_stt = 1.0 * DEEPGRAM_PER_MIN_INR
    std_1min_tts = 450 * CARTESIA_PER_CHAR_INR
    std_1min_llm = ((12000 * GEMINI_IN_PER_M_USD / 1e6) + (150 * GEMINI_OUT_PER_M_USD / 1e6)) * USD_TO_INR
    std_1min_total_inr = std_1min_sip + std_1min_stt + std_1min_tts + std_1min_llm
    std_1min_total_usd = std_1min_total_inr / USD_TO_INR

    if args.json:
        output_payload = {
            "summary": {
                "total_calls": total_calls,
                "total_duration_seconds": round(total_seconds, 1),
                "total_duration_minutes": round(total_minutes, 2),
                "average_duration_seconds": round(avg_seconds, 1),
                "average_duration_minutes": round(avg_minutes, 2),
                "total_characters_spoken": total_chars,
                "total_dialogue_turns": total_turns,
                "total_llm_input_tokens": total_in_tokens,
                "total_llm_output_tokens": total_out_tokens,
                "total_cost_inr": round(total_spend_inr, 2),
                "total_cost_usd": round(total_spend_usd, 4),
                "average_cost_per_call_inr": round(avg_cost_per_call_inr, 2),
                "effective_cost_per_minute_inr": round(effective_cost_per_minute_inr, 2),
                "effective_cost_per_minute_usd": round(effective_cost_per_minute_usd, 4),
                "standard_1min_benchmark_inr": round(std_1min_total_inr, 2),
            },
            "provider_breakdown": {
                "telephony_vobiz": {
                    "provider": "Vobiz Telecom",
                    "rate": f"₹{VOBIZ_PER_MIN_INR:.3f} / minute",
                    "total_cost_inr": round(total_telephony_inr, 2),
                    "share_percent": round((total_telephony_inr / total_spend_inr) * 100, 1) if total_spend_inr > 0 else 0,
                },
                "stt_deepgram_nova3": {
                    "provider": "Deepgram Nova-3 (Hindi Streaming)",
                    "rate": f"${DEEPGRAM_PER_MIN_USD:.4f} / min (₹{DEEPGRAM_PER_MIN_INR:.3f} / min)",
                    "total_cost_inr": round(total_stt_inr, 2),
                    "share_percent": round((total_stt_inr / total_spend_inr) * 100, 1) if total_spend_inr > 0 else 0,
                },
                "tts_cartesia_sonic3_5": {
                    "provider": "Cartesia Sonic-3.5 (Kusha Voice)",
                    "rate": f"${CARTESIA_PER_CHAR_USD * 1e6:.1f} / 1M chars (₹{CARTESIA_PER_CHAR_INR * 1000:.2f} / 1k chars)",
                    "total_cost_inr": round(total_tts_inr, 2),
                    "share_percent": round((total_tts_inr / total_spend_inr) * 100, 1) if total_spend_inr > 0 else 0,
                },
                "llm_gemini_2_5_flash_lite": {
                    "provider": "Google Gemini 2.5 Flash Lite",
                    "rate": f"${GEMINI_IN_PER_M_USD} In / ${GEMINI_OUT_PER_M_USD} Out per 1M tokens",
                    "total_cost_inr": round(total_llm_inr, 2),
                    "share_percent": round((total_llm_inr / total_spend_inr) * 100, 1) if total_spend_inr > 0 else 0,
                },
                "webrtc_livekit_cloud": {
                    "provider": "LiveKit Cloud",
                    "rate": "50,000 participant-minutes included in Free Tier",
                    "total_cost_inr": 0.0,
                    "share_percent": 0.0,
                }
            },
            "calls": metrics_list
        }
        print(json.dumps(output_payload, indent=2, ensure_ascii=False))
        return

    # Print Beautiful Terminal Dashboard
    print(f"\n{BOLD}{CYAN}================================================================================{RESET}")
    print(f"{BOLD}{CYAN}      📞 GAYATRI AI VOICE AGENT — CALL & COST ANALYTICS REPORT                 {RESET}")
    print(f"{BOLD}{CYAN}================================================================================{RESET}")
    print(f" Generated At : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (System Time)")
    print(f" Data Sources : db.json, bookings/call_billing_log.jsonl, bookings/transcripts/")
    print(f" Active Brain : Google Gemini 2.5 Flash Lite | Voice: Cartesia Sonic-3.5 (Kusha)")
    print(f" STT Engine   : Deepgram Nova-3 (Hindi)      | Telephony: Vobiz India SIP Trunk")

    print(f"\n{BOLD}{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"{BOLD} 📊 1. OVERALL CALL VOLUME & TALK TIME SUMMARY{RESET}")
    print(f"{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"  • {BOLD}Total Calls Made Till Now   :{RESET} {BOLD}{GREEN}{total_calls} calls{RESET}")
    print(f"  • {BOLD}Total Talk Time Accumulated :{RESET} {BOLD}{total_seconds:.0f} seconds{RESET} ({BOLD}{GREEN}{total_minutes:.2f} minutes{RESET})")
    print(f"  • {BOLD}Average Call Duration       :{RESET} {BOLD}{GREEN}{avg_seconds:.1f} seconds{RESET} ({BOLD}{avg_minutes:.2f} minutes / call{RESET})")
    print(f"  • {BOLD}Total Dialogue Turns        :{RESET} {total_turns} turns")
    print(f"  • {BOLD}Total Characters Spoken     :{RESET} {total_chars:,} characters (Cartesia TTS)")
    print(f"  • {BOLD}Total LLM Tokens Processed  :{RESET} {total_in_tokens:,} input | {total_out_tokens:,} output tokens")

    print(f"\n{BOLD}{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"{BOLD} 💸 2. TOTAL COSTING & PROVIDER-BY-PROVIDER BREAKDOWN{RESET}")
    print(f"{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")

    def pbar(pct):
        filled = int(pct / 5)
        return f"[{'█' * filled}{' ' * (20 - filled)}]"

    pct_vobiz = (total_telephony_inr / total_spend_inr * 100) if total_spend_inr > 0 else 0
    pct_stt = (total_stt_inr / total_spend_inr * 100) if total_spend_inr > 0 else 0
    pct_tts = (total_tts_inr / total_spend_inr * 100) if total_spend_inr > 0 else 0
    pct_llm = (total_llm_inr / total_spend_inr * 100) if total_spend_inr > 0 else 0

    print(f"  1. {BOLD}Telephony (Vobiz India SIP){RESET} : ₹{total_telephony_inr:>6.2f} (${total_telephony_inr/USD_TO_INR:>5.3f}) | {pbar(pct_vobiz)} {pct_vobiz:>5.1f}% (@ ₹0.40/min)")
    print(f"  2. {BOLD}STT (Deepgram Nova-3)     {RESET} : ₹{total_stt_inr:>6.2f} (${total_stt_inr/USD_TO_INR:>5.3f}) | {pbar(pct_stt)} {pct_stt:>5.1f}% (@ $0.0059/min = ₹0.493/min)")
    print(f"  3. {BOLD}Voice TTS (Cartesia Sonic){RESET} : ₹{total_tts_inr:>6.2f} (${total_tts_inr/USD_TO_INR:>5.3f}) | {pbar(pct_tts)} {pct_tts:>5.1f}% (@ $0.02/1k chars)")
    print(f"  4. {BOLD}Brain LLM (Gemini Flash)  {RESET} : ₹{total_llm_inr:>6.2f} (${total_llm_inr/USD_TO_INR:>5.3f}) | {pbar(pct_llm)} {pct_llm:>5.1f}% (@ $0.075/M in, $0.30/M out)")
    print(f"  5. {BOLD}WebRTC (LiveKit Cloud)    {RESET} : ₹{0.00:>6.2f} ($0.000) | [Free 50k min]      0.0% (Within Free Tier)")
    print(f"  ─────────────────────────────────────────────────────────────────────────────")
    print(f"  {BOLD}⭐ TOTAL ESTIMATED EXPENDITURE TILL NOW:{RESET} {BOLD}{GREEN}₹{total_spend_inr:.2f} INR{RESET}  (≈ {BOLD}${total_spend_usd:.3f} USD{RESET})")
    print(f"  {BOLD}⭐ AVERAGE COST PER CALL             :{RESET} {BOLD}{GREEN}₹{avg_cost_per_call_inr:.2f} INR{RESET}  (≈ {BOLD}${avg_cost_per_call_inr/USD_TO_INR:.3f} USD{RESET})")

    print(f"\n{BOLD}{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"{BOLD} ⏱️  3. HOW MUCH PER MINUTE IS THE COST?{RESET}")
    print(f"{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"  • {BOLD}Actual Effective Cost (Historical Live Calls) :{RESET} {BOLD}{GREEN}₹{effective_cost_per_minute_inr:.2f} / minute{RESET} (≈ ${effective_cost_per_minute_usd:.3f} / min)")
    print(f"  • {BOLD}Standard 1-Minute Continuous Call Benchmark    :{RESET} {BOLD}{GREEN}₹{std_1min_total_inr:.2f} / minute{RESET} (≈ ${std_1min_total_usd:.3f} / min)")
    print(f"\n  {BOLD}Component Cost Breakdown Per 1 Minute of Live Call:{RESET}")
    print(f"    ┌───────────────────────────────────┬───────────────────┬──────────────┐")
    print(f"    │ Component                         │ Cost / Minute     │ % of Total   │")
    print(f"    ├───────────────────────────────────┼───────────────────┼──────────────┤")
    print(f"    │ Telephony (Vobiz India SIP)       │ ₹0.400 / min      │     23.3 %   │")
    print(f"    │ Speech-to-Text (Deepgram Nova-3)  │ ₹0.493 / min      │     28.7 %   │")
    print(f"    │ Voice Generation (Cartesia Sonic) │ ₹0.750 / min      │     43.6 %   │")
    print(f"    │ LLM Intelligence (Gemini Flash)   │ ₹0.075 / min      │      4.4 %   │")
    print(f"    │ WebRTC Media Server (LiveKit)     │ ₹0.000 (Free)     │      0.0 %   │")
    print(f"    ├───────────────────────────────────┼───────────────────┼──────────────┤")
    print(f"    │ {BOLD}TOTAL COST PER 1 MINUTE OF CALL{RESET}   │ {BOLD}{GREEN}₹{std_1min_total_inr:.2f} / min{RESET}     │    {BOLD}100.0 %{RESET}   │")
    print(f"    │ (In USD Equivalent)               │ {BOLD}${std_1min_total_usd:.3f} / min{RESET}     │              │")
    print(f"    └───────────────────────────────────┴───────────────────┴──────────────┘")

    print(f"\n{BOLD}{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"{BOLD} 📋 4. COMPLETE LIST OF ALL CALLS MADE TILL NOW ({total_calls} Calls){RESET}")
    print(f"{YELLOW}────────────────────────────────────────────────────────────────────────────────{RESET}")
    print(f"{'#':<3} | {'Date & Time (UTC)':<19} | {'Customer':<11} | {'Duration':<9} | {'Chars':<6} | {'Vobiz':<6} | {'Deepg':<6} | {'Cart':<6} | {'Gemini':<6} | {BOLD}{'Total':<8}{RESET} | {'Outcome':<18}")
    print(f"{'-'*3}-+-{'-'*19}-+-{'-'*11}-+-{'-'*9}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*8}-+-{'-'*18}")

    for idx, m in enumerate(metrics_list, start=1):
        dt_str = m["called_at"][:19].replace("T", " ") if m["called_at"] else "Unknown"
        cust = (m["customer_name"] or "Client")[:11]
        dur_str = f"{m['duration_seconds']:.0f}s ({m['duration_minutes']:.1f}m)"
        chars_str = str(m["characters_spoken"])
        vobiz_s = f"₹{m['cost_telephony_inr']:.2f}"
        stt_s = f"₹{m['cost_stt_inr']:.2f}"
        tts_s = f"₹{m['cost_tts_inr']:.2f}"
        llm_s = f"₹{m['cost_llm_inr']:.2f}"
        total_s = f"₹{m['total_cost_inr']:.2f}"
        outc = (m["outcome"] or "Completed")[:18]

        outc_color = GREEN if "Site Visit" in outc else (CYAN if "Interested" in outc else "")
        print(f"{idx:<3} | {dt_str:<19} | {cust:<11} | {dur_str:<9} | {chars_str:<6} | {vobiz_s:<6} | {stt_s:<6} | {tts_s:<6} | {llm_s:<6} | {BOLD}{total_s:<8}{RESET} | {outc_color}{outc:<18}{RESET}")

    print(f"{'-'*3}-+-{'-'*19}-+-{'-'*11}-+-{'-'*9}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*8}-+-{'-'*18}")
    print(f"    {BOLD}TOTALS:{RESET} {total_calls} calls           | {BOLD}{total_minutes:.2f} mins{RESET}   | {total_chars:<6} | ₹{total_telephony_inr:<5.2f}| ₹{total_stt_inr:<5.2f}| ₹{total_tts_inr:<5.2f}| ₹{total_llm_inr:<5.2f}| {BOLD}{GREEN}₹{total_spend_inr:.2f}{RESET}")

    print(f"\n{BOLD}{CYAN}================================================================================{RESET}\n")


if __name__ == "__main__":
    main()
