# ECC-to-Hermes Loop Engineering

## 项目概述
- **技术栈**: Python 3.11 + pytest + Git
- **测试框架**: pytest (169 tests, all pass)
- **代码风格**: ruff lint + type annotations required

## 工作约定
- 所有新代码必须通过 `pytest -q` 才可提交
- 提交前运行 `bin/ci-local.sh`
- Phase 目录结构: `phaseN/{module}.py`, `phaseN/test_*.py`, `phaseN/STATE.md`
- 禁止硬编码路径（使用 `shared/paths.py`）

## Sub-agent 配置
- `planner`: Goal decomposition → planner-agent
- `code-reviewer`: Code quality → code-reviewer-agent
- `security`: Security audit → security-reviewer-agent
- `tdd`: Test-driven dev → tdd-guide-agent

## MCP Connectors
- `.github/mcp/github.py`: GitHub API (issues, runs, PRs)

## Memory
- `AGENTS.md`: 跨会话状态、worktree 注册、已知问题
- `STATE.md`: 当前 loop 状态（GitHub Actions 用）

## Loop 设计原则（Addy Osmani）
1. 验证仍然是你的责任
2. 保持理解力——主动阅读 Loop 产出
3. 避免认知投降
