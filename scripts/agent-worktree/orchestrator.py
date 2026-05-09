# Copyright 2025-2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Skeleton orchestrator for multi-worker Cursor `agent` CLI runs.

State is stored under ``<workspace>/.agent-worktree/<run_id>/``. This module
implements policy parsing, manifest/backlog initialization, a minimal
dispatch loop (dry-run or real ``agent``), hourly status snapshots, and a
``status`` subcommand for on-demand progress.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Literal, NoReturn
import uuid

AGENT_BIN = "agent"


def noninteractive_child_env() -> dict[str, str]:
    """Environment for subprocesses so git/agent avoid TTY prompts where possible."""
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("EDITOR", "true")
    env.setdefault("VISUAL", "true")
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")
    return env


def _load_lib_module(stem: str) -> Any:
    """Load ``lib/<stem>.py`` adjacent to this script (no package install)."""
    root = Path(__file__).resolve().parent
    path = root / "lib" / f"{stem}.py"
    name = f"_agent_worktree_lib_{stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_prompt_templates = _load_lib_module("prompt_templates")
_agent_stdout = _load_lib_module("agent_stdout")
render_worker_prompt = _prompt_templates.render_worker_prompt
parse_agent_stdout_json = _agent_stdout.parse_agent_stdout_json
extract_worker_reply = _agent_stdout.extract_worker_reply
STATE_DIRNAME = ".agent-worktree"


@dataclass(frozen=True)
class Policy:
    """Termination and reporting policy for one orchestration run."""

    max_total_commits: int
    max_wall_clock_sec: int | None
    status_interval_sec: int
    auto_commit: bool
    commit_prefix: str


@dataclass
class WorkerSlot:
    """One parallel worker lane."""

    index: int
    role: str


def parse_workers_from_requirement(text: str) -> int | None:
    """Infer worker count from common Chinese / numeric phrases."""
    # Note: avoid ``\b`` after CJK quantifiers like ``个`` when followed by ASCII
    # (e.g. ``三个agent``); Unicode word-char rules break that boundary.
    if re.search(r"(?i)(?:三|3)\s*(?:位|个|名)", text):
        return 3
    if re.search(r"(?i)(?:四|4)\s*(?:位|个|名)", text):
        return 4
    if re.search(r"(?i)(?:两|二|2)\s*(?:位|个|名)", text):
        return 2
    m = re.search(r"(\d+)\s*个\s*(?:agent|Agent|worker|Worker|角色)", text)
    if m:
        return max(1, int(m.group(1)))
    m2 = re.search(r"(?i)(\d+)\s*[- ]?\s*(?:agents?|workers?)\b", text)
    if m2:
        return max(1, int(m2.group(1)))
    return None


def parse_auto_commit_from_requirement(text: str) -> bool:
    """Return True if the user asked for automatic git commits in natural language."""
    return bool(
        re.search(
            r"(?i)(?:自动提交|自動提交|autocommit|auto[-_]?commit|commit\s+automatically)",
            text,
        )
    )


def parse_max_commits_from_requirement(text: str) -> int | None:
    """Infer max commit budget from natural language."""
    patterns = [
        r"(?:至少|不少于|最少)\s*(\d+)\s*次\s*(?:commit|提交)",
        r"(?:至少|不少于|最少)\s*(\d+)\s*(?:commit|提交)",
        r"(\d+)\s*次\s*(?:commit|提交)",
        r"max[_-]?commits?\s*[:=]\s*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return max(1, int(m.group(1)))
    return None


def infer_roles(requirement: str, workers: int) -> list[str]:
    """Assign stable role ids; heuristics for a typical robotics split."""
    req_lower = requirement.lower()
    roles: list[str] = []
    if workers == 3 and (
        "建图" in requirement or "mapping" in req_lower or "map" in req_lower
    ):
        if "导航" in requirement or "navigation" in req_lower:
            roles.append("mapping")
            roles.append("navigation")
            roles.append("perception" if ("感知" in requirement or "检测" in requirement) else "worker-2")
            return roles[:workers]
    return [f"worker-{i}" for i in range(workers)]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_rev_parse(workspace: Path, ref: str = "HEAD") -> str:
    out = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
        env=noninteractive_child_env(),
    )
    return out.stdout.strip()


def git_commit_count_range(workspace: Path, base: str, head: str = "HEAD") -> int:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "rev-list", "--count", f"{base}..{head}"],
        capture_output=True,
        text=True,
        env=noninteractive_child_env(),
        check=False,
    )
    if proc.returncode != 0:
        return 0
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def ensure_agent_cli(*, dry_run: bool) -> str | None:
    path = shutil.which(AGENT_BIN)
    if path is None and not dry_run:
        return f"'{AGENT_BIN}' not found on PATH; install Cursor CLI."
    return None


