import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO_ROOT / ".claude" / "hooks" / "global-skill-router.ps1"


def run_router(prompt: str) -> dict | None:
    payload = {
        "session_id": "test-session",
        "cwd": str(REPO_ROOT),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HOOK_SCRIPT),
        ],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    stdout = result.stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


def additional_context(prompt: str) -> str:
    payload = run_router(prompt)
    assert payload is not None
    return payload["hookSpecificOutput"]["additionalContext"]


def test_debug_prompt_routes_to_systematic_debugging() -> None:
    context = additional_context("trace_output.json 里的检索结果不对，帮我排查一下为什么 evidence gate 失败")
    assert "systematic-debugging" in context


def test_feature_prompt_routes_to_brainstorming_and_tdd() -> None:
    context = additional_context("帮我修改 continuation validator 的行为，并补上测试")
    assert "brainstorming" in context
    assert "test-driven-development" in context


def test_plan_prompt_routes_to_writing_plans() -> None:
    context = additional_context("先别写代码，帮我给验证层重构写一个分步骤实施计划")
    assert "writing-plans" in context


def test_review_feedback_routes_to_receiving_code_review() -> None:
    context = additional_context("这是 reviewer 的意见，帮我判断哪些该改，哪些不该改")
    assert "receiving-code-review" in context


def test_completion_prompt_routes_to_verification_before_completion() -> None:
    context = additional_context("这个修复应该差不多了，帮我确认能不能提交")
    assert "verification-before-completion" in context


def test_unmatched_prompt_stays_quiet() -> None:
    assert run_router("给我解释一下韩立为什么去参加七玄门测试") is None


def test_fix_bug_routes_to_debugging_not_brainstorming() -> None:
    """修复 bug 应该触发 debugging，不是 brainstorming"""
    context = additional_context("帮我 fix 一下 evidence gate 的报错")
    assert "systematic-debugging" in context
    assert "brainstorming" not in context


def test_loop_task_routes_to_loop_skill() -> None:
    """定时任务应该触发 loop skill"""
    context = additional_context("每隔5分钟检查一下服务状态")
    assert "loop" in context


def test_output_uses_slash_command_format() -> None:
    """输出应该使用斜杠命令格式"""
    context = additional_context("帮我 fix 一下这个报错")
    assert "/systematic-debugging" in context
