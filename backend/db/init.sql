-- Pixel Agent Database Schema
-- PostgreSQL 16 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- CORE TABLES (ported from Future_Agent_1)
-- ============================================================

-- Imports table: Tracks every PST upload session
CREATE TABLE IF NOT EXISTS imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending | processing | completed | failed
    emails_processed INTEGER DEFAULT 0,
    emails_skipped INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

-- Companies table
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    domain TEXT UNIQUE,
    type TEXT DEFAULT 'Unclassified',  -- Customer | Supplier | Unclassified
    industry TEXT,
    classification_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts table (was missing from Future_Agent_1 schema)
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    company_id UUID REFERENCES companies(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Email threads (was missing from Future_Agent_1 schema)
CREATE TABLE IF NOT EXISTS email_threads (
    id TEXT PRIMARY KEY,
    subject TEXT,
    related_company_id UUID REFERENCES companies(id),
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Emails table
CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_id UUID REFERENCES imports(id),
    message_id TEXT,
    dedupe_hash TEXT UNIQUE NOT NULL,
    thread_id TEXT REFERENCES email_threads(id),
    references_header TEXT,
    sender_email TEXT,
    from_name TEXT,
    recipient_emails TEXT[],
    cc_emails TEXT[],
    subject TEXT,
    body TEXT,
    html_body TEXT,
    sent_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    timestamp_missing BOOLEAN DEFAULT FALSE,
    folder_path TEXT,
    attachments JSONB,
    transport_headers JSONB,
    processed_by_ai BOOLEAN DEFAULT FALSE,
    related_company_id UUID REFERENCES companies(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Email Insights: AI analysis results
CREATE TABLE IF NOT EXISTS email_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id) UNIQUE,
    summary TEXT,
    intent TEXT,
    priority TEXT,
    priority_reason TEXT,
    quote_intent BOOLEAN DEFAULT FALSE,
    quote_fields JSONB,
    technical_analysis TEXT,
    technical_specs TEXT[],
    technical_risks TEXT[],
    suggested_actions TEXT[],
    missing_info_questions TEXT[],
    draft_reply TEXT,
    eau TEXT,
    target_price TEXT,
    brightness_nits TEXT,
    interface TEXT,
    resolution TEXT,
    customization_notes TEXT,
    -- New fields for Pixel 5-block output
    thread_summary_bullets TEXT[],
    risks_missing_info TEXT[],
    follow_up_actions JSONB,  -- [{action, owner, due_date, type}]
    opportunity_stage TEXT,
    customer_name TEXT,
    customer_email TEXT,
    sales_team_emails TEXT[],
    company_classification TEXT,
    confidence_score DECIMAL(3, 2),
    raw_ai_output JSONB,
    model_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Parts Recommended
CREATE TABLE IF NOT EXISTS parts_recommended (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id),
    part_number TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- customer_provided | recommended
    description TEXT,
    quantity INTEGER,
    where_found TEXT,
    evidence_snippet TEXT,
    recommended_at TIMESTAMPTZ,
    attribution_status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email_id, part_number, source_type)
);

-- Tasks: follow-ups and commitments
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id),
    company_name TEXT,
    fsp_name TEXT,
    task_type TEXT,  -- follow_up | waiting_on_client
    description TEXT,
    due_date DATE,
    status TEXT DEFAULT 'pending',  -- pending | completed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- NEW TABLES: Training & Feedback
-- ============================================================

-- Human-corrected training examples for RAG
CREATE TABLE IF NOT EXISTS training_examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id),
    original_email_text TEXT NOT NULL,
    original_ai_output JSONB NOT NULL,
    corrected_output JSONB NOT NULL,
    correction_type TEXT,  -- priority | parts | draft | summary | full
    corrected_by TEXT,
    confidence_before DECIMAL(3, 2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector embeddings for RAG retrieval
CREATE TABLE IF NOT EXISTS email_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id) UNIQUE,
    embedding vector(1536),  -- OpenAI text-embedding-ada-002 dimension
    metadata JSONB,          -- {intent, priority, customer_name} for filtering
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Quick feedback ratings
CREATE TABLE IF NOT EXISTS feedback_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id),
    rating TEXT NOT NULL,  -- positive | negative
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- NEW TABLES: Opportunity Tracking (from MD file)
-- ============================================================

