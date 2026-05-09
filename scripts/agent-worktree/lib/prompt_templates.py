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

"""Prompt strings for Cursor ``agent`` headless invocations."""

from __future__ import annotations

from typing import Any, Protocol


class WorkerSlotLike(Protocol):
    index: int
    role: str


def render_worker_prompt(
    task: dict[str, Any],
    worker: WorkerSlotLike,
    run_id: str,
    *,
    auto_commit: bool = False,
) -> str:
    """Build the worktree prompt for one micro-task on one worker lane."""
    body = (
        f"You are orchestrated worker slot {worker.index} (role={worker.role}) for run {run_id}.\n"
        f"Task id: {task['id']}\n"
        f"Title: {task['title']}\n"
        f"Acceptance: {task['acceptance']}\n"
        "Reply in JSON with keys: status (done|blocked), summary (string)."
    )
    if auto_commit:
        body += (
            "\n\nThe orchestrator will run `git add -A` and `git commit` in this repo "
            "after you finish if there are changes. Keep edits scoped to this task."
        )
    return body


def render_planner_prompt(requirement: str, workers: int, roles: list[str]) -> str:
    """Ask the planner agent for a machine-readable backlog (no repo edits)."""
    roles_csv = ", ".join(roles)
    return (
        "You are the orchestration planner. Do not modify any files.\n"
        f"User requirement:\n{requirement}\n\n"
        f"Worker count: {workers}. Roles: {roles_csv}.\n"
        "Output ONLY a single JSON object with key \"tasks\" whose value is an array of "
        "objects: {id, title, role, acceptance, deps (array of ids), status (todo)}. "
        "Include at least one bootstrap task per role."
    )
