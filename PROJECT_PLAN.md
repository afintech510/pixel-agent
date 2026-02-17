# Pixel Agent - Project Plan

**Project Type**: Trainable Display Specialist Agent
**Persona**: "Pixel" - Display Specialist at electronics distributor
**Stack**: Docker (PostgreSQL+pgvector, Redis, FastAPI, Streamlit)
**AI**: OpenAI API (gpt-4o-mini for analysis, ada-002 for embeddings)
**Status**: Phase 2 Complete | Phase 3+ Pending

---

## Project Overview

Pixel is a trainable AI agent that analyzes customer/supplier emails about display solutions, extracts technical specifications, generates draft replies, and learns from human corrections via RAG (Retrieval-Augmented Generation) with pgvector.

### Key Features
- **Chat-based email analysis** with 5-block structured output
- **RAG-powered learning** from human corrections (few-shot examples via pgvector)
- **PST import** for bulk seeding of training data
- **Opportunity tracking** (New → RFQ → Samples → Design-in → Production)
- **Supplier knowledge base** (Winstar, Ampire, Tianma, Truly, Sharp, Wisechip, Innolux)
- **Display domain expertise** (brightness, interface, resolution, touch, customization)

---

## Phase Status

### ✅ Phase 1: Infrastructure & Data Pipeline (COMPLETE)

**Completed**: 2026-02-17

#### Deliverables
- [x] Docker Compose multi-service setup (postgres, redis, backend, frontend)
- [x] PostgreSQL schema with pgvector extension
- [x] Core tables: emails, email_insights, parts_recommended, tasks, companies, contacts
- [x] Training tables: training_examples, email_embeddings, feedback_ratings
- [x] Opportunity tracking tables: opportunities, suppliers, part_ledger
- [x] PST parser service (ported from Future_Agent_1, pypff optional)
- [x] PST import API endpoints
- [x] Streamlit PST import UI with training mode
- [x] Database connection management (SQLAlchemy)
- [x] Backend health checks
- [x] Supplier seed data (7 suppliers loaded)

#### Files Created
- `docker-compose.yml` - Multi-container orchestration
- `backend/Dockerfile` - Python 3.11 backend container
- `frontend/Dockerfile` - Streamlit frontend container
- `backend/db/init.sql` - Complete database schema (500+ lines)
- `backend/db/connection.py` - SQLAlchemy connection management
- `backend/config.py` - Pydantic settings with environment variables
- `backend/services/pst_parser.py` - PST parser (pypff optional)
- `backend/api/pst_import.py` - PST import endpoints
- `frontend/app.py` - Streamlit landing page
- `frontend/pages/1_PST_Import.py` - PST import UI (~400 lines)
- `backend/knowledge/display_specialist.md` - Domain knowledge base
- `.env.example` - Environment template

#### Technical Notes
- pypff (PST parser C library) made optional due to Docker build complexity
- PostgreSQL healthcheck takes ~60s during first init
- Docker Compose `version` attribute deprecated but works
- Streamlit `icon` parameter requires single emoji character (not string)

---

### ✅ Phase 2: Chat Interface + RAG Engine (COMPLETE)

**Completed**: 2026-02-17

#### Deliverables
- [x] AI engine with OpenAI structured outputs (Pydantic schemas)
- [x] RAG engine with pgvector similarity search
- [x] Email text parser (extract From/To/Subject/Body from pasted text)
- [x] Chat API endpoints (/chat/analyze, /chat/refine, /chat/feedback, /chat/correction, /chat/history)
- [x] Streamlit Chat UI with 5-block output display
- [x] Frontend navigation updated (Chat page accessible)
- [x] Feedback mechanism (thumbs up/down)
- [x] Correction form for human-in-the-loop training
- [x] Draft reply refinement

#### Files Created
- `backend/prompts.py` - System prompts with Pixel persona, 5-block format, RAG augmentation template
- `backend/services/ai_engine.py` - Ported from Future_Agent_1 with extended schema
- `backend/services/rag_engine.py` - RAG engine (embedding generation, similarity search, prompt augmentation)
- `backend/utils/parsing.py` - Email text parser
- `backend/api/chat.py` - Chat endpoints (6 routes)
- `frontend/pages/2_Chat.py` - Chat interface with 5-block display (~400 lines)

