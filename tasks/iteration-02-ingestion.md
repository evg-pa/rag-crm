# Iteration 2 — Paperclip Task

## Goal
Add document ingestion: upload markdown/txt files → parse → chunk → store in PostgreSQL.

## Acceptance Criteria

1. `POST /documents/upload` accepts `.md` and `.txt` files
2. Files are parsed into text, split into chunks (default 512 chars, 128 overlap)
3. Metadata (filename, content_type, size, upload_time) stored in DB
4. Alembic migration creates tables: `documents`, `chunks`
5. `GET /documents` lists all documents with pagination
6. `GET /documents/{id}` returns document + its chunks
7. All tests pass
8. ruff + mypy --strict pass

## Files to Create/Update

### NEW: backend/app/models/__init__.py

### NEW: backend/app/models/document.py
SQLAlchemy model for documents:
- id (UUID, PK)
- filename (str)
- content_type (str)
- size_bytes (int)
- created_at (datetime)
- updated_at (datetime)

### NEW: backend/app/models/chunk.py
SQLAlchemy model for chunks:
- id (UUID, PK)
- document_id (FK → documents.id)
- index (int) — position in document
- content (Text) — chunk text
- metadata (JSONB, nullable)

### UPDATE: backend/app/core/database.py
Add `async def init_db()` — creates all tables (for tests).

### NEW: backend/app/ingestion/__init__.py

### NEW: backend/app/ingestion/parsers/__init__.py

### NEW: backend/app/ingestion/parsers/text_parser.py
- parse .txt files → plain text
- parse .md files → plain text (strip markdown syntax)

### NEW: backend/app/ingestion/chunkers/__init__.py

### NEW: backend/app/ingestion/chunkers/recursive.py
- Recursive chunker: split by paragraphs → sentences → words
- Target chunk size: 512 chars
- Overlap: 128 chars
- Must preserve document order via chunk index

### NEW: backend/app/api/documents.py
Router with:
- `POST /documents/upload` — multipart form upload
- `GET /documents` — list with pagination (page, page_size)
- `GET /documents/{id}` — get document + chunks

### UPDATE: backend/app/api/__init__.py
Add document router.

### UPDATE: backend/app/main.py
Call `init_db()` on startup (for development).

### NEW: alembic migration
```bash
cd backend && alembic init alembic
# Configure alembic/env.py to use async engine
# Create migration: "alembic revision --autogenerate -m 'add documents and chunks'"
```

### UPDATE: backend/pyproject.toml
Add dependency: `python-multipart` (required for FastAPI file uploads).

### NEW: backend/tests/test_documents.py
Tests:
- `test_upload_markdown` — upload .md file, check response
- `test_upload_txt` — upload .txt file, check response
- `test_list_documents` — upload 2 files, list, check pagination
- `test_get_document` — upload, get by id, verify chunks
- `test_upload_empty_file` — edge case

## Constraints
- No LLM calls in Iteration 2 (pure ingestion pipeline)
- Chunks must preserve original order
- pgvector not needed yet (Iteration 3)
- Use UUID for primary keys
- All timestamps in UTC

## Directory
/media/sf_VM_Share/Projects/AI/rag-crm/

## How to coordinate
1. CEO: review, create subtasks
2. Coder(s): implement files
3. QA: test upload .md + .txt, verify DB storage, pytest, ruff, mypy
4. Report results back with commit hash
