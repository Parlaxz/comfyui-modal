# Bounded Golden run wrapper.
#
# v2ctl golden run has no timeout knob and run_v2_single.bat honours none, so a
# container that stalls during Modal snapshot restore blocks forever: the cohort
# directory is created, no attempt artifact is ever written, and nothing is
# recorded.  This bounds the wait, kills the client on expiry, and preserves the
# empty cohort directory as failure evidence instead of hanging.
param(
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$Profile,
    [Parameter(Mandatory = $true)][string]$App,
    [string]$Owner = "m1-copy-rootcause",
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $WorkDir

$argList = @(
    "-m", "tools.v2_control.cli",
    "--profile", $Profile,
    "--owner", $Owner,
    "golden", "run", "--app", $App
)

$stdout = Join-Path $env:TEMP "m1b_run_stdout.log"
$stderr = Join-Path $env:TEMP "m1b_run_stderr.log"

$started = Get-Date
$proc = Start-Process -FilePath "python" -ArgumentList $argList -NoNewWindow -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

Write-Output ("BOUNDED_RUN pid={0} timeout_s={1}" -f $proc.Id, $TimeoutSeconds)

if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    $elapsed = [int]((Get-Date) - $started).TotalSeconds
    Write-Output "VERDICT=TIMEOUT elapsed_s=$elapsed"
    try { $proc.Kill($true) } catch { try { $proc.Kill() } catch {} }
    Start-Sleep -Seconds 2
    Write-Output "--- stderr tail ---"
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 12 }
    $cohortRoot = Join-Path $WorkDir "artifacts\phase_p1_parallel_golden_v1"
    if (Test-Path -LiteralPath $cohortRoot) {
        $empty = Get-ChildItem -LiteralPath $cohortRoot -Directory |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($empty) {
            $items = @(Get-ChildItem -LiteralPath $empty.FullName -Recurse -ErrorAction SilentlyContinue)
            Write-Output ("EMPTY_COHORT={0} files={1} (preserved as failure evidence)" -f $empty.Name, $items.Count)
        }
    }
    exit 124
}

$elapsed = [int]((Get-Date) - $started).TotalSeconds
Write-Output ("exit={0} elapsed_s={1}" -f $proc.ExitCode, $elapsed)
Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue |
    Select-String -Pattern "exit=" | Select-Object -Last 1
exit $proc.ExitCode
