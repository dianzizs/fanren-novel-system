# Claude Skill Routing Design

## Goal

Improve how Claude Code chooses the already-installed global superpowers skills inside this repository without adding project-local skills.

## Constraints

- Reuse only the globally installed skills that are actually present on this machine.
- Keep the routing quiet; do not force a full YES/NO skill evaluation on every prompt.
- Favor official Claude Code mechanisms already available in the repo: `CLAUDE.md` guidance plus a lightweight `UserPromptSubmit` hook.

## Chosen Approach

Use a three-part routing layer:

1. Add repository-specific guidance to `CLAUDE.md` so the project always exposes a small routing table for the most relevant superpowers skills.
2. Add a project-level `.claude/settings.json` that registers a `UserPromptSubmit` command hook.
3. Implement a small PowerShell router that reads the incoming prompt, detects high-signal cases, and injects concise `additionalContext` naming one or two relevant global skills.

## Routing Targets

- `systematic-debugging` for trace, retrieval, validator, planner, failure, and unexpected-behavior prompts
- `brainstorming` plus `test-driven-development` for behavior changes and implementation prompts
- `writing-plans` for explicit planning requests
- `receiving-code-review` for pasted review feedback
- `requesting-code-review` for fresh review requests
- `verification-before-completion` for “ready to commit/merge/submit” prompts
- `finishing-a-development-branch` for branch wrap-up prompts

## Verification

Add a targeted regression harness in `tests/test_claude_skill_router.py` that executes the hook script directly and checks the injected skill hints for representative prompts.
