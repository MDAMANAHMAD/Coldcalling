import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")

HINDI_REAL_ESTATE_PROMPT = """# IDENTITY & GREETING FLOW
- **Name/Identity**: Gayatri, warm & professional Property Advisor at Shiv Sai Construction, representing the Sai Complex project in Dombivli East.
- **Greeting (Turn 1)**: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
"""

print("=== LLM Response Latency Benchmark: Groq vs Google Gemini ===")
print("Prompt size: ~200 tokens (System instructions + user question)")

results = {}

# 1. Benchmark Groq
if groq_key:
    model_name = "openai/gpt-oss-20b"
    print(f"\n⚡ [Groq] Testing '{model_name}'...")
    t0 = time.perf_counter()
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": HINDI_REAL_ESTATE_PROMPT},
                    {"role": "user", "content": "Haan boliye, kya project hai?"}
                ],
                "temperature": 0.3,
                "max_tokens": 150
            },
            timeout=8
        )
        dt = time.perf_counter() - t0
        if r.status_code == 200:
            res_data = r.json()
            completion_text = res_data['choices'][0]['message']['content'].strip()
            print(f"  Status: {r.status_code} | Time: {dt:.3f} seconds")
            print(f"  Response: '{completion_text[:80]}...'")
            results["Groq"] = dt
        else:
            print(f"  ❌ Error {r.status_code}: {r.text}")
            results["Groq"] = f"Error {r.status_code}"
    except Exception as e:
        print(f"  ❌ Connection Error: {e}")
        results["Groq"] = "Connection Error"
else:
    print("\n[Groq] Key not set in .env")
    results["Groq"] = "Key not set"

# 2. Benchmark Google Gemini
if google_key:
    gemini_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]
    from livekit.plugins import google as lk_google
    from livekit.agents import llm as agents_llm
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    for model_name in gemini_models:
        print(f"\n⚡ [Google Gemini] Testing '{model_name}' via LiveKit Plugin...")
        t0 = time.perf_counter()
        try:
            llm_instance = lk_google.LLM(
                model=model_name,
                api_key=google_key,
                temperature=0.3
            )
            
            chat_ctx = agents_llm.ChatContext()
            chat_ctx.add_message(role="system", content=HINDI_REAL_ESTATE_PROMPT)
            chat_ctx.add_message(role="user", content="Haan boliye, kya project hai?")
            
            async def _run_gemini():
                chat_stream = llm_instance.chat(chat_ctx=chat_ctx)
                full_text = ""
                async for chunk in chat_stream:
                    if hasattr(chunk, 'delta') and chunk.delta and hasattr(chunk.delta, 'content') and chunk.delta.content:
                        full_text += chunk.delta.content
                    elif hasattr(chunk, 'choices') and chunk.choices:
                        choice = chunk.choices[0]
                        if hasattr(choice, 'delta') and choice.delta and hasattr(choice.delta, 'content') and choice.delta.content:
                            full_text += choice.delta.content
                return full_text

            response_text = loop.run_until_complete(_run_gemini())
            dt = time.perf_counter() - t0
            print(f"  Status: Success | Time: {dt:.3f} seconds")
            print(f"  Response: '{response_text.strip()[:80]}...'")
            results[f"Gemini ({model_name})"] = dt
        except Exception as e:
            print(f"  ❌ LiveKit Plugin Error for {model_name}: {e}")
            results[f"Gemini ({model_name})"] = "Error"
else:
    print("\n[Google Gemini] Key not set in .env")
    results["Gemini"] = "Key not set"


# Print side-by-side table
print("\n" + "="*50)
print(f"{'Provider':<20} | {'Latency (seconds)':<20}")
print("="*50)
for provider, score in results.items():
    if isinstance(score, float):
        print(f"{provider:<20} | {score:.3f} seconds")
    else:
        print(f"{provider:<20} | {score}")
print("="*50)
