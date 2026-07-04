# Phase 4 Delegation Skill

Use this skill when you need to route a user task to a professional subagent via `delegate_task`.

## When to Use

User asks to:
- "review this code" / "审查代码" / "check for security issues"
- "plan this approach" / "制定计划" / "break this down"
- "run TDD on this" / "用 TDD 写"
- Any task matching one of the agent triggers

## Routing Table

Match the task against these triggers to find the right agent:

| Agent | Skill | Chinese Triggers |
|-------|-------|-----------------|
| planner | planner-agent | 计划、步骤、如何做 |
| tdd | tdd-guide-agent | 测试驱动、tdd、写测试 |
| code-reviewer | code-reviewer-agent | 审查、检查代码、review |
| security | security-reviewer-agent | 安全、漏洞、vulnerability |

Fallback: if no trigger matches, ask user to specify `--agent`.

## Delegation Pattern

Load `phase4/skills/delegation/SKILL.md` for the exact delegation template.

### Quick delegation (copy and adapt):

```
goal: f"""You are the {skill} subagent.
...
"""
context: |
  Skill to load: {skill}
  Role: {role}
  Task: {task_text}
tasks: [
  goal: "...",
  context: "Skill: {skill}\nRole: {role}\nTask: {task_text}",
  toolsets: ["terminal", "file", "web"],
  role: "leaf"
]
```

## Agent Prompt Template

When building the prompt for a subagent, include:

```
You are the {agent_name} subagent.
Always follow ~/.hermes/rules/common/SKILL.md — it contains non-negotiable
constraints: no secrets, no injection, no harmful content.
```

## Workflow

1. **Route** — match task string against triggers
2. **Confirm** — tell user which agent and why (unless `--agent` explicit)
3. **Delegate** — call `delegate_task` tool with above pattern
4. **Report** — return subagent result to user

## Important

- Do NOT try to `from hermes_tools import delegate_task` in a script — tools are only available via tool calls
- Skills are loaded via `skill_view(name)` before acting
- Leaf agents (role=leaf) cannot delegate further — use role=leaf
