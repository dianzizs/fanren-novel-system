# Claude Skill Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve repository-specific routing into the already-installed global superpowers skills without creating project-local skills.

**Architecture:** Add a small routing table to `CLAUDE.md`, register a project-level `UserPromptSubmit` hook in `.claude/settings.json`, and implement a PowerShell command hook that injects concise `additionalContext` for the most relevant global skills. Verify with a direct pytest harness that runs the hook script itself.

**Tech Stack:** Claude Code project settings, PowerShell, pytest, Python subprocess

---

### Task 1: Lock The Router Behavior With Tests

**Files:**
- Create: `tests/test_claude_skill_router.py`

- [ ] **Step 1: Write the failing test**

```python
def test_debug_prompt_routes_to_systematic_debugging() -> None:
    context = additional_context("trace_output.json 里的检索结果不对，帮我排查一下为什么 evidence gate 失败")
    assert "systematic-debugging" in context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: FAIL because `.claude/hooks/global-skill-router.ps1` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```text
Add the router script and project settings that the test expects to call.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_claude_skill_router.py .claude/settings.json .claude/hooks/global-skill-router.ps1 CLAUDE.md
git commit -m "chore: route prompts to global superpowers skills"
```

### Task 2: Add Repository Routing Guidance

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write the failing test**

```python
def test_feature_prompt_routes_to_brainstorming_and_tdd() -> None:
    context = additional_context("帮我修改 continuation validator 的行为，并补上测试")
    assert "brainstorming" in context
    assert "test-driven-development" in context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: FAIL until the repository guidance and router produce the expected hint.

- [ ] **Step 3: Write minimal implementation**

```markdown
## Claude Code / Superpowers Routing
- 调试、trace、检索异常、测试失败：先考虑 `systematic-debugging`
- 新增功能、修改行为、重构：先考虑 `brainstorming`；进入代码实现后考虑 `test-driven-development`
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add superpowers routing guidance"
```

### Task 3: Register And Implement The Hook

**Files:**
- Create: `.claude/settings.json`
- Create: `.claude/hooks/global-skill-router.ps1`

- [ ] **Step 1: Write the failing test**

```python
def test_plan_prompt_routes_to_writing_plans() -> None:
    context = additional_context("先别写代码，帮我给验证层重构写一个分步骤实施计划")
    assert "writing-plans" in context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: FAIL until the hook is registered and the PowerShell router returns `additionalContext`.

- [ ] **Step 3: Write minimal implementation**

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -ExecutionPolicy Bypass -File .claude\\hooks\\global-skill-router.ps1"
          }
        ]
      }
    ]
  }
}
```

```powershell
$response = @{
    hookSpecificOutput = @{
        additionalContext = "This repository strongly prefers the installed global superpowers workflow skills."
    }
}
$response | ConvertTo-Json -Compress -Depth 4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json .claude/hooks/global-skill-router.ps1
git commit -m "chore: add global skill routing hook"
```

### Task 4: Verify Completion Routing

**Files:**
- Modify: `.claude/hooks/global-skill-router.ps1`

- [ ] **Step 1: Write the failing test**

```python
def test_completion_prompt_routes_to_verification_before_completion() -> None:
    context = additional_context("这个修复应该差不多了，帮我确认能不能提交")
    assert "verification-before-completion" in context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: FAIL until completion prompts route to the verification skill.

- [ ] **Step 3: Write minimal implementation**

```powershell
if ($isCompletion) {
    Add-Match $matches "verification-before-completion" 110 "Completion language detected; run fresh verification before claiming success."
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\anaconda3\envs\chaishu\python.exe -m pytest tests/test_claude_skill_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/global-skill-router.ps1
git commit -m "chore: route completion prompts to verification"
```
