# ECC-to-Hermes Loop SKILL

## 状态：Loop Engineering 架构已升级 ✅

基于 Loop Engineering 完全指南 v1.0 六大组件重构。

---

## 六大组件状态

| 组件 | 状态 | 位置 |
|------|------|------|
| Automations | ✅ Cron/GHA | `.github/workflows/loop-engineering.yml` |
| Worktrees | ✅ bin/worktree-manager.py | 每 agent 独立目录 |
| Skills | ✅ SKILL.md 渐进式 | `phase4/agents/*/SKILL.md` |
| MCP Connectors | ✅ .github/mcp/ | github.py, filesystem |
| Sub-agents | ✅ phase4/agent_registry | 制造者≠审查者分离 |
| Memory | ✅ AGENTS.md, STATE.md | 跨会话持久化 |

---

## 自改进协议

### 每次激活时
1. `bin/ci-local.sh` — CI 全部通过
2. `pytest -q` — 全部 tests 通过
3. 发现问题直接修复，不攒

### 自改进扫描方向
- 死 import / 死代码
- 重复模式 → 提到 shared/
- 测试覆盖缺口
- 文档过时
- 配置/常量硬编码

---

## 项目概览

| Phase | 名称 | 核心功能 | 测试 |
|-------|------|---------|------|
| p1 | PostToolUse Hook | write_file/patch 后自动格式化/lint | 30 |
| p2 | Verification Loop | 6 stage gate: build→type→lint→test→security→diff | 64 |
| p3 | Instinct Learning | 从 session 历史提取工具序列 → instinct skills | 19 |
| p4 | Professional Agents | 任务路由 + delegate_task 调用 planner/tdd/code-reviewer/security | 27 |
| p5 | HUD Status | `hermes status --json`，统一状态契约 | 34 |
| p6 | Evaluator RAG | 基于历史 session 的成功率评估 | 32 |

**总计：169 tests** ✅

---

## 常用命令

```bash
# 本地 CI
~/.hermes/ecc-to-hermes-loop/bin/ci-local.sh

# 全量测试
cd ~/.hermes/ecc-to-hermes-loop && pytest -q

# MCP GitHub connector
python3 .github/mcp/github.py issues
python3 .github/mcp/github.py runs

# Worktree 管理
python3 bin/worktree-manager.py list
python3 bin/worktree-manager.py create reviewer --purpose "code review"
python3 bin/worktree-manager.py remove reviewer

# Agent 子代理
ecc-loop p4 --list
ecc-loop p4 --task "review code in phase2/gates/" --execute
```

---

## 文件结构

```
ecc-to-hermes-loop/
├── ecc-loop                  # CLI 入口
├── AGENTS.md                # Memory: 跨会话状态
├── STATE.md                 # Loop 状态（GitHub Actions 用）
├── bin/
│   ├── ci-local.sh         # 本地 CI
│   ├── worktree-manager.py  # Agent 隔离工作树
│   ├── clear-resume.py     # 清除 resume_point
│   └── persist-resume.py   # 持久化 resume_point
├── .github/
│   ├── mcp/
│   │   └── github.py       # GitHub MCP 连接器
│   └── workflows/
│       └── loop-engineering.yml  # GitHub Actions 自动循环
├── shared/
│   ├── paths.py
│   ├── session_db.py
│   └── tool_sequence.py
└── phase1-6/
```
