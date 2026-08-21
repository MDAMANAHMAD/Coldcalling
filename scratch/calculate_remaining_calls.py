import os
import json

def calculate_remaining_capacity():
    # Use path-independent relative paths so it works on both Windows and Linux VPS
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    log_path = os.path.join(base_dir, "bookings", "call_billing_log.jsonl")
    
    # 1. Define pre-paid subscription limits
    vobiz_paid_inr = 559.0        # ₹559 telephony balance
    cartesia_char_limit = 250000  # 250,000 characters included in $5 plan
    gemini_paid_inr = 1000.0      # ₹1,000 pre-loaded credit
    
    if not os.path.exists(log_path):
        print("📊 No call billing logs found. Using standard estimation averages:")
        print(f"   - Estimated Vobiz capacity   : {vobiz_paid_inr / 0.40 / 2.0:.0f} calls (2 min average)")
        print(f"   - Estimated Cartesia capacity: {cartesia_char_limit / 850:.0f} calls (850 chars/call)")
        print(f"   - Estimated Gemini capacity  : {gemini_paid_inr / 0.15:.0f} calls")
        return

    # 2. Gather actual live call stats
    total_calls = 0
    total_duration_mins = 0.0
    total_characters = 0
    total_vobiz_spend = 0.0
    total_cartesia_spend = 0.0
    total_llm_spend = 0.0
    total_spend = 0.0

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                total_calls += 1
                total_duration_mins += record.get("duration_minutes", 0.0)
                total_characters += record.get("characters_spoken", 0)
                total_vobiz_spend += record.get("cost_vobiz_inr", 0.0)
                total_cartesia_spend += record.get("cost_cartesia_inr", 0.0)
                total_llm_spend += record.get("cost_llm_inr", 0.0)
                total_spend += record.get("total_cost_inr", 0.0)
            except Exception:
                continue

    if total_calls == 0:
        print("⚠️ No valid call records found in the log.")
        return

    # 3. Calculate call averages
    avg_mins = total_duration_mins / total_calls
    avg_chars = total_characters / total_calls
    avg_vobiz_cost = total_vobiz_spend / total_calls
    avg_cartesia_cost = total_cartesia_spend / total_calls
    avg_llm_cost = total_llm_spend / total_calls
    avg_total_cost = total_spend / total_calls

    # 4. Calculate remaining balances
    vobiz_remaining_inr = max(0.0, vobiz_paid_inr - total_vobiz_spend)
    cartesia_chars_remaining = max(0, cartesia_char_limit - total_characters)
    gemini_remaining_inr = max(0.0, gemini_paid_inr - total_llm_spend)

    # 5. Calculate remaining calls based on each service
    remaining_calls_vobiz = int(vobiz_remaining_inr / avg_vobiz_cost) if avg_vobiz_cost > 0 else 9999
    remaining_calls_cartesia = int(cartesia_chars_remaining / avg_chars) if avg_chars > 0 else 9999
    remaining_calls_gemini = int(gemini_remaining_inr / avg_llm_cost) if avg_llm_cost > 0 else 9999

    # Find the bottleneck (the service that will run out first)
    bottleneck_calls = min(remaining_calls_vobiz, remaining_calls_cartesia, remaining_calls_gemini)
    bottleneck_service = "Cartesia (Voice)"
    if bottleneck_calls == remaining_calls_vobiz:
        bottleneck_service = "Vobiz (Telephony)"
    elif bottleneck_calls == remaining_calls_gemini:
        bottleneck_service = "Google Gemini (LLM)"

    print("=" * 70)
    # Emojis removed to prevent console encoding issues
    print("REMAINING CALL CAPACITY REPORT")
    print("=" * 70)
    print(f"Based on {total_calls} actual calls made:")
    print(f"  - Average Call Duration : {avg_mins:.2f} minutes")
    print(f"  - Average Cartesia Chars: {avg_chars:.0f} characters")
    print(f"  - Average Cost Per Call : Rs. {avg_total_cost:.2f}")
    print("-" * 70)
    print("CREDITS & CAPACITY BREAKDOWN:")
    print("-" * 70)
    print(f"1. Vobiz Telephony (Rs. 559 paid):")
    print(f"   - Remaining Balance : Rs. {vobiz_remaining_inr:.2f}")
    print(f"   - Capacity Left     : {remaining_calls_vobiz} calls ({vobiz_remaining_inr / 0.40:.1f} minutes)")
    print()
    print(f"2. Cartesia Voice (Rs. 490 / 250k chars paid):")
    print(f"   - Remaining Chars   : {cartesia_chars_remaining:,} characters")
    print(f"   - Capacity Left     : {remaining_calls_cartesia} calls")
    print()
    print(f"3. Google Gemini AI (Rs. 1,000 paid):")
    print(f"   - Remaining Balance : Rs. {gemini_remaining_inr:.2f}")
    print(f"   - Capacity Left     : {remaining_calls_gemini} calls")
    print("-" * 70)
    print(f"⭐ TOTAL SAFE CAPACITY LEFT: {bottleneck_calls} calls")
    print(f"   (Bottleneck Service: {bottleneck_service})")
    print("=" * 70)

if __name__ == "__main__":
    calculate_remaining_capacity()
