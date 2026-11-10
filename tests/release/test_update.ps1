# 換版與退回的自動測試，在 Windows PowerShell 5.1 上執行（同事電腦上的環境）。
#
#   uv run --project app python tests\release\make_versions.py $env:TEMP\dp-release
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\release\test_update.ps1 $env:TEMP\dp-release
#
# 只檢查資料夾的結果與結束代碼，不比對畫面文字（中文輸出會受主控台編碼影響）。
# 安裝資料夾刻意放在有空白和中文的路徑，這是同事電腦上最常見的狀況。
param([Parameter(Mandatory = $true)][string]$Work)
$ErrorActionPreference = "Stop"

$info = Get-Content -Raw -Encoding UTF8 (Join-Path $Work "versions.json") | ConvertFrom-Json
$dir = Join-Path $Work "測試 工具"
$failures = New-Object System.Collections.Generic.List[string]
$step = ""

function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "  ok   $what" }
    else { Write-Host "  FAIL $what" -ForegroundColor Red; $failures.Add("$step：$what") }
}

function Run-Bat([string[]]$arguments) {
    Push-Location $dir
    $ErrorActionPreference = "Continue"   # 子程式寫到 stderr 不算這個測試出錯，看結束代碼
    try {
        $output = & cmd.exe /c run.bat @arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    Write-Host ($output.Trim() -replace "(?m)^", "       ") -ForegroundColor DarkGray
    return $code
}

function Version-Of([string]$folder) {
    $file = Join-Path $dir "$folder\pyproject.toml"
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    $match = Select-String -LiteralPath $file -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($match) { return $match.Matches[0].Groups[1].Value } else { return $null }
}

function Snapshot([string]$folder) {
    $root = Join-Path $dir $folder
    Get-ChildItem -LiteralPath $root -Recurse -File | Sort-Object FullName | ForEach-Object {
        "$($_.FullName.Substring($root.Length))=$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
    } | Out-String
}

function Put-Zip([string]$version) {
    $name = "data-processor-$version.zip"
    Copy-Item -LiteralPath (Join-Path $info.zips $name) -Destination (Join-Path $dir $name)
    return (Join-Path $dir $name)
}

function Start-Step([string]$name) { $script:step = $name; Write-Host ""; Write-Host "== $name" -ForegroundColor Cyan }

# ---------- 準備：照使用者的方式安裝目前版本，放一些自己的資料 ----------
Start-Step "安裝 $($info.current)"
Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$unzip = Join-Path $Work "unzip"
Remove-Item -Recurse -Force $unzip -ErrorAction SilentlyContinue
Expand-Archive -Path $info.base -DestinationPath $unzip
Copy-Item -Recurse -Path (Join-Path (Get-ChildItem $unzip -Directory | Select-Object -First 1).FullName "*") -Destination $dir
New-Item -ItemType Directory -Force -Path "$dir\workspace\recipes", "$dir\workspace\reviews\我的", "$dir\runtime" | Out-Null
Set-Content -Encoding UTF8 -LiteralPath "$dir\workspace\recipes\我的 recipe.yaml" -Value "name: 我的"
Set-Content -Encoding UTF8 -LiteralPath "$dir\workspace\reviews\我的\abc.json" -Value '{"edits": {}}'
Set-Content -Encoding UTF8 -LiteralPath "$dir\runtime\marker.txt" -Value "環境"
$workspace = Snapshot "workspace"
$runtime = Snapshot "runtime"
Check ((Run-Bat @("version")) -eq 0) "run.bat version 可以執行"
Check ((Version-Of "app") -eq $info.current) "目前是 $($info.current)"

Start-Step "沒有新版時"
Check ((Run-Bat @("update", "--yes")) -eq 0) "結束代碼 0"
Check ((Version-Of "app") -eq $info.current) "版本不變"
Check (-not (Test-Path "$dir\app.old")) "沒有產生 app.old"

Start-Step "資料夾裡只有舊版 ZIP"
$older = Put-Zip "0.0.1"
Check ((Run-Bat @("update", "--yes")) -eq 0) "結束代碼 0"
Check ((Version-Of "app") -eq $info.current) "不會降版"
Remove-Item -LiteralPath $older

Start-Step "更新到 $($info.next)"
$zip = Put-Zip $info.next
Check ((Run-Bat @("update", "--yes")) -eq 0) "結束代碼 0"
Check ((Version-Of "app") -eq $info.next) "app 是 $($info.next)"
Check (Test-Path "$dir\app\version-marker.txt") "新版的檔案到位"
Check ((Version-Of "app.old") -eq $info.current) "app.old 保留 $($info.current)"
Check (-not (Test-Path -LiteralPath $zip)) "安裝完的 ZIP 已刪除"
Check (-not (Test-Path "$dir\updates")) "沒有留下暫存資料夾"
Check ((Snapshot "workspace") -eq $workspace) "workspace 完全沒變"
Check ((Snapshot "runtime") -eq $runtime) "runtime 沒被動到"
Check (Test-Path "$dir\run.bat") "run.bat 還在"

Start-Step "退回上一版，再回到新版"
Check ((Run-Bat @("rollback")) -eq 0) "rollback 結束代碼 0"
Check ((Version-Of "app") -eq $info.current) "退回 $($info.current)"
Check ((Version-Of "app.old") -eq $info.next) "app.old 變成 $($info.next)"
Check ((Run-Bat @("rollback")) -eq 0) "再執行一次 rollback"
Check ((Version-Of "app") -eq $info.next) "回到 $($info.next)"
Check (-not (Test-Path "$dir\app.swap")) "沒有留下 app.swap"
Check ((Snapshot "workspace") -eq $workspace) "workspace 完全沒變"

foreach ($case in @(@{ version = $info.broken; why = "ZIP 裡沒有 app 資料夾" },
                    @{ version = $info.mismatch; why = "ZIP 檔名和內容版本不符" })) {
    Start-Step "壞掉的 ZIP：$($case.why)"
    $bad = Put-Zip $case.version
    Run-Bat @("update", "--yes") | Out-Null
    Check ((Version-Of "app") -eq $info.next) "還是 $($info.next)"
    Check ((Version-Of "app.old") -eq $info.current) "app.old 還是 $($info.current)，仍然可以退回"
    Check (Test-Path -LiteralPath $bad) "沒安裝成功的 ZIP 留著"
    Check (-not (Test-Path "$dir\updates")) "沒有留下暫存資料夾"
    Remove-Item -LiteralPath $bad
}

Start-Step "更新時 app 裡有檔案被開著（防毒或編輯器鎖住）"
$zip = Put-Zip $info.after
$lock = [System.IO.File]::Open("$dir\app\recipe-spec.md", "Open", "Read", "None")
try { Run-Bat @("update", "--yes") | Out-Null } finally { $lock.Close() }
Check ((Version-Of "app") -eq $info.next) "還是 $($info.next)，可以繼續用"
Check ((Version-Of "app.old") -eq $info.current) "app.old 還是 $($info.current)，失敗的更新不會弄丟可以退回的版本"
Check (-not (Test-Path "$dir\updates")) "沒有留下暫存資料夾"
Check (Test-Path -LiteralPath $zip) "ZIP 留著，下次可以再試"

Start-Step "解除鎖定後再試一次"
Check ((Run-Bat @("update", "--yes")) -eq 0) "結束代碼 0"
Check ((Version-Of "app") -eq $info.after) "更新到 $($info.after)"
Check ((Version-Of "app.old") -eq $info.next) "app.old 是 $($info.next)"
Check ((Snapshot "workspace") -eq $workspace) "workspace 完全沒變"

Start-Step "沒有上一版時 rollback"
Remove-Item -Recurse -Force "$dir\app.old"
Check ((Run-Bat @("rollback")) -ne 0) "結束代碼不是 0"
Check ((Version-Of "app") -eq $info.after) "app 沒被動到"

Write-Host ""
if ($failures.Count) {
    Write-Host "失敗 $($failures.Count) 項：" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
Write-Host "換版測試全部通過" -ForegroundColor Green