#### 5-Block Analysis Output
1. **Thread Summary** (1-3 bullets)
2. **Key Specs Extracted** (table-like display with explicit/inferred tags)
3. **Risks / Missing Info** (warnings and questions)
4. **Immediate Action Draft** (email reply)
5. **Follow-up Actions** (tasks with owners and due dates)

#### Pydantic Schema Extensions (vs Future_Agent_1)
- `thread_summary_bullets: List[str]` - Bullet point summary
- `key_specs_extracted: List[KeySpec]` - Structured specs with source attribution
- `risks_missing_info: List[str]` - Consolidated risks
- `follow_up_actions: List[FollowUpAction]` - Actions with owner/due date/type
- `opportunity_stage: str` - Lifecycle stage (New | RFQ_Sent | Quotes_Received | etc.)
- `customer_name: str` - Customer company name
- `customer_email: str` - Primary customer email
- `confidence_score: Optional[float]` - 0.0-1.0 confidence

#### RAG Flow
1. User pastes email → backend parses headers
2. Generate embedding (ada-002) for the email
3. Query pgvector for top-K similar training examples
4. Augment system prompt with few-shot examples
5. Call OpenAI for structured analysis
6. Store email + insights + embedding in database
7. Return 5-block analysis to frontend
8. User can correct → stored in `training_examples` for future RAG retrieval

#### API Endpoints
- `POST /chat/analyze` - Analyze single email with RAG augmentation
- `POST /chat/refine` - Refine draft reply with user instructions
- `POST /chat/feedback` - Submit thumbs up/down rating
- `POST /chat/correction` - Submit human correction (stores to training_examples)
- `GET /chat/history` - Get recent analyses (limit + offset pagination)
- `POST /pst/import` - Import PST file
- `POST /pst/training/label` - Label PST emails for training
- `GET /pst/imports` - List import history
- `GET /pst/training/stats` - Training data metrics

---

### 🔲 Phase 3: Feedback Collection & Correction UI (NOT STARTED)

**Status**: Planned

#### Scope
Build a dedicated Training Review page for managing the training dataset and reviewing corrections.

#### Planned Deliverables
- [ ] Training Review page (Streamlit)
- [ ] List view of all training examples with filters (intent, priority, customer, date)
- [ ] Edit/delete training examples
- [ ] Bulk correction import (CSV upload)
- [ ] Training example search (by keyword, customer, specs)
- [ ] Feedback analytics dashboard (positive/negative ratio, common correction types)
- [ ] Embedding regeneration tool (when prompts change)
- [ ] Export training data (JSON/CSV)

#### Files to Create
- `frontend/pages/3_Training_Review.py` - Training management UI
- `backend/api/training.py` - Training data CRUD endpoints
- `frontend/components/training_table.py` - Reusable training data table component

#### Technical Considerations
- Pagination for large training datasets
- Filters: intent, priority, correction_type, date range, customer
- Bulk operations: delete multiple, regenerate embeddings
- Consider adding RAG metrics: precision/recall on corrected examples

---

### 🔲 Phase 4: Opportunity Tracking & Supplier Knowledge UI (NOT STARTED)

**Status**: Planned

#### Scope
Build UI for managing opportunities (lifecycle tracking) and supplier knowledge base.

#### Planned Deliverables
- [ ] Opportunities dashboard (Streamlit)
- [ ] Opportunity lifecycle view (New → RFQ → Samples → Design-in → Production)
- [ ] Kanban-style board or timeline view
- [ ] Link opportunities to emails, parts, customers
- [ ] Supplier knowledge base UI (view/edit supplier profiles)
- [ ] Part ledger view (all recommended parts with attribution)
- [ ] RFQ tracking (sent quotes, follow-up reminders)
- [ ] Sample tracking (shipped samples, evaluation status)

