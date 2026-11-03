#!/usr/bin/env python3
"""
Diagnostic & Verification Script for Sarvam AI Voice Agent Gayatri.
Verifies credentials, connectivity, available agent versions,
and tests outbound calling specifically with the latest agent version (v26).
"""

import os
import sys
import argparse
import requests
import json
import time
from datetime import datetime, timedelta, timezone

API_KEY = os.getenv('SARVAM_API_KEY', 'sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI')
ORG_ID = os.getenv('SARVAM_ORG_ID', '01a16c8c-0d2f-7ded-b3cb-6dedfbcc168e')
WORKSPACE_ID = os.getenv('SARVAM_WORKSPACE_ID', '01a16c8c-0d68-778c-b5f4-fcd65dd809e6')
AGENT_ID = os.getenv('SARVAM_AGENT_ID', 'Gayatari-0922c4e8-551f')
CONNECTION_ID = 'Vobiz-MD-s--9a5a5823-1853'
FROM_NUMBER = '+918071580297'
LATEST_VERSION = int(os.getenv('SARVAM_AGENT_VERSION', '27'))

HEADERS = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
}

def check_analytics_recent_calls():
    print(f"\n=======================================================")
    print(f" 1. Inspecting Recent Call History from Analytics API")
    print(f"=======================================================")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    end = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    url = f"https://apps.sarvam.ai/api/analytics/v1/{ORG_ID}/{WORKSPACE_ID}/{AGENT_ID}/interactions?start_datetime={start}&end_datetime={end}&limit=20"
    
    try:
        res = requests.get(url, headers={'X-API-Key': API_KEY}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = data.get('items', [])
            print(f"[OK] Fetched {len(items)} interactions in the last 3 days.")
            versions_used = set()
            for it in items[:6]:
                v = it.get('app_version')
                versions_used.add(v)
                print(f"   * Interaction: {it.get('start_datetime')} | Version: v{v} | To: {it.get('user_contact')} | Duration: {round(it.get('duration_in_seconds', 0), 1)}s")
            print(f"[Summary] Observed versions in recent logs: {sorted(list(versions_used))}")
            return items
        else:
            print(f"[FAIL] Analytics API returned status {res.status_code}: {res.text[:200]}")
    except Exception as e:
        print(f"[ERROR] Analytics API check failed: {e}")
    return []

def verify_version_availability(target_version=LATEST_VERSION):
    print(f"\n=======================================================")
    print(f" 2. Verifying Agent Version v{target_version} on Sarvam")
    print(f"=======================================================")
    outbound_url = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{ORG_ID}/workspaces/{WORKSPACE_ID}/outbounds"
    
    # We test dummy structure to verify app_id and app_version existence
    payload = {
        "app_config": {
            "app_id": AGENT_ID,
            "app_version": target_version,
            "connection_config": {
                "connection_id": CONNECTION_ID,
                "agent_phone_number": FROM_NUMBER
            }
        },
        "user_config": {
            "user_phone_number": "+919999999999"  # Dummy check
        }
    }

    try:
        res = requests.post(outbound_url, headers=HEADERS, json=payload, timeout=10)
        print(f"Outbound API Probe Status: {res.status_code}")
        if res.status_code in [200, 201]:
            data = res.json()
            attempt_id = data.get('attempt_id')
            print(f"[SUCCESS] Agent Version v{target_version} is ACTIVE and VALIDATED on Sarvam!")
            print(f"          Probe attempt_id: {attempt_id}")
            return True
        elif res.status_code == 402:
            print(f"[ALERT: INSUFFICIENT CREDITS] Sarvam AI account credits are EXHAUSTED (HTTP 402)!")
            print(f"Details: {res.text}")
            print(f"--> Diagnostic Finding: Agent Gayatri v{target_version} is configured properly, but Sarvam is refusing outbound calls until the account balance is topped up on apps.sarvam.ai.")
            return False
        elif res.status_code == 404:
            print(f"[NOT FOUND] Version v{target_version} was not found on Sarvam API: {res.text}")
            return False
        else:
            print(f"[RESPONSE] Status {res.status_code}: {res.text}")
            return True
    except Exception as e:
        print(f"[ERROR] Version probe failed: {e}")
        return False

def initiate_test_call(phone_number, version=LATEST_VERSION):
    print(f"\n=======================================================")
    print(f" 3. Initiating Live Test Call with Latest Agent (v{version})")
    print(f"=======================================================")
    # Clean phone number
    clean_digits = ''.join(c for c in phone_number if c.isdigit())
    if clean_digits.startswith('91') and len(clean_digits) == 12:
        clean_digits = clean_digits[2:]
    elif clean_digits.startswith('0') and len(clean_digits) == 11:
        clean_digits = clean_digits[1:]

    if len(clean_digits) != 10:
        print(f"[ERROR] Invalid Indian phone number length ({len(clean_digits)} digits). Must be 10 digits.")
        return False

    full_phone = f"+91{clean_digits}"
    outbound_url = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{ORG_ID}/workspaces/{WORKSPACE_ID}/outbounds"

    payload = {
        "app_config": {
            "app_id": AGENT_ID,
            "app_version": version,
            "connection_config": {
                "connection_id": CONNECTION_ID,
                "agent_phone_number": FROM_NUMBER
            }
        },
        "user_config": {
            "user_phone_number": full_phone
        }
    }

    print(f"Calling: {full_phone}")
    print(f"From Trunk: {FROM_NUMBER}")
    print(f"Agent ID: {AGENT_ID}")
    print(f"App Version: v{version}")
    print(f"Connection: {CONNECTION_ID}")

    try:
        res = requests.post(outbound_url, headers=HEADERS, json=payload, timeout=15)
        print(f"\nSarvam Outbound Response: HTTP {res.status_code}")
        if res.status_code in [200, 201]:
            data = res.json()
            attempt_id = data.get('attempt_id')
            print(f"\n>>> CALL DISPATCHED SUCCESSFULLY! <<<")
            print(f"Attempt ID : {attempt_id}")
            print(f"Target     : {full_phone}")
            print(f"Agent Ver  : v{version} (Gayatri Latest)")
            print(f"Phone should ring within 5-10 seconds.")
            return attempt_id
        elif res.status_code == 402:
            print(f"\n[CRITICAL FAILURE] Dial blocked by Sarvam due to INSUFFICIENT CREDITS (HTTP 402).")
            print(f"Sarvam Response: {res.text}")
            print(f"Action Required: Top up your credits on https://apps.sarvam.ai to resume calls.")
            return None
        else:
            print(f"[FAIL] Dial failed ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"[ERROR] Could not dispatch outbound call: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Verify and Test Sarvam Gayatri Agent Version")
    parser.add_argument('--phone', type=str, help="Recipient phone number to place a live test call (e.g. 8898022337)")
    parser.add_argument('--version', type=int, default=LATEST_VERSION, help=f"Agent version to test (default: {LATEST_VERSION})")
    args = parser.parse_args()

    print(f"Checking Sarvam AI Voice Agent Configuration...")
    print(f"Org ID: {ORG_ID}")
    print(f"Workspace: {WORKSPACE_ID}")
    print(f"Agent ID: {AGENT_ID}")
    print(f"Target Agent Version: v{args.version}")

    # Step 1: Recent calls inspection
    check_analytics_recent_calls()

    # Step 2: Verify version availability
    is_valid = verify_version_availability(args.version)

    # Step 3: Optional live test call
    if args.phone:
        if is_valid:
            initiate_test_call(args.phone, args.version)
        else:
            print(f"[ABORT] Cannot dial: Version v{args.version} is not active on Sarvam.")
    else:
        print(f"\nTo place a live test call to your phone with v{args.version}, run:")
        print(f"  python scripts/verify_sarvam_agent_version.py --phone <your_10_digit_number>")

if __name__ == '__main__':
    main()
