---
description: Run shell command literally — immediate execution, no confirm loop
argument-hint: "<shell command>"
---

Execute the following as **one literal shell command** (no rewriting, no “improved” variant):

```bash
$ARGUMENTS
```

## Cursor 终端工具（减少二次确认）

若命令需要 **网络**、**写仓库/系统路径** 或 **子进程较多**：调用终端工具时选择 **all / full_network**（或客户端提供的非沙箱等价项），避免默认沙箱失败后让用户再手动批准一次。

## Rules (自动执行、减少人工干预)

1. **先执行**：在拿到本消息后，**立刻**用终端工具运行上述命令；不要先贴出“我准备执行…”再等待用户回复。
2. **原样执行**：`$ARGUMENTS` 即用户输入在 `/shell` 之后的全文；不要拆分、不要加引号/转义（除非用户原文里已有）。
3. **不要做前置调研**：除非命令本身必须在仓库里解析路径，否则不要为了“看懂仓库”而先跑别的命令。
4. **空参数**：若 `$ARGUMENTS` 为空或只有空白，**只问一次**要执行哪条命令，不要反复确认。
5. **执行后**：用一两句话报告退出码、以及 stderr/stdout 里对排错重要的尾部即可。

## Cursor 终端工具（减少二次确认）

当本命令需要 **网络**、**写 git 仓库**、**访问完整文件系统** 或 **长时间安装依赖** 时：调用终端工具时请选择 **all / full_network**（或当前客户端提供的「非沙箱 / 全部权限」等价项），**不要**默认用受限沙箱再让用户手动重试。

## 说明

Cursor 若仍弹出**单次**环境级批准，批准一次即可；本命令禁止 Agent 在聊天里再问「要不要执行」。
