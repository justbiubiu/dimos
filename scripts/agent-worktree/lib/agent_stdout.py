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

"""Best-effort parsing of ``agent --output-format json`` stdout."""

from __future__ import annotations

import json
from typing import Any


def parse_agent_stdout_json(stdout: str) -> dict[str, Any] | None:
    """Return a dict if stdout contains parseable JSON (whole or last object line)."""
    text = stdout.strip()
    if not text:
        return None
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = None
    if isinstance(out, dict):
        return out
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def extract_worker_reply(parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    """From worker prompt contract or nested result, return (status, summary)."""
    status = parsed.get("status")
    summary = parsed.get("summary")
    if isinstance(status, str) and isinstance(summary, str):
        return status, summary
    result = parsed.get("result")
    if isinstance(result, str):
        try:
            inner = json.loads(result)
        except json.JSONDecodeError:
            return None, result
        if isinstance(inner, dict):
            st = inner.get("status")
            su = inner.get("summary")
            if isinstance(st, str):
                return st, su if isinstance(su, str) else None
    return (status if isinstance(status, str) else None), (
        summary if isinstance(summary, str) else None
    )
