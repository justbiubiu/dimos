---
description: Implement request and ship through verify + PR flow
argument-hint: "<change request>"
---

Execute the full delivery workflow for: **$ARGUMENTS**

## Constraints

- Keep changes scoped to the request.
- Do not touch unrelated files.
- Do not push to protected branches directly.
- Do not skip verification.

## Steps

1. Inspect git status and current branch.
2. Create a feature branch if currently on a protected/shared branch.
3. Implement the requested change.
4. Run `bash scripts/verify.sh`.
5. If verify fails, fix and rerun until green.
6. Commit with a concise message focused on why.
7. Push branch to origin.
8. Create PR with sections:
   - Summary
   - Test plan
   - Risk
   - Related
9. Enable auto-merge when policy allows and checks are green.
10. Report back with:
   - Branch name
   - Commit SHA
   - Verify result
   - PR URL