-- Opportunities: Full lifecycle tracking
CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_name TEXT NOT NULL,
    program_name TEXT,
    internal_owner TEXT,
    customer_contacts JSONB,  -- [{name, email, role}]
    status TEXT DEFAULT 'New',  -- New|RFQ_Sent|Quotes_Received|Proposed|Samples_Requested|Samples_Shipped|Evaluating|Design_In|Production
    triage_score TEXT DEFAULT 'Warm',  -- Hot|Warm|Cold
    target_specs JSONB,        -- Structured display specs
    recommended_pns JSONB,     -- [{pn, supplier, interface, touch, brightness, notes}]
    quote_records JSONB,       -- [{supplier_quote_id, date, pricing_breaks, leadtime, moq, tooling}]
    risks JSONB,
    next_actions TEXT[],
    next_followup_date DATE,
    tags TEXT[],               -- #NEW_INQUIRY, #RFQ_REQUIRED, #WAITING_ON_SUPPLIER, etc.
    attachments_links TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Supplier knowledge base
CREATE TABLE IF NOT EXISTS suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    website TEXT,
    product_lines TEXT[],
    interfaces_supported TEXT[],     -- RGB, LVDS, MIPI, eDP, MCU, SPI
    touch_options TEXT[],            -- PCAP, RTP, Glass, Controller brands
    optical_bonding_capability BOOLEAN DEFAULT FALSE,
    brightness_range_min_nits INTEGER,
    brightness_range_max_nits INTEGER,
    temperature_grades TEXT[],
    standard_sizes TEXT[],
    customization_options TEXT[],
    part_number_format_notes TEXT,
    known_leadtime_pattern TEXT,
    key_contacts JSONB,              -- Internal-only contact info
    notes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Part number ledger (global tracking)
CREATE TABLE IF NOT EXISTS part_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_number TEXT NOT NULL,
    supplier TEXT,
    customers TEXT[],
    internal_owners TEXT[],
    first_recommended_date DATE,
    last_activity_date DATE,
    current_stage TEXT,
    datasheet_link TEXT,
    datasheet_revision_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat sessions (conversation history)
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    conversation_history JSONB,  -- [{role, content, timestamp}]
    current_email_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_emails_thread_id ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
CREATE INDEX IF NOT EXISTS idx_emails_dedupe_hash ON emails(dedupe_hash);
CREATE INDEX IF NOT EXISTS idx_emails_processed_by_ai ON emails(processed_by_ai);
CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON emails(sent_at);
CREATE INDEX IF NOT EXISTS idx_parts_composite ON parts_recommended(email_id, part_number, source_type);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_training_created ON training_examples(created_at);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_customer ON opportunities(customer_name);
CREATE INDEX IF NOT EXISTS idx_part_ledger_pn ON part_ledger(part_number);

-- pgvector index for similarity search
CREATE INDEX IF NOT EXISTS idx_email_embeddings_vector
    ON email_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================
-- SEED DATA: Known Suppliers (from MD file)
-- ============================================================

INSERT INTO suppliers (name, website, product_lines, interfaces_supported, touch_options, optical_bonding_capability, customization_options)
VALUES
    ('Winstar', 'https://www.winstar.com.tw', ARRAY['TFT LCD', 'OLED', 'Character LCD'], ARRAY['RGB', 'LVDS', 'MIPI', 'MCU', 'SPI'], ARRAY['PCAP', 'RTP'], FALSE, ARRAY['FPC', 'Cover Glass', 'Firmware']),
    ('Ampire', 'https://www.ampire.com.tw', ARRAY['Industrial TFT'], ARRAY['RGB', 'LVDS', 'MIPI'], ARRAY['PCAP'], FALSE, ARRAY['FPC', 'Cover Glass']),
    ('Tianma', 'https://www.tianma.com', ARRAY['TFT Modules', 'TFT Panels'], ARRAY['RGB', 'LVDS', 'MIPI', 'eDP'], ARRAY['PCAP'], TRUE, ARRAY['FPC', 'Cover Glass', 'Optical Bonding']),
    ('Truly', 'https://www.truly.com.cn', ARRAY['TFT Modules'], ARRAY['RGB', 'LVDS', 'MIPI'], ARRAY['PCAP', 'RTP'], FALSE, ARRAY['FPC', 'Customization']),
    ('Sharp', 'https://www.sharpsde.com', ARRAY['LCD Modules', 'LCD Panels'], ARRAY['LVDS', 'MIPI', 'eDP'], NULL, FALSE, NULL),
    ('Wisechip', 'https://www.wisechip.com', ARRAY['OLED Modules'], ARRAY['SPI', 'I2C', 'MCU'], NULL, FALSE, NULL),
    ('Innolux', 'https://www.innolux.com', ARRAY['TFT Modules', 'TFT Panels'], ARRAY['RGB', 'LVDS', 'MIPI', 'eDP'], ARRAY['PCAP'], TRUE, ARRAY['FPC', 'Optical Bonding'])
ON CONFLICT (name) DO NOTHING;
