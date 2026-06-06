# Runbook: Add a New Style to the RAG Library

**Purpose**: Add a new comic narrative style to the ChromaDB vector store so the storytelling pipeline can retrieve style-appropriate exemplars for that style.

**Prerequisites**:
- Docker Compose stack running (`docker compose up -d`)
- Python environment active (`cd backend && source .venv/bin/activate`)
- ChromaDB accessible (embedded, no separate service needed)

---

## Steps

1. **Write the new style exemplars**

   Open `backend/rag/style_library.json`. Add at least 3 exemplar entries for the new style, one per age group (`4-6`, `7-9`, `10-12`):

   ```json
   {
     "id": "newstyle-01",
     "style": "newstyle",
     "age_group": "4-6",
     "tone": "playful",
     "text": "Alex found a magical doorway behind the old bookshelf..."
   }
   ```

   Ensure each entry has a unique `id` following the pattern `<style>-<nn>`.

2. **Validate the JSON file**

   ```bash
   python3 -c "import json; json.load(open('backend/rag/style_library.json')); print('JSON valid')"
   ```

3. **Rebuild the ChromaDB index**

   ```bash
   cd backend
   python3 -m rag.build_index
   ```

   Expected output:
   ```
   Loaded 54 exemplars from style_library.json
   Embedded and upserted 54 documents into ChromaDB
   Collection 'style_library' now has 54 items
   ```

4. **Run the RAG evaluation**

   ```bash
   cd backend
   pytest tests/test_rag_eval.py -v
   ```

   The test asserts `precision@3 >= 0.8` for each style. Confirm the new style is included in the output and passes.

5. **Update `backend/rag/style_library.json` styles list** (if maintained)

   If there is a separate styles manifest or enum in `backend/app/schemas.py` or the frontend, add the new style name there too.

6. **Commit the changes**

   ```bash
   git add backend/rag/style_library.json
   git commit -m "feat(rag): add <newstyle> style to RAG library"
   ```

---

## Verification

After completing the steps, send a test generation request using the new style:

```bash
curl -X POST http://localhost:8000/api/generate-comic \
  -F "drawing=@tests/fixtures/sample_drawing.png" \
  -F "child_name=Test" \
  -F "age_group=7-9" \
  -F "style=newstyle"
```

Poll the returned `job_id` until `status=complete`, then inspect the comic to confirm the narrative reflects the new style.

---

## Rollback

If the new style produces poor narrative quality:

1. Remove the new entries from `style_library.json`.
2. Rebuild the index: `python3 -m rag.build_index`.
3. Commit the revert: `git revert HEAD`.