#### Files to Create
- `frontend/pages/4_Opportunities.py` - Opportunity tracking UI
- `frontend/pages/5_Suppliers.py` - Supplier knowledge base UI
- `backend/api/opportunities.py` - Opportunity CRUD endpoints
- `backend/api/suppliers.py` - Supplier CRUD endpoints
- `frontend/components/kanban_board.py` - Kanban component for opportunity stages

#### Database Enhancements
- Add `opportunity_id` foreign key to `emails` table
- Add `stage_history` JSONB column to `opportunities` for timeline
- Add `sample_shipments` table with tracking numbers
- Add `rfq_quotes` table with quote history

#### Technical Considerations
- Real-time updates (WebSocket or polling) for opportunity stage changes
- Drag-and-drop Kanban board (Streamlit limitations - may need custom component)
- Email threading for opportunity context
- Automated reminders for follow-ups (requires background task scheduler)

---

### 🔲 Phase 5: Advanced Features (NOT STARTED)

**Status**: Planned

#### Scope
Polish and advanced capabilities.

#### Planned Deliverables
- [ ] Confidence scoring with uncertainty quantification
- [ ] Multi-email thread analysis (conversation history context)
- [ ] Automated quote generation (integrate pricing data)
- [ ] Email composer skill integration (draft generation in email client)
- [ ] Analytics dashboard (volume trends, response times, win rates)
- [ ] Custom display spec templates (automotive, medical, industrial)
- [ ] Supplier performance tracking (lead time, quality, responsiveness)
- [ ] Admin panel (user management, API key rotation, settings)
- [ ] Export to CRM (Salesforce, HubSpot integration)
- [ ] Webhook triggers for external systems

#### Files to Create
- `frontend/pages/6_Analytics.py` - Analytics dashboard
- `backend/services/confidence_scorer.py` - Confidence scoring logic
- `backend/services/thread_analyzer.py` - Multi-email thread context
- `backend/services/quote_generator.py` - Automated quote generation
- `backend/api/integrations.py` - External integrations (CRM, webhooks)
- `frontend/pages/7_Admin.py` - Admin panel

#### Technical Considerations
- Confidence scoring: Use multiple models or ensemble for uncertainty
- Thread analysis: Store thread_id and parent_message_id in emails table
- Quote generation: Requires pricing database (not yet implemented)
- Email composer integration: Requires Claude Code email-composer skill
- Analytics: Consider using Plotly for interactive charts
- CRM export: OAuth flow for Salesforce/HubSpot

---

## Current Status Summary

### ✅ Working Features (Phases 1-2)
1. **Docker Infrastructure**: 4 healthy containers (postgres, redis, backend, frontend)
2. **Database**: Full schema with pgvector, 7 suppliers seeded
3. **PST Import**: Upload PST files, label emails for training (pypff optional)
4. **Chat Interface**: Paste emails for RAG-augmented analysis
5. **5-Block Output**: Structured analysis with priority, intent, specs, risks, draft, actions
6. **RAG Learning**: Human corrections stored and retrieved via pgvector similarity
7. **Draft Refinement**: Iterative improvement with user instructions
8. **Feedback System**: Thumbs up/down + correction forms

### 🔲 Pending Features (Phases 3-5)
1. **Training Review UI**: Manage and review training dataset
2. **Opportunity Tracking**: Lifecycle management (New → Production)
3. **Supplier Knowledge UI**: Edit supplier profiles and capabilities
4. **Confidence Scoring**: Quantify AI uncertainty
5. **Multi-email Thread Analysis**: Context from full conversation history
6. **Quote Generation**: Automated pricing quotes
7. **Analytics Dashboard**: Volume trends, win rates, response times
8. **CRM Integration**: Export to Salesforce/HubSpot

---

## Technical Stack

### Backend
- **Framework**: FastAPI (async Python web framework)
- **Database**: PostgreSQL 16 + pgvector (vector similarity search)
- **Cache**: Redis 7 (sessions, rate limiting)
- **ORM**: SQLAlchemy 2.0 (async + sync)
- **AI**: OpenAI API
  - `gpt-4o-mini` for email analysis
  - `gpt-4o` for draft refinement
  - `text-embedding-ada-002` for 1536-dim embeddings
