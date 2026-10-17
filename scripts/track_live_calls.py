#!/usr/bin/env python3
"""
Real-Time Call & Latency Tracker for Gayatri AI Voice Agent
Usage on VPS:
    python3 scripts/track_live_calls.py
    
    Or pipe journalctl directly:
    journalctl -u voice-agent -f | python3 scripts/track_live_calls.py
"""

import sys
import os
import re
import subprocess
import shutil
import time

# Safe encoding for terminal output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Terminal Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
MAGENTA = '\033[95m'
BLUE = '\033[94m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

# Ignored noisy logs
IGNORED_PATTERNS = [
    "Failed to detect devices under",
    "plugin registered",
    "preloading plugins",
    "HTTP server listening",
    "Process priority successfully set",
    "[DIAGNOSTICS] Google GenAI Models",
    "[DIAGNOSTICS] RAM Status",
    "[DIAGNOSTICS] CPU Load",
    "Failed to list Groq models",
    "DeprecationWarning",
    "draining worker",
    "shutting down worker",
    "process exited with non-zero exit code 255"
]

def get_time_tag() -> str:
    return time.strftime("%H:%M:%S")

def format_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""

    # Skip raw JSON structured log duplicates from systemd
    if line.startswith("{") and '"message":' in line:
        return ""

    # Skip duplicates or noisy system warnings
    for pattern in IGNORED_PATTERNS:
        if pattern in line:
            return ""

    t_now = get_time_tag()

    # 1. New Call Inbound / Job Received
    if "Job received for Room:" in line:
        room_match = re.search(r"Job received for Room:\s*([^\s]+)", line)
        room_name = room_match.group(1) if room_match else "Unknown"
        return f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}\n" \
               f" {BOLD}{GREEN}📞 [{t_now}] [INCOMING CALL]{RESET} Room: {YELLOW}{room_name}{RESET} | Connecting..."

    # 2. Caller Joined & Customer Identity
    if "Caller joined:" in line:
        caller = line.split("Caller joined:")[-1].strip()
        return f" {CYAN}👤 [{t_now}] Caller Connected:{RESET} {BOLD}{caller}{RESET}"

    if "Resolved customer name dynamically" in line:
        name = line.split("participants:")[-1].strip()
        return f" {CYAN}🏷️  [{t_now}] Customer Name:{RESET} {BOLD}{GREEN}{name}{RESET}"

    if "Kusha Cloned Voice" in line and ("Initializing Cartesia TTS" in line or "STATE RESET" in line):
        return f" {MAGENTA}🎙️ Voice Engine:{RESET} {BOLD}Cartesia Kusha Cloned Voice (ID: 68da925c-0163-4b50-a4e6-08862f6dd5de){RESET}"

    # 3. Agent Session Ready
    if "Speaking Greeting to caller" in line:
        return f" {MAGENTA}👋 [{t_now}] Gayatri is greeting caller...{RESET}"

    # 4. Fast Turn-Taking / User Stopped Speaking (VAD)
    if "[VAD] User stopped speaking!" in line:
        return f" {DIM}⏱️  [{t_now}] [VAD] Caller stopped speaking -> Waiting for final transcript...{RESET}"

    # 5. User Speech Transcripts (STT) - Interim / Partial Streaming
    if "[STT TRANSCRIPT] Final=False" in line:
        text_match = re.search(r"Text:\s*['\"](.*?)['\"]", line)
        if text_match:
            speech_text = text_match.group(1).strip()
            if speech_text:
                return f"   {DIM}{CYAN}🎙️  [{t_now}] [Transcribing live...] \"{speech_text}\"{RESET}"
        return ""

    # 6. User Speech Transcripts (STT) - Final Confirmed Text
    if "[STT TRANSCRIPT] Final=True" in line:
        text_match = re.search(r"Text:\s*['\"](.*?)['\"]", line)
        time_match = re.search(r"\(\+(\d+\.?\d*ms)\)", line)
        speech_text = text_match.group(1) if text_match else line
        timing = f" {DIM}(STT latency: {time_match.group(1)}){RESET}" if time_match else ""
        divider = f"{YELLOW}────────────────────────────────────────────────────────────{RESET}"
        return f"\n{divider}\n" \
               f" {BOLD}{YELLOW}👤 [{t_now}] CALLER (Final STT):{RESET} {BOLD}\"{speech_text}\"{RESET}{timing}"

    # 7. Language Detection & STT Switching
    if "Early Language Detection:" in line or "Language Switch Detected:" in line:
        lang_match = re.search(r"['\"]([a-z]{2})['\"]", line)
        lang_code = lang_match.group(1).upper() if lang_match else "?"
        lang_name = "Hindi" if lang_code == "HI" else ("Marathi" if lang_code == "MR" else "English" if lang_code == "EN" else lang_code)
        return f"   {CYAN}🌐 [{t_now}] Language Detected: {BOLD}{lang_name} ({lang_code}){RESET}"

    if "Switched STT language to" in line:
        stt_lang = line.split("to")[-1].strip().replace("'", "").replace('"', '')
        return f"   {DIM}🔄 [{t_now}] STT model synced to language '{stt_lang}'{RESET}"

    # 8. Decision Engine - Input Normalization
    if "[DECISION ENGINE] Evaluating Caller Input:" in line:
        norm_match = re.search(r"Normalized:\s*['\"](.*?)['\"]", line)
        norm_words = norm_match.group(1) if norm_match else ""
        return f"   {DIM}🔍 [{t_now}] Evaluated Keywords: \"{norm_words}\"{RESET}"

    # 9. Decision: Predefined Keyword / Fast-Path Matched
    if any(k in line for k in ["⚡ [FAST-PATH", "⚡ [TURN 1 DECLINE", "⚡ [TURN 1 BOTH", "⚡ [TURN 1 1BHK", "⚡ [TURN 1 2BHK", "⚡ [TURN 1 FALLBACK", "⚡ [SITE VISIT", "⚡ [AFFIRMATIVE PROMPT"]):
        bracket_match = re.search(r"⚡\s*\[(.*?)\]", line)
        rule_name = bracket_match.group(1) if bracket_match else "FAST-PATH"
        text_match = re.search(r"for\s*['\"](.*?)['\"]", line)
        query_str = f" for \"{text_match.group(1)}\"" if text_match else ""
        return f"   {BOLD}{GREEN}⚡ [{t_now}] DECISION: [PREDEFINED KEYWORD MATCHED]{RESET}\n" \
               f"      {GREEN}↳ Rule: {BOLD}{rule_name}{RESET}{GREEN}{query_str} (0ms LLM wait - Instant Fast-Path){RESET}"

    # 10. Decision: Dispatched to Gemini Brain
    if "🧠 [ROUTING TO BRAIN / GEMINI]" in line:
        text_match = re.search(r"(?:for text:|detected:)\s*['\"](.*?)['\"]", line)
        query_str = f" Query: \"{text_match.group(1)}\"" if text_match else ""
        return f"   {BOLD}{MAGENTA}🧠 [{t_now}] DECISION: [GIVEN TO GEMINI BRAIN]{RESET}\n" \
               f"      {MAGENTA}↳ Reason: No predefined keyword matched -> Dispatched to Gemini LLM{RESET}\n" \
               f"      {MAGENTA}↳{query_str} (Waiting for Gemini reasoning...){RESET}"

    # 11. Unclear / Noise Filter warnings
    if "[UNCLEAR SPEECH DETECTED]" in line or "[TURN 1 NOISE FILTER]" in line:
        return f"   {YELLOW}⚠️  [{t_now}] [VOICE RECOGNITION NOTE] Audio frame was short or unclear -> Asking caller to repeat{RESET}"

    # 12. Brain (Gemini) Response Metrics
    if "[LATENCY TRACE] LLM Metrics:" in line:
        ttft_match = re.search(r"TTFT=(\d+\.?\d*)s", line)
        tokens_match = re.search(r"Prompt=(\d+)\s*\|\s*Completion=(\d+)", line)
        ttft_str = f"{float(ttft_match.group(1))*1000:.0f}ms" if ttft_match else "N/A"
        tokens_str = f"Prompt={tokens_match.group(1)}, Out={tokens_match.group(2)}" if tokens_match else ""
        return f"   {MAGENTA}🧠 [{t_now}] Gemini Brain Replied:{RESET} {BOLD}TTFT = {ttft_str}{RESET} | {tokens_str}"

    # 13. Agent Speech Captured (Gayatri Dynamic Replies)
    if "[DIALOGUE CAPTURED: GAYATRI]" in line:
        text_match = re.search(r"GAYATRI\]\s*(?:\[\d+\.?\d*s\]\s*)?['\"](.*?)['\"]", line)
        speech_text = text_match.group(1) if text_match else line
        return f" {BOLD}{MAGENTA}🎙️ [{t_now}] Gayatri:{RESET} \"{speech_text}\""

    # 14. Voice Synthesis (TTS) Latency
    if "[LATENCY TRACE] TTS Metrics:" in line:
        ttfb_match = re.search(r"TTFB=(\d+\.?\d*)s", line)
        chars_match = re.search(r"Chars=(\d+)", line)
        ttfb_str = f"{float(ttfb_match.group(1))*1000:.0f}ms" if ttfb_match else "N/A"
        chars_str = f"{chars_match.group(1)} chars" if chars_match else ""
        return f"   {DIM}🗣️  [{t_now}] Voice Engine (Cartesia): TTFB = {ttfb_str} | {chars_str}{RESET}"

    # 15. Turn-by-Turn Latency Metrics
    if "[TURN " in line and "RESPONSE LATENCY]" in line:
        latency_match = re.search(r"(\d+\.?\d*ms\s*\(\d+\.?\d*s\))", line)
        turn_match = re.search(r"\[TURN\s*(\d+)", line)
        turn_num = turn_match.group(1) if turn_match else "?"
        lat_val = latency_match.group(1) if latency_match else line
        return f" {BOLD}{GREEN}⚡ [{t_now}] [TURN {turn_num} TOTAL LATENCY]{RESET} {BOLD}{GREEN}Caller silence -> Speech audio: {lat_val}{RESET}"

    if "[SILENCE RECOVERY]" in line:
        rec_match = re.search(r"after\s*(\d+\.?\d*s)", line)
        sec_val = rec_match.group(1) if rec_match else ""
        return f" {DIM}⏳ [{t_now}] [CALLER SILENCE] Gayatri checked in after {sec_val} of silence.{RESET}"

    # 16. Site Visit Booked
    if "REAL ESTATE SITE VISIT BOOKED" in line:
        return f"\n{BOLD}{GREEN}╔══════════════════════════════════════════════════════════════╗{RESET}\n" \
               f"{BOLD}{GREEN}║  🎉 [SUCCESS] SITE VISIT BOOKED!                             ║{RESET}\n" \
               f"{BOLD}{GREEN}╚══════════════════════════════════════════════════════════════╝{RESET}"

    if "Client Name" in line and ":" in line:
        return f"   {BOLD}• {line.split('enterprise_voice_agent:')[-1].strip()}{RESET}"
    if "Preferred Day" in line and ":" in line:
        return f"   {BOLD}• {line.split('enterprise_voice_agent:')[-1].strip()}{RESET}"
    if "Preferred Time" in line and ":" in line:
        return f"   {BOLD}• {line.split('enterprise_voice_agent:')[-1].strip()}{RESET}"
    if "Flat Type" in line and ":" in line:
        return f"   {BOLD}• {line.split('enterprise_voice_agent:')[-1].strip()}{RESET}"

    # 17. Call Termination & Disconnect
    if "[SILENCE WATCHDOG]" in line and "Prompting 'Hello'" in line:
        return f"\n {BOLD}{YELLOW}⏳ [{t_now}] [SILENCE DETECTED (>10s)]{RESET} Gayatri: \"Hello? Kya aap sun rahe hain?\""

    if "[SILENCE WATCHDOG]" in line and "Terminating call" in line:
        return f"\n {BOLD}{RED}⏳ [{t_now}] [SILENCE TIMEOUT (>30s)]{RESET} Gayatri: \"Aapka din shubh ho... bye!\" (Auto-terminating call)"

    if "audio buffer grace period before sending SIP BYE" in line:
        return f" {MAGENTA}📴 [{t_now}] Goodbye spoken. Disconnecting carrier line in 0.8s...{RESET}"

    if "Carrier SIP BYE sent" in line or "LiveKit room successfully deleted" in line:
        return f" {BOLD}{GREEN}✅ [{t_now}] Carrier line released (SIP BYE sent). Call ended.{RESET}"

    # 18. Post-Call Intelligence & Transcript Saving
    if "[SAVING CALL RECORD]" in line:
        acct_match = re.search(r"Account:\s*([^\s|]+)", line)
        acct = f" ({acct_match.group(1)})" if acct_match else ""
        return f"\n {BOLD}{BLUE}💾 [{t_now}] [SAVING CALL RECORD]{RESET} Finalizing transcript & saving under account{BOLD}{acct}{RESET}..."

    if "[POST-CALL INTELLIGENCE" in line:
        outcome_match = re.search(r"Outcome:\s*['\"]([^'\"]+)['\"]", line)
        sent_match = re.search(r"Sentiment:\s*['\"]([^'\"]+)['\"]", line)
        outcome_str = outcome_match.group(1) if outcome_match else "Completed"
        sent_str = f" | Sentiment: {sent_match.group(1)}" if sent_match else ""
        color = GREEN if "visit" in outcome_str.lower() or "interest" in outcome_str.lower() and "not" not in outcome_str.lower() else (RED if "not" in outcome_str.lower() else CYAN)
        return f" {BOLD}{color}🧠 [{t_now}] [AI CATEGORIZATION]{RESET} {BOLD}{color}{outcome_str}{RESET}{sent_str}"

    if "[TRANSCRIPT RECORDED]" in line:
        return f" {GREEN}📝 [{t_now}] [TRANSCRIPT SAVED]{RESET} Full dialogue saved to bookings/transcripts/ and call_transcripts.jsonl"

    if "[AUDIO RECORDING EMBEDDED]" in line:
        return f" {BOLD}{GREEN}🎙️ [{t_now}] [AUDIO RECORDING SAVED]{RESET} Audio recording embedded & ready for dashboard playback!"

    if "[AUDIO RECORDING]" in line and "Flushing" not in line:
        return f" {MAGENTA}🎙️ [{t_now}] [AUDIO RECORDING]{RESET} Capturing dual-channel conversation audio..."

    if "[WEBHOOK SYNC] Delivering" in line:
        return f" {CYAN}🌐 [{t_now}] [WEBHOOK SYNC]{RESET} Transmitting call data to Web Dashboard..."

    if "[WEBHOOK SYNC] Delivered!" in line:
        return f" {BOLD}{GREEN}✅ [{t_now}] [WEBHOOK DELIVERED]{RESET} Web Dashboard updated in real-time! (Status: 200 OK)"

    if "Could not deliver webhook" in line:
        return f" {BOLD}{RED}⚠️ [{t_now}] [WEBHOOK ERROR]{RESET} {line.split('webhook to')[-1].strip()}"

    if "Failed to record call billing or transcript" in line:
        return f" {BOLD}{RED}❌ [{t_now}] [SAVE ERROR]{RESET} {line.split('transcript:')[-1].strip()}"

    if "Active call lock released" in line:
        return f" {CYAN}🔒 [{t_now}] Call completed. Agent ready for next call.{RESET}\n" \
               f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}\n"

    # 19. Errors
    if "ERROR" in line or "[AGENT SESSION ERROR]" in line:
        if "Unclosed client session" in line or "Unclosed connector" in line:
            return ""
        return f" {BOLD}{RED}❌ [{t_now}] ERROR:{RESET} {line.split('ERROR')[-1].strip()}"

    # 20. Startup / LLM Compilation
    if "successfully compiled and selected" in line:
        model_match = re.search(r"'([^']+)'", line)
        model = model_match.group(1) if model_match else "Gemini"
        return f" {GREEN}🚀 Voice Agent Brain Active:{RESET} {BOLD}{model}{RESET} (Ready for calls!)"

    return ""

