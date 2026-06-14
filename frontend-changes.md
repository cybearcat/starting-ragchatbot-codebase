# Testing Framework Enhancement

## Changes Made

### `backend/tests/conftest.py`
- Added `patch` to `unittest.mock` import.
- Added `from fastapi.testclient import TestClient` import.
- Added `_StubStaticFiles` class: a minimal ASGI stub that replaces `StaticFiles` during
  tests. A real subclassable class is required because `app.py` defines
  `class DevStaticFiles(StaticFiles)` — patching with a bare `MagicMock` would raise
  `TypeError` at class-definition time.
- Added `app_module` fixture (session-scoped): patches `RAGSystem` and `StaticFiles` only
  during the `import app` call, then releases the patches. The mock instance is stored on
  `app.rag_system` and shared across all API tests.
- Added `mock_rag` fixture (function-scoped): fully resets the `rag_system` mock between
  tests (including return values and side effects) and re-configures
  `add_course_folder.return_value = (0, 0)` so the startup event never tries to unpack a
  bare `MagicMock`.
- Added `api_client` fixture (function-scoped): creates a `TestClient` context around the
  FastAPI app; lists `mock_rag` first to ensure the mock is configured before the startup
  event fires.

### `backend/tests/test_api_endpoints.py` (new file)
API endpoint tests covering all three routes:

| Endpoint | Test |
|---|---|
| `POST /api/query` | Returns answer + sources in `QueryResponse` shape |
| `POST /api/query` | Creates a new session when none is provided |
| `POST /api/query` | Uses caller-supplied `session_id` without creating a new one |
| `POST /api/query` | Returns HTTP 500 when `rag_system.query` raises |
| `POST /api/query` | Returns HTTP 422 on missing required `query` field |
| `GET /api/courses` | Returns `CourseStats` with total count and titles |
| `GET /api/courses` | Returns HTTP 500 when `get_course_analytics` raises |
| `GET /` | Static route is mounted and reachable (stub returns 200, not 404) |
| `DELETE /api/session/{id}` | Returns `{"status": "ok"}` and calls `delete_session` |

## Design Decisions

- **Patches are released immediately after import** rather than held for the session scope.
  This avoids interfering with `test_rag_system.py` and `test_ai_generator.py`, which
  patch `RAGSystem` independently.
- **`_StubStaticFiles` is a real class** (not `MagicMock`) so that
  `class DevStaticFiles(StaticFiles)` in `app.py` can inherit from it without error.
- **`pytest.ini_options` was already present** in `pyproject.toml` (`pythonpath`,
  `testpaths`) — no changes needed there.
- **`httpx`** was already available as a transitive dependency — no new dev dependency
  required.
