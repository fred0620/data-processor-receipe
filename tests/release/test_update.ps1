# 換版與退回的自動測試。不需要網路、Python 或 uv，只要 Windows PowerShell 5.1（同事電腦上的環境）。
# 公司內網、沒有外網的電腦或 GitLab runner 都能跑。
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\release\test_update.ps1
#       用目前的程式碼（run.bat 與 app\）當作已安裝的版本
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\release\test_update.ps1 -Zip dist\data-processor-0.2.0.zip
#       用實際要發布的 ZIP（從內部 GitLab Release 下載的也可以）
#
# 「下一版」與壞掉的 ZIP 都由這個腳本自己做出來。
# 只檢查資料夾的結果與結束代碼，不比對畫面文字（中文輸出會受主控台編碼影響）。
# 安裝資料夾刻意放在有空白和中文的路徑，這是同事電腦上最常見的狀況。
param(
    [string]$Zip = "",
    [string]$Work = (Join-Path $env:TEMP "dp-update-test")
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem

$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dir = Join-Path $Work "測試 工具"
$failures = New-Object System.Collections.Generic.List[string]
$step = ""

function Read-Version([string]$appDir) {
    $match = Select-String -LiteralPath (Join-Path $appDir "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    return $match.Matches[0].Groups[1].Value
}

function Bump([string]$version, [int]$n) {
    $v = [version]$version
    return "$($v.Major).$($v.Minor).$($v.Build + $n)"
}

# 準備「目前版本」：解開指定的 ZIP，或從程式碼複製（略過開發環境與快取）
Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$base = Join-Path $Work "base"
if ($Zip) {
    Expand-Archive -Path $Zip -DestinationPath (Join-Path $Work "unzip")
    $found = Get-ChildItem (Join-Path $Work "unzip") -Recurse -Filter launcher.ps1 | Select-Object -First 1
    if (-not $found) { throw "ZIP 裡找不到 app\launcher.ps1" }
    Move-Item -LiteralPath (Split-Path -Parent $found.Directory.FullName) -Destination $base
} else {
    New-Item -ItemType Directory -Force -Path "$base\app" | Out-Null
    Copy-Item -LiteralPath "$Repo\run.bat", "$Repo\run.sh" -Destination $base
    $skip = '\\(\.venv|wheels|__pycache__|\.pytest_cache)(\\|$)'
    Get-ChildItem -LiteralPath "$Repo\app" -Recurse -File | Where-Object { $_.FullName.Substring($Repo.Length) -notmatch $skip } | ForEach-Object {
        $target = Join-Path "$base\app" $_.FullName.Substring("$Repo\app".Length + 1)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
}
$current = Read-Version "$base\app"
$info = @{ current = $current; next = (Bump $current 1); after = (Bump $current 2); mismatch = (Bump $current 3); broken = (Bump $current 4) }

# 做出各種 ZIP：根目錄是 data-processor-版本，和正式發布包一樣
$zips = Join-Path $Work "zips"
New-Item -ItemType Directory -Force -Path $zips, (Join-Path $Work "stage") | Out-Null
function New-ReleaseZip([string]$fileVersion, [string]$contentVersion, [bool]$withApp = $true) {
    $stage = Join-Path $Work "stage\data-processor-$fileVersion"
    Copy-Item -Recurse -LiteralPath $base -Destination $stage
    if ($withApp) {
        $toml = Join-Path $stage "app\pyproject.toml"
        $text = [IO.File]::ReadAllText($toml) -replace '(?m)^version\s*=\s*"[^"]+"', "version = `"$contentVersion`""
        [IO.File]::WriteAllText($toml, $text)
        [IO.File]::WriteAllText((Join-Path $stage "app\version-marker.txt"), $contentVersion)
    } else {
        Remove-Item -Recurse -Force (Join-Path $stage "app")
    }
    $archive = [IO.Compression.ZipFile]::Open((Join-Path $zips "data-processor-$fileVersion.zip"), "Create")
    try {
        $rootLength = (Split-Path -Parent $stage).Length + 1
        foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File) {
            $entry = $file.FullName.Substring($rootLength) -replace '\\', '/'
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $entry) | Out-Null
        }
    } finally { $archive.Dispose() }
}
New-ReleaseZip $info.next $info.next                  # 正常的下一版
New-ReleaseZip $info.after $info.after                # 再下一版（測試更新失敗後重試）
New-ReleaseZip $info.mismatch $info.next              # 檔名和內容版本不符
New-ReleaseZip $info.broken $info.broken $false       # 沒有 app 資料夾
New-ReleaseZip "0.0.1" "0.0.1"                        # 比目前舊
$info.zips = $zips

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
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item -Recurse -Path "$base\*" -Destination $dir
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
