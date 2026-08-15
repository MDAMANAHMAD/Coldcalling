import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Pre-import google plugin
import livekit.plugins.google as lk_google

async def main():
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        print("No GOOGLE_API_KEY found!")
        return

    print("Instantiating Google LLM...")
    llm = lk_google.LLM(
        model="gemini-flash-latest",
        api_key=google_key,
        temperature=0.0
    )

    print("Running _prewarm_impl for the first time (compiling)...")
    t0 = time.perf_counter()
    try:
        await llm._prewarm_impl()
        t1 = time.perf_counter() - t0
        print(f"First prewarm took: {t1:.3f} seconds")
    except Exception as e:
        print("Prewarm error:", e)

    # Let's run a test chat call to see if the first request is now instant
    print("Testing a dummy chat completion with function tools to see latency...")
    from livekit.agents import llm as agents_llm
    from voice_agent.agent import PriyaRealEstateAgent
    
    agent = PriyaRealEstateAgent()
    agent_tools = agent.tools
    print(f"Loaded {len(agent_tools)} tools from agent.")
    
    chat_ctx = agents_llm.ChatContext()
    chat_ctx.add_message(role="user", content="hello")
    
    # We call llm.chat with tools to compile function-calling schemas
    t2 = time.perf_counter()
    try:
        chat_stream = llm.chat(chat_ctx=chat_ctx, tools=agent_tools)
        async for chunk in chat_stream:
            # Just consume first chunk
            print("First chunk received!")
            break
        t3 = time.perf_counter() - t2
        print(f"First chat reply latency: {t3:.3f} seconds")
    except Exception as e:
        print("Chat completion error:", e)

if __name__ == "__main__":
    asyncio.run(main())
