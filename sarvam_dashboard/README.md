# Sai Garden — Dedicated Sarvam AI Voice Calling Dashboard

This folder contains the complete, dedicated Sarvam AI integration and dashboard suite customized specifically for the **Sai Garden** real estate project (Lodha Heaven, Nilje, Dombivli East, opp. Xperia Mall, MahaRERA: PR1330002501452).

## Configuration Credentials:
- **SARVAM_API_KEY**: `sk_samvaad_zwb1zcz6_1iukvGXfgQG21wlwTrclbhJI`
- **SARVAM_AGENT_ID**: `Gayatari-0922c4e8-551f`
- **SARVAM_FROM_NUMBER**: `+918071580297`
- **Domain**: `https://qualivo.duckdns.org/sarvam-dashboard`

---

## Core Dashboard Architecture & Pages:

1. **Home & Upload Page (`/sarvam-dashboard`)**:
   - **Automated CSV Format Verification & Auto-Healing**: Verifies headers against Sarvam AI's cohort specification (`phone_number,user_name,initial_bot_message,initial_state_name,initial_language_name`). Automatically repairs swapped names/phones, trims prefixes, extracts valid 10-digit Indian numbers, and allows downloading the healed Sarvam CSV.
   - **Live Calling Sheet Progress Card**: Displays ongoing calling sheet status (Total contacts, Completed, Remaining, Interested, and Site Visits).
   - **Key Performance Indicators**: Total calls, Site visits, Positive intent, and 1 BHK vs 2 BHK preference distribution.
   - **Time Filter Bar**: Filter all data across `Today`, `Yesterday`, `Last 7 Days`, `Last 30 Days`, or `All Time`.

2. **Analytical Page (`/sarvam-dashboard/analytics`)**:
   - Detailed conversion funnel (Calls Initiated $\rightarrow$ Connected $\rightarrow$ Interested $\rightarrow$ Site Visits).
   - Call engagement metrics (Average duration, total minutes, sub-second Sarvam latency).
   - Buyer configuration preferences (1 BHK ₹30L vs 2 BHK ₹45L).
   - Daily pacing trends table.

3. **Site Visit Page (`/sarvam-dashboard/site-visits`)**:
   - Retains exclusively confirmed site visit appointments.
   - **Unmasked Full Phone Numbers**: Displays exact customer mobile numbers (e.g. `+91 98213 61686`).
   - Scheduled visit day and time (e.g., Sunday 4:00 PM).
   - Full conversational transcripts and audio recording players.
   - **Export to PDF & CSV**: Download formatted reports containing full phone numbers, dates, and summaries.

4. **Interested Page (`/sarvam-dashboard/interested`)**:
   - Retains prospects with positive intent (WhatsApp floor plans/brochure requests, budget discussions).
   - Full unmasked phone numbers, audio recordings, and dialogue transcripts.
   - **Export to PDF & CSV** filtered by time period.

5. **Sarvam Webhook Endpoint (`/api/sarvam/webhook`)**:
   - Webhook URL: `https://qualivo.duckdns.org/api/sarvam/webhook`
   - Automatically processes inbound & outbound call completion events from Sarvam AI.
   - Filters and archives **only** high-intent calls (Site Visit & Interested) to keep data clean and actionable.
