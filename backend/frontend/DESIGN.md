# Iteration 11: Streamlit Frontend — UI Design

> Design brief for the RAG-CRM document management frontend.
> Inspired by Perplexity, NotebookLM, Linear, and ChatGPT Retrieval.

## Overview

A Streamlit multi-page app that replaces curl-based interaction with a polished, desktop-first UI. Three core user workflows: **Document Management**, **Q&A (chat-style)**, and **Knowledge Browsing**.

## Tech Stack

- **Streamlit** ≥1.40 (multi-page via `st.navigation`)
- **httpx** (async HTTP client to backend)
- **streamlit-option-menu** (sidebar navigation with icons)
- **plotly** (dashboard charts, optional)
- **pillow** (if needed for image handling)
- Python 3.12+

## Pages & Layout

### Global Layout

```
┌─────────────────────────────────────────────┐
│  [☰] 📄 RAG-CRM                🌙 Theme    │  ← Top bar
├──────────┬──────────────────────────────────┤
│          │                                  │
│  📊 Dash │                                  │
│  📄 Docs │    Main Content Area              │
│  💬 Q&A  │                                  │
│  🔍 Search│                                  │
│  📚 Wiki │                                  │
│  ⚙️ Pipe │                                  │
│          │                                  │
├──────────┴──────────────────────────────────┤
│  Status: All systems healthy                │  ← Footer bar
└─────────────────────────────────────────────┘
```

- **Sidebar** — Narrow (250px), icons + labels, active state highlighted
- **Top bar** — App logo/name, theme toggle (dark/light), connection status
- **Footer bar** — System health, database connection indicator
- **Main area** — Content fills remaining space

### Page 1: Dashboard

**Endpoint:** `GET /health`, `GET /documents`, `GET /pipeline/status`

**Layout:**
```
┌─────────────────────────────────────────────┐
│ 📊 Dashboard                                 │
│                                              │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│ │ 42   │ │ 156  │ │ 3.2K │ │ Live │        │  ← KPI cards
│ │ Docs  │ │Chunks│ │Q&A   │ │Status│        │
│ └──────┘ └──────┘ └──────┘ └──────┘        │
│                                              │
│ Recent Documents          Pipeline Status    │  ← Two columns
│ ┌─────────────────┐      ┌──────────────┐   │
│ │ report.pdf  ⏱2m │      │ Router:  ✅  │   │
│ │ notes.docx ⏱5m │      │ Retriever:✅  │   │
│ │ page.html  ⏱1h │      │ Reranker: ✅  │   │
│ └─────────────────┘      │ Critic:   ✅  │   │
│                          └──────────────┘   │
└─────────────────────────────────────────────┘
```

**Key metrics cards** (4 columns):
- Total documents count
- Total chunks count
- Total Q&A queries (from history)
- System status (green 🟢 / yellow 🟡 / red 🔴)

**Two-column bottom:**
- Left: Recent 5 documents (filename, content-type icon, upload time ago)
- Right: Pipeline agent status (from `/pipeline/status`), each agent with green/yellow/red dot

### Page 2: Documents

**Endpoints:** `POST /documents/upload`, `POST /documents/scrape`, `GET /documents`, `GET /documents/supported`

**Layout — Upload section (top):**
```
┌─────────────────────────────────────────────┐
│ 📄 Documents                                 │
│                                              │
│ ┌─ Upload ──────────────────────────────┐   │
│ │                                       │   │
│ │        📁 Drag & drop files here      │   │  ← st.file_uploader (full width)
│ │        or click to browse             │   │
│ │   Supported: .pdf .docx .html .txt.md │   │
│ └───────────────────────────────────────┘   │
│                                              │
│ Or paste a URL to scrape:                    │
│ ┌─────────────────────┐ [🌐 Scrape]         │  ← URL input + button
│ └─────────────────────┘                     │
│                                              │
│ ──── All Documents ──────────────────────────│
│                                              │
│ [🔍 Search docs...]        [.pdf▼] [Sort▼]  │  ← Filter bar
│                                              │
│ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐         │
│ │📄  │ │📄  │ │📄  │ │📄  │ │📄  │         │  ← Document cards grid
│ │Rep │ │Not │ │Read│ │API │ │Sec │         │
│ │ort │ │es  │ │me  │ │Doc │ │ond │         │
│ └────┘ └────┘ └────┘ └────┘ └────┘         │
│                                              │
└─────────────────────────────────────────────┘
```

