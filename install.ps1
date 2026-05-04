# =============================================================
# 🍱 식품안전나라 통합 도구 - 원라이너 설치/실행 스크립트
# =============================================================
# 사용법: PowerShell에서
#   iwr https://raw.githubusercontent.com/ryujisung007/0227total/main/install.ps1 | iex
# =============================================================

$ErrorActionPreference = "Stop"

# 한글 깨짐 방지 (PowerShell 콘솔 인코딩 UTF-8로)
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch {}

# 사용자가 자기 repo에 맞게 수정해야 할 부분
$RepoOwner = "ryujisung007"
$RepoName  = "0227total"
$Branch    = "main"

Write-Host @"

============================================================
  🍱 식품안전나라 통합 도구 - 자동 설치/실행
============================================================
"@ -ForegroundColor Cyan

# -----------------------------------------------------------
# 1. Python 설치 확인
# -----------------------------------------------------------
Write-Host "`n[1/5] Python 설치 확인" -ForegroundColor Yellow
try {
    $pyVersion = & python --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "python not callable" }
    Write-Host "  ✅ $pyVersion" -ForegroundColor Green
} catch {
    Write-Host @"

  ❌ Python이 설치되어 있지 않습니다.

  다음 중 하나로 설치 후 PowerShell 재시작 → 이 명령어 다시 실행:

  방법 1) python.org에서 다운로드 (가장 안전)
          https://www.python.org/downloads/
          [Add python.exe to PATH] 체크박스 반드시 체크!

  방법 2) winget (Windows 10/11):
          winget install Python.Python.3.12

  방법 3) Microsoft Store에서 'Python' 검색 후 설치

"@ -ForegroundColor Red
    Read-Host "엔터를 눌러 종료"
    exit 1
}

# -----------------------------------------------------------
# 2. 설치 디렉토리 결정
# -----------------------------------------------------------
$installDir = Join-Path $env:USERPROFILE "food_safety_app"
Write-Host "`n[2/5] 설치 디렉토리: $installDir" -ForegroundColor Yellow

$needDownload = $true
if (Test-Path $installDir) {
    $choice = Read-Host "  이미 설치되어 있습니다. (U)pdate / (R)un / (C)ancel"
    switch ($choice.ToUpper()) {
        "U" {
            Write-Host "  최신 버전으로 업데이트..." -ForegroundColor Cyan
            Remove-Item -Recurse -Force $installDir
            $needDownload = $true
        }
        "R" {
            Write-Host "  기존 설치로 바로 실행" -ForegroundColor Green
            $needDownload = $false
        }
        default {
            Write-Host "  취소" -ForegroundColor Red
            exit 0
        }
    }
}

# -----------------------------------------------------------
# 3. GitHub에서 다운로드 + 압축 해제
# -----------------------------------------------------------
if ($needDownload) {
    Write-Host "`n[3/5] GitHub에서 다운로드 중..." -ForegroundColor Yellow
    $zipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
    $zipFile = Join-Path $env:TEMP "food_safety_$(Get-Random).zip"
    $tempExtract = Join-Path $env:TEMP "food_safety_extract_$(Get-Random)"

    try {
        Write-Host "  URL: $zipUrl"
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile -UseBasicParsing
        Write-Host "  ✅ 다운로드 완료" -ForegroundColor Green

        Write-Host "  압축 해제 중..."
        Expand-Archive -Path $zipFile -DestinationPath $tempExtract -Force

        # GitHub zip은 {RepoName}-{Branch} 형태 폴더로 들어감
        $extractedDir = Get-ChildItem $tempExtract -Directory | Select-Object -First 1
        if (-not $extractedDir) { throw "압축 해제 결과가 비어있습니다" }
        Move-Item $extractedDir.FullName $installDir
        Write-Host "  ✅ 설치: $installDir" -ForegroundColor Green
    }
    finally {
        Remove-Item $zipFile -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue
    }
}

Set-Location $installDir

# -----------------------------------------------------------
# 4. Python 패키지 설치
# -----------------------------------------------------------
Write-Host "`n[4/5] Python 패키지 설치 (requirements.txt)" -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠️ pip install 일부 실패 - 그래도 계속" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ 완료" -ForegroundColor Green
    }
} else {
    Write-Host "  ⚠️ requirements.txt 없음 - 핵심 패키지만 설치" -ForegroundColor Yellow
    python -m pip install streamlit playwright pandas openpyxl --quiet
}

# -----------------------------------------------------------
# 5. Chromium 확인 (없으면 설치)
# -----------------------------------------------------------
Write-Host "`n[5/5] Playwright Chromium 확인" -ForegroundColor Yellow
$chromiumCache = Join-Path $env:USERPROFILE "AppData\Local\ms-playwright"
$hasChromium = $false
if (Test-Path $chromiumCache) {
    $hasChromium = (Get-ChildItem $chromiumCache -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -like "chromium*" -or $_.Name -like "chrome-*" }).Count -gt 0
}
if ($hasChromium) {
    Write-Host "  ✅ Chromium 이미 설치됨" -ForegroundColor Green
} else {
    Write-Host "  Chromium 설치 중 (1회, 약 1~2분)..." -ForegroundColor Cyan
    python -m playwright install chromium
    Write-Host "  ✅ 완료" -ForegroundColor Green
}

# -----------------------------------------------------------
# 실행 - 사용 가능한 포트 자동 탐색
# -----------------------------------------------------------
function Test-PortAvailable {
    param([int]$Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback, $Port
        )
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

$port = 8501
foreach ($p in @(8501, 8502, 8503, 8504, 8505, 8510)) {
    if (Test-PortAvailable -Port $p) {
        $port = $p
        break
    }
}

Write-Host @"

============================================================
  🚀 Streamlit 앱 실행 중...
============================================================
  포트: $port (자동 선택)
  브라우저가 자동으로 열립니다.
  안 열리면: http://localhost:$port

  종료: 이 PowerShell 창에서 Ctrl+C
============================================================
"@ -ForegroundColor Green

python -m streamlit run app.py --server.port $port
