---
name: agent-worktree
description: >-
  Starts or inspects the DimOS multi-worker Cursor Agent CLI orchestration
  pipeline (git worktrees, configurable workers and stop policy, hourly
  status). Use when the user invokes /agent-worktree, mentions agent-worktree
  orchestration, or wants parallel Cursor CLI workers under scripts/agent-worktree.
disable-model-invocation: true
---

# Agent Worktree（多 Worker + Orchestrator）

本 Skill 描述如何在仓库内启动 **Orchestrator + 多 Worker** 骨架：通过 Cursor 的 **`agent` CLI**（`agent -p --force`，见官方文档）执行任务；默认使用 **`--worktree`** 隔离编辑区。若启用 **`--auto-commit`**，则改为仅在 **`--workspace`** 内改文件并在每次 Worker 成功后 **`git add -A && git commit`**。

## 何时使用

- 用户在 CLI 或聊天中输入 **`/agent-worktree`** 并附上需求文本。
- 用户提到 **`scripts/agent-worktree`**、多 agent 并行、worktree 隔离编排。

## 前置条件

1. 已安装 Cursor CLI，且 **`agent` 在 `PATH` 中**。
2. 设置 **`CURSOR_API_KEY`**（headless 场景需要）。
3. 在仓库根目录执行；工作区为有效 Git 仓库。

## 启动编排（推荐）

在仓库根目录：

```bash
bash scripts/agent-worktree/run.sh start --requirement "你的需求全文" --workspace .
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--workers N` | Worker 数量；默认 `2`。需求里若写明人数/角色数，应先解析或让用户传此参数。 |
| `--max-commits N` | 全仓累计新 commit 上限（相对 run 基线）；默认 `100`。 |
| `--max-wall-clock-sec N` | 可选墙钟上限（秒）。 |
| `--dry-run` | 只记录将执行的 `agent` 命令，不真正调用子进程。 |
| `--status-interval-sec N` | 状态摘要间隔；默认 `3600`（1 小时）。调试用可改小。 |
| `--auto-commit` | 每个 Worker 任务成功且工作区有变更时自动提交；**不再**传 `agent --worktree`，以便 git 能看到改动。需求中含「自动提交」等词时也会开启。 |
| `--commit-prefix S` | 提交说明前缀（默认 `agent-worktree`）；完整消息形如 ``S: run=<uuid> task=<id> role=<role>``。 |
| （实现细节） | `orchestrator` 对子进程设置 `GIT_TERMINAL_PROMPT=0`、`DEBIAN_FRONTEND=noninteractive` 等；自动提交使用 `git commit --no-gpg-sign` 以避免 GPG 弹窗。`run.sh` 入口亦导出同名环境变量。 |

等价调用：

```bash
uv run python scripts/agent-worktree/orchestrator.py start --requirement "..." --workspace .
```

## 查询某次 run 的进展

```bash
uv run python scripts/agent-worktree/orchestrator.py status --workspace . --run-id "<uuid>"
```

## Agent 在收到 `/agent-worktree` 时应做的事

1. **自检（不逐条问用户）**：若缺少 `agent` 或 `CURSOR_API_KEY`，打印明确错误/一次性设置说明后停止；不要在聊天里循环确认。
2. 将用户自然语言需求整理为一条 **`--requirement`** 字符串；若能从需求中确定人数，追加 **`--workers`**。
3. **立刻**在仓库根执行 **`run.sh start`**（需要 `uv`/网络时，终端工具选 **all** 或 **full_network**，避免沙箱失败后再让用户手动点重试）。说明状态目录：**`<workspace>/.agent-worktree/<run-id>/`**。
4. 设计细节与任务分解约定见：`unitree_sdk2/doc/worktree/agent-orchestration-24h_9480fd9f.plan.md`（若路径存在）。

## 约束

- 不修改 `scripts/verify.sh` 以绕过检查。
- 本流水线为骨架：生产级 backlog、真实 `agent` 结果解析与合并策略需在后续 PR 中扩展。