**Document card design:**
```
┌──────────────────────┐
│ 📄                   │  ← Content-type icon
│ report.pdf           │  ← Filename
│ 2.4 MB · 5 chunks    │  ← Size + chunks
│ 10 min ago           │  ← Upload time
│ 🗑️  🔍               │  ← Delete + view actions
└──────────────────────┘
```

**Document detail (expandable section or modal):**
When clicking a document card:
- Title bar with filename, content-type, file size
- Metadata section (author, page count, dates — if available)
- Chunks list with index and content preview
- Search within document button
- Delete confirmation dialog

**Drag & drop:** Use `st.file_uploader` with `accept_multiple_files=True` and visual styling for drag-over state via custom CSS.

### Page 3: Q&A Chat (⭐ Primary Feature)

**Endpoint:** `POST /qa`, `GET /qa/history`

**Layout — Inspired by ChatGPT / Perplexity:**
```
┌─────────────────────────────────────────────┐
│ 💬 Q&A — Ask your documents                 │
│                                              │
│ ┌──────────────────────────────────────┐    │
│ │                                      │    │
│ │  👤 You (13:42)                      │    │
│ │  ┌──────────────────────────────┐    │    │
│ │  │ What were the Q3 revenue     │    │    │
│ │  │ projections for the CRM?     │    │    │
│ │  └──────────────────────────────┘    │    │
│ │                                      │    │
│ │  🤖 Assistant (13:43)                │    │
│ │  ┌──────────────────────────────┐    │    │
│ │  │ Based on the Q3 planning     │    │    │
│ │  │ document, the CRM revenue    │    │    │
│ │  │ projection was $2.4M...     │    │    │
│ │  │                              │    │    │
│ │  │ 📚 Sources:                  │    │    │
│ │  │  [1] Q3_planning.pdf — p.12  │    │    │  ← Source citations
│ │  │  [2] board_notes.docx — p.5  │    │    │     (expandable)
│ │  └──────────────────────────────┘    │    │
│ │                                      │    │
│ │  [💬 Ask a question...       ] [➤]  │    │  ← Chat input
│ └──────────────────────────────────────┘    │
│                                              │
│ [🗑️ Clear conversation]  [📋 Copy last]    │  ← Utility buttons
│                                              │
└─────────────────────────────────────────────┘
```

**Key features:**
- Chat message history with `st.chat_message`
- User messages right-aligned (or styled differently)
- Assistant messages with:
  - Answer text (markdown rendered)
  - Expandable "Sources" section showing citations with document names and page numbers
  - Copy answer button
- Chat input at bottom with send button
- Loading spinner / streaming indicator while generating
- "Clear conversation" resets session state + backend history
- `top_k` slider in sidebar (hidden at bottom, default 5)

**Session state:**
```python
st.session_state.messages = []  # list of {"role", "content", "sources"}
st.session_state.history_loaded = False
```

### Page 4: Search

**Endpoint:** `GET /search`

**Layout:**
```
┌─────────────────────────────────────────────┐
│ 🔍 Search                                    │
│                                              │
│ 🔎 [Search your documents...       ] [🔍]   │  ← Prominent search bar
│                                              │
│ Results (12 found)  Hybrid search            │  ← Result count + mode label
│                                              │
│ ┌─────────────────────────────────────────┐  │
│ │ 📄 report.pdf · chunk #3               │  │  ← Result card
│ │ 0.87 · "The revenue projections for    │  │     (relevance score)
│ │ Q3 indicate a growth of 15%..."        │  │
│ │ ─────────────────────────────────────  │  │
│ │ [👁️ View document] [📋 Copy excerpt]   │  │  ← Actions
│ └─────────────────────────────────────────┘  │
│                                              │
│ ┌─────────────────────────────────────────┐  │
│ │ 📄 board_notes.docx · chunk #1         │  │
│ │ 0.72 · "CRM strategy focuses on..."    │  │
│ │ ...                                     │  │
│ └─────────────────────────────────────────┘  │
│                                              │
│ [← Prev] Page 1 of 3 [Next →]               │  ← Pagination
└─────────────────────────────────────────────┘
```

**Features:**
- Real-time search as you type (debounced, optional)
- Result cards with: document icon, filename, chunk index, relevance score (colored bar), excerpt with highlighted query terms
- Click result → expand full chunk content
- "View document" → navigates to document detail
- Top-K slider in sidebar
- Pagination (10 per page)
- Loading spinner during search

