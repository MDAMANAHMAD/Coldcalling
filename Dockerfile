FROM python:3.11-slim

WORKDIR /app

# Install system audio and build utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY voice_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY voice_agent/ ./voice_agent/

# Memory optimization environment variables for 512MB Render instances
ENV PYTHONUNBUFFERED=1
ENV MALLOC_ARENA_MAX=2
ENV PYTHONMALLOC=malloc

# Run the LiveKit Agent in start mode
CMD ["python", "voice_agent/agent.py", "start"]
