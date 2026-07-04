# Agent Registry — Phase 4
# Maps task types to professional subagents

AGENTS = {
    "planner": {
        "skill": "agents/planner",
        "description": "Decompose complex tasks into bite-sized plans",
        "triggers": ["plan", "/plan", "approach", "how to", "break down", "步骤"],
        "role": "planner",
    },
    "tdd": {
        "skill": "agents/tdd-guide",
        "description": "Test-driven development discipline",
        "triggers": ["tdd", "test-first", "写测试", "测试驱动"],
        "role": "tdd-guide",
    },
    "code-reviewer": {
        "skill": "agents/code-reviewer",
        "description": "Independent code quality review",
        "triggers": ["review", "code review", "审查", "检查代码"],
        "role": "code-reviewer",
    },
    "security": {
        "skill": "agents/security-reviewer",
        "description": "Security-focused code review",
        "triggers": ["security", "安全", "vulnerability", "漏洞"],
        "role": "security-reviewer",
    },
}
