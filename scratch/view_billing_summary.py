import os
import json
import sys

def view_summary():
    # Use path-independent relative paths so it works on both Windows and Linux VPS
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    log_path = os.path.join(base_dir, "bookings", "call_billing_log.jsonl")
    
    if not os.path.exists(log_path):
        print("📊 No call billing logs found yet. Once you make your first call, the stats will appear here!")
        return

    total_calls = 0
    total_duration_mins = 0.0
    total_characters = 0
    total_input_tokens = 0
    total_output_tokens = 0
    
    total_vobiz_cost = 0.0
    total_cartesia_cost = 0.0
    total_llm_cost = 0.0
    total_cost = 0.0

    print("=" * 80)
    print("📞 DETAILED CALL LOGS:")
    print("=" * 80)
    print(f"{'Date/Time (UTC)':<20} | {'Customer':<12} | {'Mins':<6} | {'Chars':<6} | {'Tokens':<8} | {'Total Cost':<10} | {'Per Min':<8}")
    print("-" * 80)

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                total_calls += 1
                duration_mins = record.get("duration_minutes", 0.0)
                total_duration_mins += duration_mins
                total_characters += record.get("characters_spoken", 0)
                total_input_tokens += record.get("input_tokens", 0)
                total_output_tokens += record.get("output_tokens", 0)
                
                total_vobiz_cost += record.get("cost_vobiz_inr", 0.0)
                total_cartesia_cost += record.get("cost_cartesia_inr", 0.0)
                total_llm_cost += record.get("cost_llm_inr", 0.0)
                total_cost += record.get("total_cost_inr", 0.0)
                
                # Format timestamp
                dt_str = record.get("timestamp", "").split(".")[0].replace("T", " ")
                customer = record.get("customer_name", "Unknown")[:12]
                mins = f"{duration_mins:.2f}"
                chars = str(record.get("characters_spoken", 0))
                tokens = str(record.get("input_tokens", 0) + record.get("output_tokens", 0))
                cost = f"Rs. {record.get('total_cost_inr', 0.0):.2f}"
                
                # Per minute calculation
                per_min_val = record.get("cost_per_minute_inr", record.get("total_cost_inr", 0.0) / duration_mins if duration_mins > 0 else 0.0)
                per_min_str = f"Rs. {per_min_val:.2f}"
                
                print(f"{dt_str:<20} | {customer:<12} | {mins:<6} | {chars:<6} | {tokens:<8} | {cost:<10} | {per_min_str:<8}")
            except Exception as e:
                continue

    print("=" * 80)
    print("📊 CUMULATIVE BILLING SUMMARY:")
    print("=" * 80)
    print(f"Total Calls Tracked:       {total_calls}")
    print(f"Total Call Duration:      {total_duration_mins:.2f} minutes")
    print(f"Total Characters Spoken:  {total_characters} characters (Cartesia)")
    print(f"Total LLM Tokens Used:    {total_input_tokens + total_output_tokens} (In: {total_input_tokens}, Out: {total_output_tokens})")
    print("-" * 80)
    print(f"Estimated Telephony (Vobiz):  Rs. {total_vobiz_cost:.2f}")
    print(f"Estimated Voice (Cartesia):   Rs. {total_cartesia_cost:.2f}")
    print(f"Estimated Brain (LLM):        Rs. {total_llm_cost:.2f}")
    print("-" * 80)
    print(f"⭐ TOTAL ESTIMATED SPEND:      Rs. {total_cost:.2f}")
    avg_per_minute = total_cost / total_duration_mins if total_duration_mins > 0 else 0.0
    print(f"Average Cost Per Call:         Rs. {(total_cost / total_calls):.2f}" if total_calls > 0 else "Average Cost Per Call:         Rs. 0.00")
    print(f"Average Cost Per Minute:       Rs. {avg_per_minute:.2f}")
    print("=" * 80)

if __name__ == "__main__":
    view_summary()
