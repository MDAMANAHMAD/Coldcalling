# LiveKit + Google Gemini Live + Vobiz SIP Outbound Voice AI Agent

A production-ready, ultra-low-latency (~300–500ms) outbound Voice AI Cold Calling agent powered by:
- **LiveKit Agent Framework**: Real-time WebRTC/SIP media server and agent orchestration.
- **Google Gemini Live (Realtime API)**: Native multimodal speech-to-speech engine for conversational audio.
- **Vobiz SIP Trunking**: Outbound telecommunications carrier bridge for dialing physical phone numbers.
- **Silero VAD**: Low-latency Voice Activity Detection enabling instant interruption handling (barge-in).

---

## Architecture Diagram

```
[Target Phone Number] (+91XXXXXXXXXX)
         ▲
         │ PSTN / Cellular
         ▼
[Vobiz SIP Trunk] (sip.vobiz.ai)
         ▲
         │ SIP Signaling & RTP Audio
         ▼
[LiveKit Cloud / Server] (SIP Participant Room)
         ▲
         │ WebRTC Audio Stream
         ▼
[LiveKit Python Agent Worker] (agent.py)
         ▲
         │ Native Speech-to-Speech (Bi-directional WebSocket)
         ▼
[Google Gemini Live Realtime] (gemini-2.5-flash)
```

---

## 1. Account Subscriptions & Setup Guide

### Step 1: LiveKit Cloud Account & Keys
1. Go to [https://cloud.livekit.io](https://cloud.livekit.io) and create a free account (LiveKit gives free monthly bandwidth and compute credits).
2. Create a new project (e.g. `cold-calling-voice-agent`).
3. In the left navigation menu, go to **Settings** -> **Keys**.
4. Copy your:
   - **`LIVEKIT_URL`** (e.g. `wss://your-project-subdomain.livekit.cloud`)
   - **`LIVEKIT_API_KEY`** (e.g. `APIxxxxxxxxxxxx`)
   - **`LIVEKIT_API_SECRET`** (e.g. `secretxxxxxxxxxxxxxxxx`)

---

### Step 2: Google Gemini Live API Key
1. Visit Google AI Studio: [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Sign in with your Google account.
3. Click **Create API Key** -> Select your Google Cloud Project.
4. Copy your **`GOOGLE_API_KEY`**.
*(Note: Google AI Studio offers free-tier usage for Gemini multimodal models).*

---

### Step 3: Vobiz SIP Trunking Account & Outbound Number
1. Sign up on [https://vobiz.ai](https://vobiz.ai) (or your preferred SIP provider like Twilio/Telnyx).
2. In your Vobiz portal:
   - Go to **Numbers / DIDs** and buy an outbound caller ID number (e.g. India `+91` or US `+1`).
   - Go to **SIP Trunks / Credentials** and note down:
     - **SIP Host/Domain**: `sip.vobiz.ai` (or port `5060`)
     - **SIP Username / Auth User**: Your Vobiz SIP account username
     - **SIP Password**: Your Vobiz SIP password
     - **Caller ID**: Your purchased phone number in E.164 format

---

### Step 4: Configure the Vobiz SIP Trunk in LiveKit Dashboard
1. Open your [LiveKit Cloud Dashboard](https://cloud.livekit.io).
2. Go to **SIP** in the left navigation sidebar.
3. Select the **Outbound Trunks** tab and click **Create Outbound Trunk**.
4. Fill in the Vobiz trunk details:
   - **Trunk Name**: `Vobiz-Outbound-Primary`
   - **Address**: `sip.vobiz.ai` (or `sip.vobiz.ai:5060`)
   - **Transport**: `UDP` or `Auto`
   - **Auth Username**: Your Vobiz username
   - **Auth Password**: Your Vobiz password
   - **Numbers (Caller IDs)**: Add your purchased Vobiz phone number (e.g. `+91XXXXXXXXXX`)
5. Click **Save Trunk**.
6. Copy the generated **Trunk ID** (e.g. `ST_xxxxxxxxxxxxxxxx`) and save it as **`SIP_OUTBOUND_TRUNK_ID`**.

---

## 2. Local Installation & Configuration

### Step 1: Clone / Navigate to Directory
```bash
cd voice_agent
```

### Step 2: Create Python Virtual Environment (Python 3.10+)
```bash
# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# On Linux/macOS:
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure `.env`
Create a `.env` file in the `voice_agent` folder by copying `.env.example`:
```bash
cp .env.example .env
```

Populate the `.env` file with your credentials:
```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxxxxxx
LIVEKIT_API_SECRET=secretxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SIP_OUTBOUND_TRUNK_ID=ST_xxxxxxxxxxxxxxxx
```

---

## 3. Running the Outbound Voice AI Agent

### Step 1: Start the LiveKit Agent Worker (Terminal 1)
Run the agent in development watch mode:
```bash
python agent.py dev
```
*The worker connects to LiveKit Cloud and continuously listens for incoming or outbound SIP rooms to handle calls automatically.*

---

### Step 2: Trigger Outbound Calls (Terminal 2)

#### 1. Single Contact Dialing:
```bash
python outbound_dialer.py --phone +918693081506 --name "Aman" --company "Aman Corp"
```

#### 2. Batch CSV Dialing:
```bash
python outbound_dialer.py --csv sample_leads.csv
```

---

## 4. How the AI Conversation Works

1. **Instant Connection:** When the dialed lead answers their phone, Vobiz bridges the call to LiveKit.
2. **Personalized Greeting:** `agent.py` detects the lead's name and company from the room metadata and immediately speaks:
   > *"Hi Aman! This is Sarah from Antigravity. I noticed Aman Corp was exploring operational automation—did I catch you at a good time for a quick 60 seconds?"*
3. **Speech-to-Speech Streaming:** Gemini Live Realtime receives microphone audio from the phone and speaks back in under 400ms without text intermediate conversions.
4. **Barge-in / Interruption:** If the customer interrupts the agent at any point, Silero VAD cuts off the agent's voice instantly.
5. **Tool Execution:** When the customer agrees to a demo, Gemini automatically triggers `book_demo_appointment(...)`, saving the appointment details into `bookings/demo_appointments.jsonl`.

---

## 5. Production Server Deployment (Render / AWS / Docker)

### Running as a Linux Systemd Service (Ubuntu / Debian VPS)
Create `/etc/systemd/system/voice-agent.service`:
```ini
[Unit]
Description=LiveKit Outbound Voice AI Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cold-calling/voice_agent
EnvironmentFile=/home/ubuntu/cold-calling/voice_agent/.env
ExecStart=/home/ubuntu/cold-calling/voice_agent/venv/bin/python agent.py start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable voice-agent
sudo systemctl start voice-agent
sudo systemctl status voice-agent
```
