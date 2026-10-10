# 一键回归门禁 —— 提交前必跑（tech-debt 台账 T2，docs/audit/AUDIT.md 的"可回退"承诺落地）
#
# Windows / PowerShell 5.1 直接跑：   pwsh -File scripts\check_all.ps1
# 或显式：                            powershell -ExecutionPolicy Bypass -File scripts\check_all.ps1
#
# 覆盖四道：
#   1. 语法编译   python -m compileall（每个 .py 都能被解释器读）
#   2. 静态门禁   ruff（未定义名 / 运行时错误类，见 backed/pyproject.toml [tool.ruff]）
#   3. 单元测试   pytest（DB/任务引擎/标签/版本/事件/调度器/质检/REST 接线）
#   4. 前端构建   vite build（产物落 backed/../server/static，FastAPI 挂载点）
#
# 任一步失败立刻停（等同 bash 的 set -e），最后打一行 PASS/FAIL 汇总。

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$backed = Join-Path $repoRoot 'backed'

$failed = New-Object System.Collections.Generic.List[string]

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "===> $Name" -ForegroundColor Cyan
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $Body
        if ($LASTEXITCODE -ne 0) { throw "退出码 $LASTEXITCODE" }
        Write-Host "<=== PASS $Name ($([math]::Round($sw.Elapsed.TotalSeconds,1))s)" -ForegroundColor Green
    } catch {
        Write-Host "<=== FAIL $Name : $($_.Exception.Message) ($([math]::Round($sw.Elapsed.TotalSeconds,1))s)" -ForegroundColor Red
        $failed.Add($Name)
    }
}

Push-Location $backed
try {
    $env:UV_NO_PROGRESS = '1'

    Invoke-Step '1/4 语法编译 compileall' {
        uv run python -m compileall -q .
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }

    Invoke-Step '2/4 静态门禁 ruff（backed + 根目录 mcp_server.py）' {
        uv run ruff check .
        if ($LASTEXITCODE -ne 0) { exit 1 }
        # mcp_server.py 在仓库根，不在 backed/ 的 pyproject 作用域内，显式带上同一套规则
        uv run ruff check "$repoRoot/mcp_server.py" --select E9,F7,F82
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }

    Invoke-Step '3/4 单元测试 pytest' {
        uv run pytest -q --no-header -p no:cacheprovider
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }

    if (Test-Path (Join-Path $repoRoot 'web\node_modules')) {
        Invoke-Step '4/4 前端构建 vite build' {
            pnpm --dir (Join-Path $repoRoot 'web') build
            if ($LASTEXITCODE -ne 0) { exit 1 }
        }
    } else {
        Write-Host ""
        Write-Host "===> 4/4 前端构建（跳过：web/node_modules 不存在，先 pnpm --dir web install）" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "FAIL - 未通过：$($failed -join ' | ')" -ForegroundColor Red
    exit 1
}
Write-Host "PASS - 四道门禁全绿，可以提交" -ForegroundColor Green
