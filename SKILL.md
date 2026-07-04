# ECC-to-Hermes Loop SKILL

## 状态：全部完成 ✅

Phase 1-6 全部实现并通过测试。

---

## 当前维护模式

进入维护模式，只做自改进（self-improvement loop）：

### 每次激活时
1. 运行 `bin/ci-local.sh` 确认 CI 全部通过
2. 运行 `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -m pytest --tb=short -q` 确认全部 166 tests 通过
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
cd ~/.hermes/ecc-to-hermes-loop && /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -m pytest --tb=short -q

# 单 phase 测试
python3 -m pytest phase4/test_phase4_e2e.py -v

# 运行特定 phase
ecc-loop p4 --list
ecc-loop p5 --json
ecc-loop p6 --query "ECC self-improvement"
```

---

## 文件结构

```
ecc-to-hermes-loop/
├── ecc-loop              # CLI 入口
├── bin/ci-local.sh      # 本地 CI
├── shared/
│   ├── paths.py         # HERMES_HOME, STATE_DB, SKILLS_DIR
│   ├── session_db.py    # get_db()（phase3/5 共用）
│   └── tool_sequence.py # 工具序列提取（phase3/6 共用）
├── phase1/  # PostToolUse Hook
├── phase2/  # Verification Loop
├── phase3/  # Instinct Learning
├── phase4/  # Professional Agents
├── phase5/  # HUD Status
└── phase6/  # Evaluator RAG
```