def ensure_api_key(*, dry_run: bool) -> str | None:
    if dry_run:
        return None
    if not os.environ.get("CURSOR_API_KEY"):
        return "CURSOR_API_KEY is not set; required for headless `agent` runs."
    return None


def build_agent_argv(
    *,
    workspace: Path,
    prompt: str,
    output_format: Literal["json", "text"] = "json",
    use_agent_worktree: bool = True,
) -> list[str]:
    """Argv for one headless ``agent`` invocation.

    When ``use_agent_worktree`` is False (e.g. ``--auto-commit``), edits land in
    ``--workspace`` so the orchestrator can ``git commit`` them. Otherwise the
    Cursor CLI uses ``--worktree`` and changes may live outside this workspace.
    """
    argv: list[str] = [
        AGENT_BIN,
        "-p",
        "--force",
        "--output-format",
        output_format,
        "--workspace",
        str(workspace),
    ]
    if use_agent_worktree:
        argv.extend(["--worktree", prompt])
    else:
        argv.append(prompt)
    return argv


def git_try_autocommit(workspace: Path, *, message: str) -> tuple[bool, str]:
    """If the tree has changes, ``git add -A`` and ``git commit -m message``.

    Returns ``(True, sha)`` on a new commit, ``(False, reason)`` if there was
    nothing to commit or git failed.
    """
    env = noninteractive_child_env()
    st = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if st.returncode != 0:
        return False, f"git status failed: {(st.stderr or '').strip()}"
    if not (st.stdout or "").strip():
        return False, "nothing_to_commit"

    add = subprocess.run(
        ["git", "-C", str(workspace), "add", "-A"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if add.returncode != 0:
        return False, f"git add failed: {(add.stderr or add.stdout or '').strip()}"

    cm = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "commit",
            "--no-gpg-sign",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if cm.returncode != 0:
        detail = (cm.stderr or cm.stdout or "git commit failed").strip()
        return False, detail

    head = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return True, head.stdout.strip()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_event(run_dir: Path, event: dict[str, Any]) -> None:
    line = json.dumps(event, sort_keys=True) + "\n"
    log_path = run_dir / "events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _truncate(s: str, max_chars: int = 8192) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 32] + "\n...<truncated>...\n"


def initial_backlog(run_id: str, roles: list[str]) -> list[dict[str, Any]]:
    """Minimal placeholder tasks so the skeleton has something to dispatch."""
    tasks: list[dict[str, Any]] = []
    for i, role in enumerate(roles):
        tasks.append(
            {
                "id": f"bootstrap-{i}",
                "title": f"Verify repo layout and AGENTS.md for role {role}",
                "role": role,
                "status": "todo",
                "acceptance": "Print a one-line summary of repo purpose; no code changes required.",
            }
        )
    return tasks


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def load_backlog(run_dir: Path) -> list[dict[str, Any]]:
    data = json.loads((run_dir / "backlog.json").read_text(encoding="utf-8"))
    return list(data["tasks"])


def save_backlog(run_dir: Path, tasks: list[dict[str, Any]]) -> None:
    write_json(run_dir / "backlog.json", {"tasks": tasks})


def write_worker_state(run_dir: Path, worker: WorkerSlot, payload: dict[str, Any]) -> None:
    d = run_dir / "workers"
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / f"{worker.index}-{worker.role}.json", payload)


def write_status_report(run_dir: Path, tasks: list[dict[str, Any]], note: str) -> None:
    by_status: dict[str, int] = {}
    for t in tasks:
        st = str(t.get("status", "unknown"))
        by_status[st] = by_status.get(st, 0) + 1
    report = {
        "generated_at": utc_now_iso(),
        "note": note,
        "task_counts_by_status": by_status,
        "tasks": tasks,
    }
    write_json(run_dir / "last_status.json", report)
    append_event(run_dir, {"type": "status", "at": report["generated_at"], "counts": by_status})


def cmd_start(args: argparse.Namespace) -> int:
    workspace: Path = Path(args.workspace).resolve()
    if not (workspace / ".git").exists() and not (workspace / ".git").is_file():
        print(f"error: not a git workspace: {workspace}", file=sys.stderr)
        return 2

    err = ensure_agent_cli(dry_run=args.dry_run)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    err_key = ensure_api_key(dry_run=args.dry_run)
    if err_key:
        print(f"error: {err_key}", file=sys.stderr)
        return 1

    req = args.requirement.strip()
    if not req:
        print("error: --requirement must be non-empty", file=sys.stderr)
        return 2

    hinted = parse_workers_from_requirement(req)
    workers: int = hinted if hinted is not None else int(args.workers)
    if workers < 1:
        print("error: workers must be >= 1", file=sys.stderr)
        return 2

    max_commits_hint = parse_max_commits_from_requirement(req)
    max_commits = max_commits_hint if max_commits_hint is not None else int(args.max_commits)

    auto_commit = bool(args.auto_commit) or parse_auto_commit_from_requirement(req)
    use_agent_worktree = not auto_commit
    if auto_commit and not args.dry_run:
        print(
            "agent-worktree: auto-commit enabled — agent runs in --workspace "
            "(no --worktree) so git can see changes.",
            file=sys.stderr,
        )

    policy = Policy(
        max_total_commits=max_commits,
        max_wall_clock_sec=int(args.max_wall_clock_sec)
        if args.max_wall_clock_sec is not None
        else None,
        status_interval_sec=max(60, int(args.status_interval_sec)),
        auto_commit=auto_commit,
        commit_prefix=str(args.commit_prefix).strip() or "agent-worktree",
    )

    run_id = str(uuid.uuid4())
    baseline = git_rev_parse(workspace)
    run_dir = workspace / STATE_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    roles = infer_roles(req, workers)
    while len(roles) < workers:
        roles.append(f"worker-{len(roles)}")
    roles = roles[:workers]
    slots = [WorkerSlot(i, roles[i]) for i in range(workers)]

    manifest = {
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "workspace": str(workspace),
        "baseline_sha": baseline,
        "requirement": req,
        "policy": asdict(policy),
        "workers": [asdict(s) for s in slots],
        "use_agent_worktree": use_agent_worktree,
    }
    write_json(run_dir / "manifest.json", manifest)
    tasks = initial_backlog(run_id, roles)
    save_backlog(run_dir, tasks)
    append_event(run_dir, {"type": "run_started", "run_id": run_id})

    print(f"agent-worktree: run_id={run_id}")
    print(f"agent-worktree: state_dir={run_dir}")

    start_mono = time.monotonic()
    last_status_mono = start_mono
    iteration = 0

    while True:
        iteration += 1
        elapsed = time.monotonic() - start_mono
        if policy.max_wall_clock_sec is not None and elapsed >= policy.max_wall_clock_sec:
            append_event(run_dir, {"type": "stop", "reason": "max_wall_clock_sec"})
            print("orchestrator: stopping (wall clock limit).")
            break

        commits = git_commit_count_range(workspace, baseline)
        if commits >= policy.max_total_commits:
            append_event(
                run_dir,
                {"type": "stop", "reason": "max_total_commits", "commits": commits},
            )
            print(f"orchestrator: stopping (commit budget {commits}>={policy.max_total_commits}).")
            break

        tasks = load_backlog(run_dir)
        if all(t.get("status") == "done" for t in tasks):
            append_event(run_dir, {"type": "stop", "reason": "backlog_empty"})
            print("orchestrator: stopping (all tasks done).")
            break

        if time.monotonic() - last_status_mono >= policy.status_interval_sec:
            write_status_report(run_dir, tasks, note="interval")
            print(
                f"orchestrator: status snapshot (commits_since_baseline={commits}, "
                f"iteration={iteration})"
            )
            last_status_mono = time.monotonic()

        dispatched = False
        for slot in slots:
            task = next(
                (t for t in tasks if t.get("role") == slot.role and t.get("status") == "todo"),
                None,
            )
            if task is None:
                continue
            dispatched = True
            task["status"] = "doing"
            save_backlog(run_dir, tasks)
            prompt = render_worker_prompt(task, slot, run_id, auto_commit=auto_commit)
            argv = build_agent_argv(
                workspace=workspace,
                prompt=prompt,
                use_agent_worktree=use_agent_worktree,
            )
            append_event(
                run_dir,
                {
                    "type": "dispatch",
                    "worker": asdict(slot),
                    "task_id": task["id"],
                    "argv": argv,
                    "dry_run": args.dry_run,
                    "auto_commit": auto_commit,
                },
            )

            if args.dry_run:
                print(f"dry-run: would execute: {shlex_join(argv)}")
                task["status"] = "done"
                dry_payload: dict[str, Any] = {
                    "last_task_id": task["id"],
                    "exit_code": 0,
                    "summary": "dry-run",
                    "updated_at": utc_now_iso(),
                }
                if auto_commit:
                    print(
                        "dry-run: would run git add -A && git commit if tree dirty "
                        f"(prefix={policy.commit_prefix})",
                        file=sys.stderr,
                    )
                    dry_payload["auto_commit"] = True
                write_worker_state(run_dir, slot, dry_payload)
            else:
                proc = subprocess.run(
                    argv,
                    cwd=str(workspace),
                    check=False,
                    capture_output=True,
                    text=True,
                    env=noninteractive_child_env(),
                )
                ok = proc.returncode == 0
                combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                parsed = parse_agent_stdout_json(proc.stdout or "")
                reply_status, reply_summary = (
                    extract_worker_reply(parsed) if parsed is not None else (None, None)
                )
                if ok and reply_status == "blocked":
                    task["status"] = "blocked"
                elif ok and reply_status == "done":
                    task["status"] = "done"
                else:
                    task["status"] = "done" if ok else "blocked"
                summary = (
                    reply_summary
                    if reply_summary
                    else ("completed" if ok else "agent_failed")
                )
                worker_payload: dict[str, Any] = {
                    "last_task_id": task["id"],
                    "exit_code": proc.returncode,
                    "summary": summary,
                    "agent_reply_status": reply_status,
                    "stdout_tail": _truncate(combined),
                    "updated_at": utc_now_iso(),
                }
                if auto_commit and task["status"] == "done":
                    cmsg = (
                        f"{policy.commit_prefix}: run={run_id} "
                        f"task={task['id']} role={slot.role}"
                    )
                    committed, detail = git_try_autocommit(workspace, message=cmsg)
                    worker_payload["git_autocommit_ok"] = committed
                    worker_payload["git_autocommit_detail"] = detail
                    if committed:
                        worker_payload["git_commit_sha"] = detail
                    append_event(
                        run_dir,
                        {
                            "type": "git_autocommit",
                            "task_id": task["id"],
                            "worker": asdict(slot),
                            "ok": committed,
                            "detail": detail,
                        },
                    )
                write_worker_state(run_dir, slot, worker_payload)
            save_backlog(run_dir, tasks)
            break

        if not dispatched:
            time.sleep(1.0)
            if all(t.get("status") in ("done", "blocked") for t in load_backlog(run_dir)):
                append_event(run_dir, {"type": "stop", "reason": "no_dispatchable_tasks"})
                print("orchestrator: stopping (no todo tasks remain).")
                break

    write_status_report(run_dir, load_backlog(run_dir), note="final")
    return 0


def shlex_join(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)


def cmd_status(args: argparse.Namespace) -> int:
    workspace: Path = Path(args.workspace).resolve()
    run_dir = workspace / STATE_DIRNAME / args.run_id
    if not run_dir.is_dir():
        print(f"error: run_dir not found: {run_dir}", file=sys.stderr)
        return 2
    status_path = run_dir / "last_status.json"
    if not status_path.is_file():
        print(f"error: no status file yet: {status_path}", file=sys.stderr)
        return 1
    sys.stdout.write(status_path.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agent worktree orchestrator (skeleton).")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start", help="Run orchestration loop until a stop condition.")
    s.add_argument("--workspace", type=Path, default=Path.cwd(), help="Git repository root.")
    s.add_argument("--requirement", type=str, required=True, help="User requirement text.")
    s.add_argument("--workers", type=int, default=2, help="Worker count when requirement omits it.")
    s.add_argument("--max-commits", type=int, default=100, help="Max new commits vs baseline.")
    s.add_argument(
        "--max-wall-clock-sec",
        type=int,
        default=None,
        help="Optional wall-clock limit in seconds.",
    )
    s.add_argument(
        "--status-interval-sec",
        type=int,
        default=3600,
        help="Write last_status.json at least this often (default 1h).",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not invoke `agent`; mark tasks done after logging argv.",
    )
    s.add_argument(
        "--auto-commit",
        action="store_true",
        help=(
            "After each successful worker task, git add -A && git commit in "
            "--workspace. Implies agent runs without --worktree so changes are visible to git."
        ),
    )
    s.add_argument(
        "--commit-prefix",
        default="agent-worktree",
        help="First line of commit message prefix (default: agent-worktree).",
    )
    s.set_defaults(func=cmd_start)

    t = sub.add_parser("status", help="Print last_status.json for a run.")
    t.add_argument("--workspace", type=Path, default=Path.cwd())
    t.add_argument("--run-id", type=str, required=True)
    t.set_defaults(func=cmd_status)

    return p


def main() -> NoReturn:
    parser = build_parser()
    args = parser.parse_args()
    code = int(args.func(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