### Page 5: Wiki / Knowledge Base

**Endpoint:** `GET /wiki`, `GET /wiki/{id}`, `GET /wiki/search?q=`

**Layout:**
```
┌─────────────────────────────────────────────┐
│ 📚 Knowledge Base                            │
│                                              │
│ 🔎 [Search wiki entries...        ] [🔍]    │  ← Search bar
│                                              │
│ ┌─────────────────────────────────────────┐  │
│ │ 📋 Q3 Revenue Planning                  │  │  ← Wiki entry card
│ │ Generated from: Q3_planning.pdf         │  │
│ │ Updated: 2 hours ago                    │  │
│ │ ─────────────────────────────────────  │  │
│ │ The Q3 revenue plan covers... [more]   │  │  ← Summary preview
│ └─────────────────────────────────────────┘  │
│                                              │
│ ┌─────────────────────────────────────────┐  │
│ │ 📋 CRM Strategy Overview                │  │
│ │ ...                                      │  │
│ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**Features:**
- Click entry → expand full wiki markdown content
- Search filters entries in real-time
- Each card shows: source document name, auto-generated summary first 200 chars, last updated time
- Refresh button to regenerate from latest documents

### Page 6: Pipeline Dashboard

**Endpoint:** `GET /pipeline/status`

**Layout:**
```
┌─────────────────────────────────────────────┐
│ ⚙️ Pipeline Dashboard                        │
│                                              │
│ LangGraph Agent Pipeline                     │
│ ┌─────────────────────────────────────────┐  │
│ │               Query Flow                │  │
│ │                                         │  │
│ │  🟢 Router → 🟢 Retriever → 🟢 Reranker│  │  ← Agent flow diagram
│ │             ↓                           │  │
│ │        🟢 Answer → 🟢 Critic            │  │
│ │             ↓           ↓ (retry→↑)     │  │
│ │        🟢 Memory → 🟢 Synthesizer       │  │
│ └─────────────────────────────────────────┘  │
│                                              │
│ Agent Details:                               │
│ ┌──────────────┬─────────┬───────┬────────┐  │
│ │ Agent        │ Status  │ Lat  │ Calls  │  │  ← Agent stats table
│ ├──────────────┼─────────┼───────┼────────┤  │
│ │ Router       │ ✅ idle │ 45ms  │ 128    │  │
│ │ Retriever    │ ✅ idle │ 120ms │ 128    │  │
│ │ Reranker     │ ✅ idle │ 80ms  │ 96     │  │
│ │ Answer       │ ✅ idle │ 2.4s  │ 128    │  │
│ │ Critic       │ ✅ idle │ 1.1s  │ 110    │  │
│ │ Memory       │ ✅ idle │ 30ms  │ 128    │  │
│ │ Synthesizer  │ ✅ idle │ 50ms  │ 128    │  │
│ └──────────────┴─────────┴───────┴────────┘  │
└─────────────────────────────────────────────┘
```

**Features:**
- Visual agent flow diagram (using st.graphviz_chart or HTML/CSS flow boxes)
- Agent table with: name, status (colored dot), average latency, total calls
- Auto-refresh every 10s via `st.autorefresh`
- Animated spinner on currently active agent during a query

## Visual Design

### Color Palette

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--bg-primary` | `#FFFFFF` | `#0E1117` | Main background |
| `--bg-secondary` | `#F5F5F5` | `#1A1C23` | Sidebar, cards |
| `--bg-tertiary` | `#EBEBEB` | `#262730` | Inputs, hover states |
| `--text-primary` | `#1A1A2E` | `#E0E0E0` | Body text |
| `--text-secondary` | `#666680` | `#9E9EB0` | Captions, metadata |
| `--accent` | `#4F46E5` | `#7C73FF` | Primary buttons, links |
| `--accent-hover` | `#4338CA` | `#6D63F0` | Button hover |
| `--success` | `#10B981` | `#34D399` | Status OK |
| `--warning` | `#F59E0B` | `#FBBF24` | Warnings |
| `--error` | `#EF4444` | `#F87171` | Errors |
| `--border` | `#E5E7EB` | `#333540` | Card borders |

### Typography

- Font: system-ui, -apple-system, sans-serif (native feel)
- Headings: `st.markdown` with `##` (configurable in custom CSS)
- Code: monospace for inline and blocks
- Chat messages: 16px body, 14px metadata

