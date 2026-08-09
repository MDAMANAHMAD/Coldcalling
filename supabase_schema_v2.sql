-- Automated AI Cold Calling & CSV Lead Engine Database Schema
-- Version 2.0 (Supabase / PostgreSQL)

-- 1. Create Enums for statuses
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_status') THEN
        CREATE TYPE lead_status AS ENUM ('queued', 'calling', 'interested', 'not_interested', 'callback_required', 'meeting_scheduled', 'failed');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'call_sentiment') THEN
        CREATE TYPE call_sentiment AS ENUM ('positive', 'neutral', 'negative');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'meeting_status') THEN
        CREATE TYPE meeting_status AS ENUM ('confirmed', 'rescheduled', 'cancelled');
    END IF;
END
$$;

-- 2. Leads Table
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    phone TEXT NOT NULL CHECK (phone ~ '^\+[1-9]\d{1,14}$'), -- E.164 verification regex
    email TEXT,
    company TEXT,
    status lead_status DEFAULT 'queued'::lead_status NOT NULL,
    follow_up_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Indexes for fast query sorting
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);

-- 3. Call Logs Table
CREATE TABLE IF NOT EXISTS call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    call_sid TEXT NOT NULL UNIQUE, -- Vapi/Retell Call ID
    duration_seconds INTEGER DEFAULT 0 NOT NULL,
    recording_url TEXT,
    transcript TEXT,
    ai_summary TEXT,
    sentiment call_sentiment DEFAULT 'neutral'::call_sentiment NOT NULL,
    called_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_logs_lead ON call_logs(lead_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_sentiment ON call_logs(sentiment);

-- 4. Meetings Table
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    google_meet_link TEXT NOT NULL,
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status meeting_status DEFAULT 'confirmed'::meeting_status NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meetings_lead ON meetings(lead_id);
CREATE INDEX IF NOT EXISTS idx_meetings_scheduled_time ON meetings(scheduled_time);

-- Enable RLS Policies (Row Level Security)
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;

-- Allow Public/Anon access for development purposes
CREATE POLICY "Public leads access" ON leads FOR ALL USING (true);
CREATE POLICY "Public call_logs access" ON call_logs FOR ALL USING (true);
CREATE POLICY "Public meetings access" ON meetings FOR ALL USING (true);
