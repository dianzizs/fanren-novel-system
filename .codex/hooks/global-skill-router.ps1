[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

function Add-Match {
    param(
        [hashtable]$Matches,
        [string]$Skill,
        [int]$Priority,
        [string]$Reason
    )

    if (-not $Matches.ContainsKey($Skill) -or $Matches[$Skill].Priority -lt $Priority) {
        $Matches[$Skill] = @{
            Skill = $Skill
            Priority = $Priority
            Reason = $Reason
        }
    }
}

function Contains-Any {
    param(
        [string]$Haystack,
        [string[]]$Needles
    )

    if ([string]::IsNullOrEmpty($Haystack)) {
        return $false
    }

    $normalized = $Haystack.ToLowerInvariant()
    foreach ($needle in $Needles) {
        if ($normalized.Contains($needle.ToLowerInvariant())) {
            return $true
        }
    }

    return $false
}

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) {
    exit 0
}

$payload = $raw | ConvertFrom-Json
$prompt = [string]$payload.prompt
if ([string]::IsNullOrWhiteSpace($prompt)) {
    exit 0
}

$text = $prompt.ToLowerInvariant()
$matches = @{}

$isReviewFeedback = Contains-Any $prompt @(
    "reviewer",
    "review feedback",
    "code review feedback",
    "review comments",
    "评审意见",
    "审查意见",
    "review 意见",
    "代码审查反馈",
    "reviewer 的意见"
)

$isReviewRequest = (-not $isReviewFeedback) -and (Contains-Any $prompt @(
    "帮我 review",
    "review 一下",
    "review下",
    "code review",
    "review my",
    "帮我审查",
    "审查一下",
    "代码审查"
))

$isPlanning = Contains-Any $prompt @(
    "plan",
    "roadmap",
    "step-by-step",
    "implementation plan",
    "计划",
    "方案",
    "规划",
    "分步骤",
    "拆步骤",
    "实施计划",
    "先别写代码"
)

$isCompletion = Contains-Any $prompt @(
    "ready to submit",
    "ready to commit",
    "ready to merge",
    "can i submit",
    "done",
    "finished",
    "passes now",
    "all tests pass",
    "能不能提交",
    "可以提交",
    "准备提交",
    "准备合并",
    "修好了",
    "完成了",
    "差不多了",
    "pass了",
    "通过了"
)

$isLoop = Contains-Any $prompt @(
    "every",
    "poll",
    "monitor",
    "watch for",
    "check every",
    "run every",
    "每隔",
    "定时",
    "定期",
    "周期",
    "轮询",
    "监控"
)

$isBranchWrap = Contains-Any $prompt @(
    "finish branch",
    "wrap up branch",
    "cleanup branch",
    "merge workflow",
    "整理分支",
    "收尾",
    "合并分支",
    "结束开发分支"
)

$isDebug = Contains-Any $prompt @(
    "debug",
    "trace",
    "failing",
    "failure",
    "broken",
    "regression",
    "evidence gate",
    "报错",
    "错误",
    "异常",
    "排查",
    "定位",
    "失败",
    "不对",
    "不符合预期",
    "追踪",
    "检索结果",
    "证据门",
    "验证层",
    "trace_output",
    "test_trace"
)

$isImplementation = Contains-Any $prompt @(
    "implement",
    "add",
    "change",
    "modify",
    "refactor",
    "support",
    "optimize",
    "optimise",
    "fix",
    "新增",
    "添加",
    "修改",
    "实现",
    "重构",
    "优化",
    "修复",
    "支持"
)

if ($isReviewFeedback) {
    Add-Match $matches "receiving-code-review" 100 "Incoming review feedback detected; evaluate suggestions before changing code."
}

if ($isReviewRequest) {
    Add-Match $matches "requesting-code-review" 90 "Fresh review requested; use the review workflow instead of ad-hoc spot checks."
}

if ($isPlanning) {
    Add-Match $matches "writing-plans" 95 "The user is explicitly asking for a plan rather than direct implementation."
}

if ($isCompletion) {
    Add-Match $matches "verification-before-completion" 110 "Completion language detected; run fresh verification before claiming success."
}

if ($isBranchWrap) {
    Add-Match $matches "finishing-a-development-branch" 85 "The user is asking about branch integration or cleanup."
}

if ($isDebug) {
    Add-Match $matches "systematic-debugging" 105 "Debugging signals detected; find the root cause before proposing fixes."
}

if ($isLoop) {
    Add-Match $matches "loop" 95 "Recurring task detected; use loop skill for interval-based execution."
}

if ($isImplementation -and -not ($isDebug -or $isPlanning -or $isReviewFeedback -or $isReviewRequest -or $isCompletion)) {
    Add-Match $matches "brainstorming" 92 "Behavior change request detected; align on design before implementation."
    Add-Match $matches "test-driven-development" 88 "When changing code, write and watch a failing test before implementation."
}

if ($matches.Count -eq 0) {
    exit 0
}

$ordered = $matches.Values | Sort-Object Priority -Descending
$top = @($ordered | Select-Object -First 2)
$lines = @(
    "This repository uses superpowers skills. Invoke them with slash commands."
)

foreach ($match in $top) {
    $lines += ("- Use `/{0}`: {1}" -f $match.Skill, $match.Reason)
}

$response = @{
    hookSpecificOutput = @{
        additionalContext = ($lines -join "`n")
    }
}

$response | ConvertTo-Json -Compress -Depth 4
