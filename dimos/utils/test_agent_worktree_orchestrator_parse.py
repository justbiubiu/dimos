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

"""Tests for ``scripts/agent-worktree/orchestrator.py`` requirement heuristics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


@pytest.fixture(scope="module")
def orch() -> Any:
    repo = Path(__file__).resolve().parents[2]
    path = repo / "scripts" / "agent-worktree" / "orchestrator.py"
    name = "agent_worktree_orchestrator_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_workers_three_agents_no_space_before_ascii(orch: Any) -> None:
    assert orch.parse_workers_from_requirement("三个agent分别负责建图") == 3


def test_parse_workers_digit_prefix(orch: Any) -> None:
    assert orch.parse_workers_from_requirement("需要5个agent并行") == 5


def test_parse_max_commits_chinese(orch: Any) -> None:
    assert orch.parse_max_commits_from_requirement("至少120次commit完成") == 120


def test_infer_roles_mapping_nav_perception(orch: Any) -> None:
    req = "建图、导航、目标检测"
    roles = orch.infer_roles(req, 3)
    assert roles == ["mapping", "navigation", "perception"]


@pytest.fixture(scope="module")
def agent_stdout_mod() -> Any:
    repo = Path(__file__).resolve().parents[2]
    path = repo / "scripts" / "agent-worktree" / "lib" / "agent_stdout.py"
    name = "agent_worktree_lib_agent_stdout_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_agent_stdout_json_whole(agent_stdout_mod: Any) -> None:
    raw = '{"status": "done", "summary": "ok"}\n'
    parsed = agent_stdout_mod.parse_agent_stdout_json(raw)
    assert parsed == {"status": "done", "summary": "ok"}


def test_parse_agent_stdout_json_last_line(agent_stdout_mod: Any) -> None:
    raw = "noise\n{\"status\": \"blocked\", \"summary\": \"waiting\"}\n"
    parsed = agent_stdout_mod.parse_agent_stdout_json(raw)
    assert parsed == {"status": "blocked", "summary": "waiting"}


def test_extract_worker_reply(agent_stdout_mod: Any) -> None:
    st, su = agent_stdout_mod.extract_worker_reply({"status": "done", "summary": "x"})
    assert st == "done" and su == "x"


def test_parse_auto_commit_from_requirement(orch: Any) -> None:
    assert orch.parse_auto_commit_from_requirement("需要自动提交每次任务") is True
    assert orch.parse_auto_commit_from_requirement("use AUTO-COMMIT please") is True
    assert orch.parse_auto_commit_from_requirement("只做开发不提交流程") is False


def test_build_agent_argv_without_worktree(orch: Any) -> None:
    argv = orch.build_agent_argv(
        workspace=Path("/repo"),
        prompt="do the thing",
        use_agent_worktree=False,
    )
    assert "--worktree" not in argv
    assert argv[-1] == "do the thing"


def test_git_try_autocommit(tmp_path: Path, orch: Any) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.st"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    ok, detail = orch.git_try_autocommit(tmp_path, message="add f")
    assert ok is True
    assert len(detail) >= 7
    ok2, detail2 = orch.git_try_autocommit(tmp_path, message="noop")
    assert ok2 is False
    assert detail2 == "nothing_to_commit"
