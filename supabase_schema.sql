-- Database schema for Automated Business Operations CRM
-- Serves Sales, Founder Productivity, Support, and Admin tools

-- 1. Profiles / Users Table
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY,
  full_name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT DEFAULT 'founder' CHECK (role IN ('founder', 'sales_rep', 'support_agent')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Enable RLS for Profiles
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- 2. Sales Leads Table
CREATE TABLE IF NOT EXISTS leads (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  phone TEXT,
  email TEXT,
  status TEXT DEFAULT 'New' CHECK (status IN ('New', 'Called', 'Interested', 'Not Interested', 'Callback Needed')),
  follow_up_date TIMESTAMP WITH TIME ZONE,
  notes TEXT,
  last_call_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

-- 3. Sales Campaigns Table
CREATE TABLE IF NOT EXISTS campaigns (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  template TEXT NOT NULL,
  sequence_rules JSONB DEFAULT '{"delayDays": 1, "maxFollowUps": 3}'::jsonb,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;

-- 4. Classified Emails Table
CREATE TABLE IF NOT EXISTS classified_emails (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  sender TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  category TEXT DEFAULT 'Other' CHECK (category IN ('Urgent', 'VC', 'Other', 'Spam', 'Trash')),
  actionable_link TEXT,
  received_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE classified_emails ENABLE ROW LEVEL SECURITY;

-- 5. Support Tickets Table
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, -- format #TCK-XXXX
  customer_name TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  issue_description TEXT NOT NULL,
  chatbot_history JSONB DEFAULT '[]'::jsonb,
  status TEXT DEFAULT 'Pending' CHECK (status IN ('Pending', 'In Progress', 'Resolved')),
  agent_notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;

-- 6. Invoices Table
CREATE TABLE IF NOT EXISTS invoices (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  invoice_number TEXT NOT NULL UNIQUE,
  client_name TEXT NOT NULL,
  client_email TEXT,
  items JSONB NOT NULL, -- array of { id, description, qty, unitPrice }
  tax_rate NUMERIC DEFAULT 0.0,
  total NUMERIC NOT NULL,
  status TEXT DEFAULT 'Unpaid' CHECK (status IN ('Unpaid', 'Paid', 'Overdue')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

-- Create basic public read policies for demo purposes
CREATE POLICY "Public Read Access for Leads" ON leads FOR SELECT USING (true);
CREATE POLICY "Public Write Access for Leads" ON leads FOR ALL USING (true);
CREATE POLICY "Public Read Access for Campaigns" ON campaigns FOR SELECT USING (true);
CREATE POLICY "Public Write Access for Campaigns" ON campaigns FOR ALL USING (true);
CREATE POLICY "Public Read Access for Emails" ON classified_emails FOR SELECT USING (true);
CREATE POLICY "Public Write Access for Emails" ON classified_emails FOR ALL USING (true);
CREATE POLICY "Public Read Access for Tickets" ON tickets FOR SELECT USING (true);
CREATE POLICY "Public Write Access for Tickets" ON tickets FOR ALL USING (true);
CREATE POLICY "Public Read Access for Invoices" ON invoices FOR SELECT USING (true);
CREATE POLICY "Public Write Access for Invoices" ON invoices FOR ALL USING (true);
