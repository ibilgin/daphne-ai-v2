---
description: Commit all current changes and push to GitHub. Handles first-time remote setup if needed. Usage: /github-push or /github-push "optional commit message"
---

Safely commit and push current work to GitHub for the Sketch to Story project.

Follow this process:

1. **Security check first** — scan staged and unstaged changes for accidental secrets:
   ```bash
   git diff HEAD | grep -iE "(password|secret|token|private_key|access_key)" | head -20
   ls -la .secrets .env 2>/dev/null
   ```
   If any secrets are found in the diff, STOP and warn the user before proceeding.

2. **Check git status**:
   ```bash
   git status
   git log --oneline -5
   ```

3. **Check if remote exists**:
   ```bash
   git remote -v
   ```
   If no remote is configured, ask the user for their GitHub repo URL, then:
   ```bash
   git init  # if not already a git repo
   git remote add origin <url>
   git branch -M main
   ```

4. **Ensure .gitignore is correct** — verify these patterns are present: `.secrets`, `.env`, `__pycache__/`, `node_modules/`, `chroma_db/`, `mlruns/`, `*.safetensors`, `*.bin`, `.DS_Store`. Add any missing patterns.

5. **Stage changes** — add all modified/new files EXCEPT secrets:
   ```bash
   git add -A
   git reset HEAD .secrets .env 2>/dev/null || true
   ```

6. **Compose commit message**:
   - If the user provided a message in $ARGUMENTS, use it
   - Otherwise infer from the files changed: check `git diff --cached --name-only` and write a descriptive message following the project convention: `type(scope): description`

7. **Commit**:
   ```bash
   git commit -m "$(cat <<'EOF'
   <message>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

8. **Push**:
   ```bash
   git push -u origin $(git branch --show-current)
   ```

9. **Report**: Show the commit hash, branch, and GitHub URL for the pushed branch. If this is a phase-complete push, suggest running `/github-push` again after creating a PR with `gh pr create`.
