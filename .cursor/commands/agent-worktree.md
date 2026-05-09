---
description: Start multi-worker Cursor agent CLI orchestration (agent-worktree)
argument-hint: "<requirement text>"
---

Run the **agent-worktree** orchestration skeleton for: **$ARGUMENTS**

## Steps

1. Read project skill `.cursor/skills/agent-worktree/SKILL.md` if you need full flags and constraints.
2. **Pre-flight（不聊天确认）**：若 `command -v agent` 失败或 `CURSOR_API_KEY` 未设置，**一次性**打印错误与修复说明（不要请用户在对话里粘贴密钥）；不要为同一件事反复追问。
3. From the repository root, **immediately** run (use terminal tool with **all** / **full_network** if `uv` or `agent` needs it — do not pick a sandbox that will fail and require a manual rerun):

   ```bash
   bash scripts/agent-worktree/run.sh start --workspace . --requirement "$ARGUMENTS"
   ```

   If the user only wants a dry run (no real `agent` calls), add `--dry-run`.

4. Report the printed `run_id` and state path `.agent-worktree/<run_id>/`.
5. For progress without waiting an hour:

   ```bash
   uv run python scripts/agent-worktree/orchestrator.py status --workspace . --run-id "<run_id>"
   ```

## Notes

- Worker count defaults to `2`; pass `--workers N` when the user specifies a team size and the requirement text does not already imply it.
- Max commits defaults to `100`; override with `--max-commits N` when the user asks for a larger budget.
- If the user wants **automatic git commits** after each worker step, add **`--auto-commit`** (or include phrases like「自动提交」in the requirement). Optionally set **`--commit-prefix my-scope`**.
