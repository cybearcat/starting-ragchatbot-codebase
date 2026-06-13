# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Quick start
chmod +x run.sh && ./run.sh

# Manual start
cd backend
uv run uvicorn app:app --reload --port 8000
```

Requires a `.env` file in the project root:
```
ANTHROPIC_API_KEY=your_key_here
```

App runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

## Dependencies

Managed with `uv`. All deps declared in `pyproject.toml`. Install with:
```bash
uv sync
```

## Architecture

This is a RAG (Retrieval-Augmented Generation) system where course documents are chunked, embedded, and stored in ChromaDB. At query time, Claude uses a tool to search the vector store before generating an answer.

### Key data flow

**Ingestion (on startup):** `app.py` → `rag_system.add_course_folder("../docs/")` → `document_processor.process_course_document()` → `vector_store.add_course_metadata()` + `vector_store.add_course_content()`

**Query:** Browser `POST /api/query` → `rag_system.query()` → `ai_generator.generate_response()` → Claude decides whether to call `search_course_content` tool → `vector_store.search()` (ChromaDB cosine search) → second Claude call to synthesize → response returned with sources

### ChromaDB collections

- `course_catalog` — one document per course (title, instructor, link, lessons JSON). Used for fuzzy course name resolution via semantic search.
- `course_content` — one document per text chunk. Metadata: `course_title`, `lesson_number`, `chunk_index`. IDs: `CourseName_42`.

Embeddings use `all-MiniLM-L6-v2` (sentence-transformers, runs locally). DB persisted at `./chroma_db`.

### Document format expected by the processor

Course files in `docs/` must follow this structure:
```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <title>
Lesson Link: <url>
...lesson text...

Lesson 1: <title>
...
```

Chunks are sentence-based (CHUNK_SIZE=800 chars, CHUNK_OVERLAP=100). The first chunk of each lesson is prefixed with `"Lesson N content: "` to carry context into the embedding.

### Tool use / agentic loop

Claude is given one tool (`search_course_content`) with `tool_choice: auto`. If it fires, `AIGenerator._handle_tool_execution()` runs the tool, appends the result to the message thread, and makes a second API call without tools. `MAX_HISTORY=2` keeps the last 2 exchanges in the system prompt.

### Config

All tunable parameters live in `backend/config.py` as a `Config` dataclass. The active `ANTHROPIC_MODEL` string must be a current model ID — check `/claude-api` for valid IDs before changing it.
