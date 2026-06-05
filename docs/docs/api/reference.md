# API Reference

This page documents the REST API exposed by the FastAPI backend (default: `http://localhost:8000`). All routes are proxied through the Node.js BFF (default: `http://localhost:3001`) under the same paths.

The FastAPI interactive docs (Swagger UI) are available at `http://localhost:8000/docs` when the server is running.

---

## Authentication

Routes are protected by JWT bearer tokens. Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

For local development, authentication can be disabled via `AUTH_DISABLED=true` in `backend/.env`.

---

## Comic Generation

### POST /api/generate-comic

Submit a drawing for comic generation. Returns a job ID immediately; generation happens asynchronously.

**Request** (multipart/form-data):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `drawing` | file | Yes | Image file (JPEG, PNG, WebP). Max 5 MB. |
| `child_name` | string | Yes | Child's first name. Used on the comic cover. |
| `age_group` | string | Yes | One of: `4-6`, `7-9`, `10-12` |
| `style` | string | Yes | One of: `adventure`, `fantasy`, `friendship`, `mystery`, `animals`, `space` |

**Response 202 Accepted**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

**Error responses**:

| Status | Condition |
|--------|-----------|
| 400 | Missing or invalid fields |
| 413 | Drawing file exceeds 5 MB |
| 422 | Validation error (e.g. unknown style or age group) |

---

## Job Status

### GET /api/jobs/{job_id}

Poll the status of an in-progress comic generation job.

**Path parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | UUID string | Job ID returned from POST /api/generate-comic |

**Response 200 OK**:

```json
{
  "status": "processing",
  "progress_pct": 45,
  "stage": "storytelling",
  "result_id": null,
  "error": null
}
```

**Status values**:

| Status | Description |
|--------|-------------|
| `queued` | Job is waiting for a Celery worker |
| `processing` | Worker is actively generating the comic |
| `complete` | Comic is ready; `result_id` is populated |
| `failed` | Generation failed; `error` field describes the reason |

**Stage values** (in order):

| Stage | Description |
|-------|-------------|
| `queued` | Waiting in queue |
| `captioning` | BLIP-2 is captioning the drawing |
| `storytelling` | RAG + LLM is generating the story |
| `rendering` | Comic panels are being assembled |
| `safety_check` | Detoxify safety gate is running |

**Response 404 Not Found**: Job ID does not exist.

---

## Comics

### GET /api/comics

List all completed comics in the library.

**Response 200 OK**:

```json
[
  {
    "id": "abc123",
    "child_name": "Lily",
    "cover_title": "Lily and the Magic Forest",
    "created_at": "2026-06-05T14:32:00Z",
    "pages": []
  }
]
```

Note: The `pages` array may be empty in the list response for performance. Use `GET /api/comics/{id}` for the full comic with panels.

---

### GET /api/comics/{comic_id}

Retrieve a complete comic with all pages and panels.

**Path parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `comic_id` | string | Comic ID |

**Response 200 OK** (`ComicSchema`):

```json
{
  "id": "abc123",
  "child_name": "Lily",
  "cover_title": "Lily and the Magic Forest",
  "created_at": "2026-06-05T14:32:00Z",
  "pages": [
    {
      "page_num": 1,
      "layout": "2",
      "panels": [
        {
          "image_bytes_b64": "<base64-encoded PNG>",
          "caption": "A girl in a forest with magical glowing trees",
          "narration": "Lily stepped into the glowing forest, her eyes wide with wonder.",
          "dialogue": "Whoa... it's beautiful!"
        }
      ]
    }
  ]
}
```

**Schema details**:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique comic identifier |
| `child_name` | string | Child's first name |
| `cover_title` | string | AI-generated title for the cover |
| `created_at` | ISO 8601 datetime | UTC timestamp |
| `pages[].page_num` | int | 1-indexed |
| `pages[].layout` | `"1"`, `"2"`, `"3"`, `"4"` | Number of panels in a grid (1=full, 2=side by side, 3=one wide + two, 4=2x2) |
| `panels[].image_bytes_b64` | string | Base64-encoded PNG of the panel image |
| `panels[].caption` | string | AI caption describing the panel content |
| `panels[].narration` | string | Story narration text below the panel |
| `panels[].dialogue` | string or null | Speech bubble text, null if no dialogue |

**Response 404 Not Found**: Comic ID does not exist.

---

## BFF-Only Routes

These routes are handled by the Node.js BFF and do not reach FastAPI.

### GET /api/comics/{comic_id}/export-html

Download a self-contained HTML file of the comic. The file contains all images as inline base64 data URIs and all CSS inline — it renders correctly offline with no external dependencies.

**Response 200 OK**:

- `Content-Type: text/html; charset=utf-8`
- `Content-Disposition: attachment; filename="comic-{comic_id}.html"`

### GET /health

BFF health check. Returns BFF status and whether the FastAPI upstream is reachable.

**Response 200 OK**:

```json
{
  "status": "ok",
  "upstream": true
}
```

`upstream: false` indicates the FastAPI server is not reachable from the BFF.

---

## FastAPI Health

### GET /health

FastAPI application health check.

**Response 200 OK**:

```json
{
  "status": "ok"
}
```