def main():
    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}    GAYATRI AI VOICE AGENT — LIVE CALL & LATENCY MONITOR               {RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    print(f" {DIM}Listening to live calls in real-time with full STT & Brain logs. Press Ctrl+C to exit.{RESET}\n")

    last_line = ""
    last_time = 0.0

    def print_clean(text: str):
        nonlocal last_line, last_time
        now = time.time()
        # Suppress identical messages printed within 1.0 second (systemd multi-logger duplicates)
        if text == last_line and (now - last_time) < 1.0:
            return
        last_line = text
        last_time = now
        print(text)
        sys.stdout.flush()

    # If input is piped (e.g. journalctl -u voice-agent -f | python3 track_live_calls.py)
    if not sys.stdin.isatty():
        try:
            for raw_line in sys.stdin:
                formatted = format_line(raw_line)
                if formatted:
                    print_clean(formatted)
        except KeyboardInterrupt:
            print("\nExiting tracker...")
        return

    # Check if journalctl is available (Linux VPS)
    if shutil.which("journalctl"):
        cmd = ["journalctl", "-u", "voice-agent", "-f", "-n", "25", "--output=cat"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                formatted = format_line(line)
                if formatted:
                    print_clean(formatted)
        except KeyboardInterrupt:
            proc.terminate()
            print("\nExiting tracker...")
        except Exception as e:
            print(f"Could not spawn journalctl: {e}")
    else:
        print("💡 journalctl not detected on this OS.")
        print("To stream from a log file: tail -f log_file.log | python scripts/track_live_calls.py")

if __name__ == "__main__":
    main()
