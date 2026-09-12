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

def format_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""

    # Skip duplicates or noisy system warnings
    for pattern in IGNORED_PATTERNS:
        if pattern in line:
            return ""

    # 1. New Call Inbound / Job Received
    if "Job received for Room:" in line:
        room_match = re.search(r"Job received for Room:\s*([^\s]+)", line)
        room_name = room_match.group(1) if room_match else "Unknown"
        return f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}\n" \
               f" {BOLD}{GREEN}📞 [INCOMING CALL]{RESET} Room: {YELLOW}{room_name}{RESET} | Connecting..."

    # 2. Caller Joined & Customer Identity
    if "Caller joined:" in line:
        caller = line.split("Caller joined:")[-1].strip()
        return f" {CYAN}👤 Caller Connected:{RESET} {BOLD}{caller}{RESET}"

    if "Resolved customer name dynamically" in line:
        name = line.split("participants:")[-1].strip()
        return f" {CYAN}🏷️  Customer Name:{RESET} {BOLD}{GREEN}{name}{RESET}"

    if "Kusha Cloned Voice" in line and ("Initializing Cartesia TTS" in line or "STATE RESET" in line):
        return f" {MAGENTA}🎙️ Voice Engine:{RESET} {BOLD}Cartesia Kusha Cloned Voice (ID: 68da925c-0163-4b50-a4e6-08862f6dd5de){RESET}"

    # 3. Agent Session Ready
    if "Speaking Greeting to caller" in line:
        return f" {MAGENTA}👋 Gayatri is greeting caller...{RESET}"

    # 4. User Speech Transcripts (STT)
    if "[STT TRANSCRIPT] Final=True" in line:
        text_match = re.search(r"Text:\s*['\"](.*?)['\"]", line)
        time_match = re.search(r"\(\+(\d+\.?\d*ms)\)", line)
        speech_text = text_match.group(1) if text_match else line
        timing = f" {DIM}(STT took {time_match.group(1)}){RESET}" if time_match else ""
        return f"\n {BOLD}{YELLOW}👤 Caller:{RESET} \"{speech_text}\"{timing}"

    # 4.1 Agent Speech Captured (Gayatri Dynamic Replies)
    if "[DIALOGUE CAPTURED: GAYATRI]" in line:
        text_match = re.search(r"GAYATRI\]\s*['\"](.*?)['\"]", line)
        speech_text = text_match.group(1) if text_match else line
        return f" {BOLD}{MAGENTA}🎙️ Gayatri:{RESET} \"{speech_text}\""

    # 5. Fast Turn-Taking / User Stopped Speaking
    if "[VAD] User stopped speaking!" in line:
        return f" {DIM}⏱️  [VAD] Caller stopped speaking -> Waiting for transcript & LLM...{RESET}"

    # 6. Latency Metrics (Turn-by-Turn response time)
    if "[TURN " in line and "RESPONSE LATENCY]" in line:
        latency_match = re.search(r"(\d+\.?\d*ms\s*\(\d+\.?\d*s\))", line)
        turn_match = re.search(r"\[TURN\s*(\d+)", line)
        turn_num = turn_match.group(1) if turn_match else "?"
        lat_val = latency_match.group(1) if latency_match else line
        return f" {BOLD}{GREEN}⚡ [TURN {turn_num} LATENCY]{RESET} {BOLD}{GREEN}Response Time: {lat_val}{RESET}"

    # 7. LLM Latency Trace
    if "[LATENCY TRACE] LLM Metrics:" in line:
        ttft_match = re.search(r"TTFT=(\d+\.?\d*)s", line)
        tokens_match = re.search(r"Prompt=(\d+)\s*\|\s*Completion=(\d+)", line)
        ttft_str = f"{float(ttft_match.group(1))*1000:.0f}ms" if ttft_match else "N/A"
        tokens_str = f"Prompt={tokens_match.group(1)}, Out={tokens_match.group(2)}" if tokens_match else ""
        return f"   {DIM}🧠 Brain (Gemini): TTFT = {ttft_str} | {tokens_str}{RESET}"

    # 8. TTS Latency Trace
    if "[LATENCY TRACE] TTS Metrics:" in line:
        ttfb_match = re.search(r"TTFB=(\d+\.?\d*)s", line)
        chars_match = re.search(r"Chars=(\d+)", line)
        ttfb_str = f"{float(ttfb_match.group(1))*1000:.0f}ms" if ttfb_match else "N/A"
        chars_str = f"{chars_match.group(1)} chars" if chars_match else ""
        return f"   {DIM}🗣️  Voice (Cartesia): TTFB = {ttfb_str} | {chars_str}{RESET}"

    # 9. Site Visit Booked
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

    # 10. Call Termination & Disconnect
    if "[SILENCE WATCHDOG]" in line and "Prompting 'Hello'" in line:
        return f"\n {BOLD}{YELLOW}⏳ [SILENCE DETECTED (>10s)]{RESET} Gayatri: \"Hello? Kya aap sun rahe hain?\""

    if "[SILENCE WATCHDOG]" in line and "Terminating call" in line:
        return f"\n {BOLD}{RED}⏳ [SILENCE TIMEOUT (>30s)]{RESET} Gayatri: \"Aapka din shubh ho... bye!\" (Auto-terminating call)"

    if "Disconnecting SIP room in" in line:
        return f" {MAGENTA}📴 Call ending... Hanging up carrier line.{RESET}"

    if "Terminating SIP call and deleting room" in line:
        return f" {MAGENTA}✅ Carrier line released (SIP BYE sent).{RESET}"

    # 10.1 Post-Call Intelligence & Transcript Saving
    if "[SAVING CALL RECORD]" in line:
        acct_match = re.search(r"Account:\s*([^\s|]+)", line)
        acct = f" ({acct_match.group(1)})" if acct_match else ""
        return f"\n {BOLD}{BLUE}💾 [SAVING CALL RECORD]{RESET} Finalizing transcript & saving under account{BOLD}{acct}{RESET}..."

    if "[POST-CALL INTELLIGENCE" in line:
        outcome_match = re.search(r"Outcome:\s*['\"]([^'\"]+)['\"]", line)
        sent_match = re.search(r"Sentiment:\s*['\"]([^'\"]+)['\"]", line)
        outcome_str = outcome_match.group(1) if outcome_match else "Completed"
        sent_str = f" | Sentiment: {sent_match.group(1)}" if sent_match else ""
        color = GREEN if "visit" in outcome_str.lower() or "interest" in outcome_str.lower() and "not" not in outcome_str.lower() else (RED if "not" in outcome_str.lower() else CYAN)
        return f" {BOLD}{color}🧠 [AI CATEGORIZATION]{RESET} {BOLD}{color}{outcome_str}{RESET}{sent_str}"

    if "[TRANSCRIPT RECORDED]" in line:
        return f" {GREEN}📝 [TRANSCRIPT SAVED]{RESET} Full dialogue saved to bookings/transcripts/ and call_transcripts.jsonl"

    if "[WEBHOOK SYNC] Delivering" in line:
        return f" {CYAN}🌐 [WEBHOOK SYNC]{RESET} Transmitting call data to Web Dashboard..."

    if "[WEBHOOK SYNC] Delivered!" in line:
        return f" {BOLD}{GREEN}✅ [WEBHOOK DELIVERED]{RESET} Web Dashboard updated in real-time! (Status: 200 OK)"

    if "Could not deliver webhook" in line:
        return f" {BOLD}{RED}⚠️ [WEBHOOK ERROR]{RESET} {line.split('webhook to')[-1].strip()}"

    if "Failed to record call billing or transcript" in line:
        return f" {BOLD}{RED}❌ [SAVE ERROR]{RESET} {line.split('transcript:')[-1].strip()}"

    if "Active call lock released" in line:
        return f" {CYAN}🔒 Call completed. Agent ready for next call.{RESET}\n" \
               f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}\n"

    # 11. Errors
    if "ERROR" in line or "[AGENT SESSION ERROR]" in line:
        return f" {BOLD}{RED}❌ ERROR:{RESET} {line.split('ERROR')[-1].strip()}"

    # 12. Startup / LLM Compilation
    if "successfully compiled and selected" in line:
        model_match = re.search(r"'([^']+)'", line)
        model = model_match.group(1) if model_match else "Gemini"
        return f" {GREEN}🚀 Voice Agent Brain Active:{RESET} {BOLD}{model}{RESET} (Ready for calls!)"

    return ""

def main():
    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}    GAYATRI AI VOICE AGENT — LIVE CALL & LATENCY MONITOR               {RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    print(f" {DIM}Listening to live calls in real-time. Press Ctrl+C to exit.{RESET}\n")

    last_line = ""
    last_time = 0.0

    def print_clean(text: str):
        nonlocal last_line, last_time
        now = time.time()
        # Suppress identical messages printed within 1.5 seconds (systemd multi-logger duplicates)
        if text == last_line and (now - last_time) < 1.5:
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
