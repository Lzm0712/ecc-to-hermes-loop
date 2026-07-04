# AGENTS.md — Loop Engineering Memory

## Loop Configuration
- **Repository**: Lzm0712/ecc-to-hermes-loop
- **Current Round**: R4
- **Started**: 2026-06-20

## Active Loop Goals
- [ ] 实现 Worktree 隔离（每 agent 独立目录）
- [ ] 实现 MCP 连接器（GitHub API, Filesystem）
- [ ] 实现 Memory 文件持久化（AGENTS.md, TODO.md）
- [ ] 实现 /goal 等价的验证条件驱动循环

## Worktree Registry
| Branch | Worktree Path | Purpose | Agent |
|--------|--------------|---------|-------|
| main | (primary) | Stable branch | - |
| worktree/agent-* | ../worktrees/agent-* | Agent isolation | each agent |

## Agent Registry
| Agent | Role | Skill | Worktree |
|-------|------|-------|----------|
| planner | Goal decomposition | planner-agent | worktree/planner |
| code-reviewer | Code quality | code-reviewer-agent | worktree/reviewer |
| security | Security audit | security-reviewer-agent | worktree/security |
| tdd | Test-driven dev | tdd-guide-agent | worktree/tdd |

## Known Issues
- [ ] 5 个 phase 目录缺少 __init__.py（phase1/3/4/5/6）
- [ ] 类型注解缺失（13 个中严重度函数）
- [ ] ecc-loop inline Python shell 语法错误（已修复）

## Completed
- [x] R1: pytest import 误收集
- [x] R2: shared module, paths, security.py 静默吞异常, pytest_gate 硬编码
- [x] R3: 相对导入失效, ecc-loop --root, pytest-xdist 并行, 硬编码路径, 魔法数字
- [x] R4: shell 语法错误修复, bin/clear-resume.py, bin/persist-resume.py