- **Validation**: Pydantic 2.0 (structured outputs)
- **PST Parser**: libpff + pypff-python (optional, built from source)

### Frontend
- **Framework**: Streamlit (rapid UI prototyping)
- **HTTP Client**: requests library
- **Pages**: Multi-page app with st.page_link navigation

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Networking**: Named network (pixel-network)
- **Volumes**: Persistent postgres_data volume
- **Health Checks**: PostgreSQL, Redis, backend endpoints

---

## Environment Variables

Required in `.env` file:

```bash
# Database
POSTGRES_DB=pixel_agent
POSTGRES_USER=pixel
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgresql://pixel:your_secure_password@postgres:5432/pixel_agent

# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002

# Redis
REDIS_URL=redis://redis:6379

# Backend
BACKEND_URL=http://backend:8000

# Agent Config
AGENT_NAME=Pixel
AGENT_ROLE=Display Specialist

# RAG Settings
RAG_TOP_K=5
RAG_CONFIDENCE_THRESHOLD=0.7
```

---

## Running the Project

### Start All Services
```bash
cd C:/Users/alark/projects/pixel-agent
docker-compose up -d
```

### Check Health
```bash
curl http://localhost:8000/health
```

### Access Frontend
Open browser to: [http://localhost:8501](http://localhost:8501)

### View Logs
```bash
docker-compose logs -f backend    # Backend logs
docker-compose logs -f frontend   # Frontend logs
docker-compose logs -f postgres   # Database logs
```

### Rebuild After Code Changes
```bash
docker-compose up -d --build backend frontend
```

### Stop All Services
```bash
docker-compose down
```

### Reset Database (WARNING: Deletes all data)
```bash
docker-compose down -v
docker-compose up -d
```

---

## Database Schema

### Core Tables
- `emails` - Raw email data (subject, body, sender, recipients, sent_at, folder_path)
- `email_insights` - AI analysis results (summary, intent, priority, specs, risks, draft)
- `parts_recommended` - Extracted part numbers (customer_provided | recommended)
- `tasks` - Follow-up actions with due dates
- `companies` - Customer/Supplier entities
- `contacts` - Individual contacts at companies
- `email_threads` - Thread hierarchy (parent_message_id)

### Training Tables
- `training_examples` - Human-corrected examples for RAG
- `email_embeddings` - 1536-dim vectors with pgvector ivfflat index
- `feedback_ratings` - Thumbs up/down ratings

### Opportunity Tracking Tables
- `opportunities` - Deal pipeline (stage, eau, target_price, close_date)
- `suppliers` - Supplier knowledge base (name, specialties, lead_time, contact)
- `part_ledger` - Recommended parts attribution (part_number, supplier_id, recommended_at)

### Indexes
- `idx_emails_processed` on `emails(processed_by_ai)`
- `idx_emails_folder` on `emails(folder_path)`
- `idx_email_insights_priority` on `email_insights(priority)`
- `idx_email_insights_intent` on `email_insights(intent)`
- `idx_parts_email` on `parts_recommended(email_id)`
- `idx_tasks_status` on `tasks(status)`
- `idx_training_email` on `training_examples(email_id)`
- `email_embeddings_embedding_idx` (ivfflat) on `email_embeddings USING ivfflat (embedding vector_cosine_ops)`

---

## Known Issues & Limitations

### Phase 1-2 Issues
1. **pypff Docker build**: Complex C library build in Docker. Currently optional with try/except import.
   - **Workaround**: PST import shows clear error if pypff unavailable. Can use dedicated Dockerfile.Pypff or alternative PST parser.

2. **Streamlit emoji icons**: `st.page_link()` icon parameter requires single emoji character, not strings or shortcodes.
   - **Fixed**: Removed icon parameters from page links.

3. **Docker Compose version warning**: `version` attribute deprecated.
   - **Impact**: Warning only, no functional issue.

4. **PostgreSQL slow healthcheck**: First init takes ~60s for schema + seed data.
   - **Impact**: Backend waits for DB healthy status before starting.

5. **OpenAI API key required**: Analysis will fail with 503 if key not configured.
   - **Workaround**: Clear error message prompts user to set OPENAI_API_KEY in .env.

6. **No authentication**: Current implementation has no user auth or API keys.
   - **Impact**: Anyone with network access can use the agent.
   - **Future**: Add user management in Phase 5.

### Pending Limitations
- No multi-user support (single shared agent)
- No email threading context (analyzes emails in isolation)
- No automated follow-up reminders
- No pricing database (cannot generate quotes)
- No CRM integration yet
- No confidence scoring (raw model output)
- No rate limiting on API endpoints
- No audit log for corrections

---

## Development Workflow

### Adding New Features
1. Plan the feature (endpoints, UI, database changes)
2. Update database schema if needed (`backend/db/init.sql`)
3. Create backend services/endpoints (`backend/services/`, `backend/api/`)
4. Create frontend pages/components (`frontend/pages/`, `frontend/components/`)
5. Register routers in `backend/main.py`
6. Add page links in `frontend/app.py`
7. Rebuild containers: `docker-compose up -d --build backend frontend`
8. Test end-to-end
9. Update this plan file with progress

### Testing RAG Learning
1. Go to Chat page
2. Paste a test email
3. Review analysis output
4. Click "Needs Correction"
5. Submit corrections in the form
6. Paste similar email again
7. Verify RAG augmentation (should show "RAG: Used N training examples")
8. Analysis should improve based on corrections

### Model Strategy
- **Phases 1, 3-4**: Use Sonnet (standard coding, CRUD, UI)
- **Phases 2, 5**: Use Opus (complex AI architecture, RAG design, confidence scoring)

---

## Next Steps for Continuation

### Immediate Next Phase: Phase 3
To continue development, the next agent should:

1. **Create Training Review UI** (`frontend/pages/3_Training_Review.py`)
   - List all training examples with filters
   - Edit/delete functionality
   - Search by keyword, customer, intent, priority
   - Feedback analytics (positive/negative ratio)

2. **Create Training API** (`backend/api/training.py`)
   - GET /training/examples (list with pagination + filters)
   - GET /training/examples/:id (single example)
   - PUT /training/examples/:id (update)
   - DELETE /training/examples/:id (delete)
   - POST /training/regenerate-embeddings (bulk regenerate)
   - GET /training/analytics (feedback stats, correction types)

3. **Update Frontend Navigation**
   - Add "Training Review" page link in `frontend/app.py`
   - Remove "Coming Soon" label

4. **Test End-to-End**
   - Create training examples via Chat corrections
   - View them in Training Review page
   - Edit an example
   - Verify RAG retrieval uses updated example

### Reference Files for Next Agent
- **Current plan**: `C:\Users\alark\projects\pixel-agent\PROJECT_PLAN.md` (this file)
- **Original detailed plan**: `C:\Users\alark\.claude\plans\declarative-sparking-lampson.md`
- **Memory file**: `C:\Users\alark\.claude\projects\C--Users-alark\memory\MEMORY.md`
- **Database schema**: `C:\Users\alark\projects\pixel-agent\backend\db\init.sql`
- **AI engine**: `C:\Users\alark\projects\pixel-agent\backend\services\ai_engine.py`
- **RAG engine**: `C:\Users\alark\projects\pixel-agent\backend\services\rag_engine.py`

---

## Project Links

- **Project Directory**: `C:\Users\alark\projects\pixel-agent\`
- **Frontend URL**: [http://localhost:8501](http://localhost:8501)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Original Plan**: `C:\Users\alark\.claude\plans\declarative-sparking-lampson.md`

---

**Last Updated**: 2026-02-17
**Phases Complete**: 2/5 (Phase 1: Infrastructure, Phase 2: Chat + RAG)
**Phases Remaining**: 3/5 (Phase 3: Training Review, Phase 4: Opportunities, Phase 5: Advanced)