### Component Design Guidelines

**Cards:**
- Subtle border, rounded corners (12px), padding 16px
- Hover: slight shadow lift (transition 0.2s)
- Content-type icon as emoji: 📄 PDF, 📝 DOCX, 🌐 HTML, 📄 MD/TXT
- Document cards in responsive grid (3-4 columns on desktop, 2 on tablet, 1 on mobile)

**Buttons:**
- Primary: accent background, white text, rounded (8px), padding 8px 16px
- Secondary/ghost: transparent, border, accent text on hover
- Danger: red tint

**Chat messages:**
- User: right-aligned, accent background bubble, white text
- Assistant: left-aligned, secondary background bubble
- Sources: collapsible `<details>` tag, smaller text, subtle background

**Status indicators:**
- Green dot: 🟢 healthy/ready
- Yellow dot: 🟡 loading/pending
- Red dot: 🔴 error
- Spinner for in-progress operations

## File Structure

```
frontend/
├── requirements.txt           # streamlit, httpx, etc.
├── Dockerfile                 # streamlit Docker (separate from backend)
├── app.py                     # Entry point — st.navigation
├── pages/
│   ├── dashboard.py           # Page 1
│   ├── documents.py           # Page 2
│   ├── qa_chat.py             # Page 3
│   ├── search.py              # Page 4
│   ├── wiki.py                # Page 5
│   └── pipeline.py            # Page 6
├── components/
│   ├── __init__.py
│   ├── sidebar.py             # Sidebar navigation
│   ├── document_card.py       # Document card component
│   ├── chat_message.py        # Chat bubble component
│   ├── search_result.py       # Search result card
│   ├── kpi_card.py            # Dashboard metric card
│   └── pipeline_diagram.py    # Pipeline flow diagram
├── utils/
│   ├── __init__.py
│   ├── api.py                 # httpx async client to backend
│   ├── state.py               # Session state management
│   └── theme.py               # Dark/light theme CSS
└── static/
    └── style.css              # Global custom styles
```

## API Client (`utils/api.py`)

```python
import httpx
import streamlit as st

BASE_URL = "http://backend:8000"  # Docker Compose DNS

@st.cache_resource
def get_client():
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

async def health_check() -> dict:
    client = get_client()
    r = await client.get("/health")
    return r.json()

async def list_documents() -> list[dict]:
    client = get_client()
    r = await client.get("/documents")
    return r.json()

async def upload_document(file_bytes: bytes, filename: str) -> dict:
    client = get_client()
    r = await client.post("/documents/upload", files={"file": (filename, file_bytes)})
    return r.json()

async def scrape_url(url: str) -> dict:
    client = get_client()
    r = await client.post("/documents/scrape", json={"url": url})
    return r.json()

async def ask_question(query: str, top_k: int = 5) -> dict:
    client = get_client()
    r = await client.post("/qa", json={"query": query, "top_k": top_k})
    return r.json()

async def search(query: str, top_k: int = 10) -> dict:
    client = get_client()
    r = await client.get("/search", params={"q": query, "top_k": top_k})
    return r.json()

# ... etc for wiki, pipeline, memory endpoints
```

## Session State (`utils/state.py`)

```python
import streamlit as st

def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "messages": [],
        "history_loaded": False,
        "theme": "dark",
        "documents_cache": None,
        "wiki_cache": None,
        "pipeline_status": None,
        "last_search_query": "",
        "current_page": "dashboard",
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
```

## Implementation Order (for CEO delegation)

1. **Setup** — `requirements.txt`, `Dockerfile`, `app.py` entry point with st.navigation, theme toggle
2. **API client + session state** — `utils/api.py`, `utils/state.py`, `utils/theme.py`
3. **Sidebar** — `components/sidebar.py` with navigation menu
4. **Dashboard page** — KPI cards, recent docs, pipeline status summary
5. **Documents page** — Upload (drag & drop), URL scrape, document grid, document detail
6. **Q&A Chat page** — Chat interface, message history, source citations, streaming indicator
7. **Search page** — Search bar, result cards, pagination, excerpt highlighting
8. **Wiki page** — Entry cards, search, expand/collapse content
9. **Pipeline page** — Agent flow diagram, stats table, auto-refresh
10. **Docker integration** — Wire into `infrastructure/docker-compose.yml`, health check
