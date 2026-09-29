<#
    LangChain 에이전트 실습 환경 자동 구축 스크립트
    ---------------------------------------------
    이 파일은 "설치하기.bat" 을 더블클릭하면 자동으로 실행됩니다.
    관리자 권한은 필요하지 않습니다.

    하는 일
      1. Python 3.12 설치 (없을 때만)
      2. 이 폴더 안에 .venv 라는 전용 파이썬 환경 만들기
      3. 실습에 필요한 라이브러리 설치 (requirements.txt)
      4. 주피터 노트북에서 쓸 커널 등록
      5. VS Code + 파이썬/주피터/Continue 확장 설치

    이미 되어 있는 단계는 자동으로 건너뜁니다. 여러 번 실행해도 안전합니다.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

# 한글이 깨지지 않도록 콘솔 출력 인코딩을 UTF-8 로 맞춘다
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$Root       = $PSScriptRoot
$VenvDir    = Join-Path $Root '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$Req        = Join-Path $Root 'requirements.txt'

$PythonVersion   = '3.12.10'
$PythonInstaller = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"

# ---------------------------------------------------------------- 출력 도우미

function Write-Step  { param($n, $msg) Write-Host ""; Write-Host "[$n/5] $msg" -ForegroundColor Cyan }
function Write-Info  { param($msg)     Write-Host "      $msg" -ForegroundColor Gray }
function Write-Ok    { param($msg)     Write-Host "      $msg" -ForegroundColor Green }
function Write-Warn2 { param($msg)     Write-Host "      $msg" -ForegroundColor Yellow }

# 현재 창의 PATH 를 최신 상태로 갱신한다 (재부팅 없이 방금 설치한 프로그램을 쓰기 위해)
function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $extra   = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\Scripts'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps')
    )
    $parts = @($machine, $user) + $extra | Where-Object { $_ }
    $env:Path = ($parts -join ';')
}

# ------------------------------------------------------- 1단계: Python 3.12

function Test-Python312 {
    # 이 함수 안에서는 오류가 나도 스크립트를 멈추지 않는다 (단순 존재 확인이므로)
    $ErrorActionPreference = 'Continue'
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { return $false }
    try {
        & py -3.12 -c "import sys" | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Install-Python312 {
    # (1) winget 으로 시도
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "winget 으로 Python $PythonVersion 설치를 시도합니다. (몇 분 걸릴 수 있습니다)"
        $ErrorActionPreference = 'Continue'
        & winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
        $ErrorActionPreference = 'Stop'
        Update-SessionPath
        if (Test-Python312) { return }
        Write-Warn2 "winget 설치가 되지 않았습니다. 공식 설치파일로 다시 시도합니다."
    } else {
        Write-Info "이 PC 에는 winget 이 없습니다. 공식 설치파일을 내려받습니다."
    }

    # (2) python.org 공식 설치파일로 폴백
    $dest = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    Write-Info "python.org 에서 설치파일을 내려받는 중입니다..."
    Invoke-WebRequest -Uri $PythonInstaller -OutFile $dest -UseBasicParsing

    Write-Info "설치 중입니다. 설치 창이 잠깐 떠도 끄지 마세요."
    $opts = @('/passive', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'Include_test=0')
    $proc = Start-Process -FilePath $dest -ArgumentList $opts -Wait -PassThru
    Update-SessionPath

    if (-not (Test-Python312)) {
        throw ("Python 3.12 설치에 실패했습니다. (설치 프로그램 종료 코드: " + $proc.ExitCode + ")`n" +
               "      https://www.python.org/downloads/release/python-31210/ 에서`n" +
               "      'Windows installer (64-bit)' 를 직접 받아 설치한 뒤, 이 스크립트를 다시 실행해 주세요.")
    }
}

# ------------------------------------------- 5단계: VS Code 기본 인터프리터

function Set-VSCodeInterpreter {
    $settingsDir  = Join-Path $env:APPDATA 'Code\User'
    $settingsFile = Join-Path $settingsDir 'settings.json'

    if (Test-Path $settingsFile) {
        $raw = [IO.File]::ReadAllText($settingsFile)
        if ($raw.Trim()) {
            # 주석이 들어 있는 settings.json 은 PowerShell 이 읽지 못하므로 그 경우 예외로 넘긴다
            $settings = $raw | ConvertFrom-Json
        } else {
            $settings = New-Object PSObject
        }
        Copy-Item $settingsFile "$settingsFile.bak" -Force
    } else {
        New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
        $settings = New-Object PSObject
    }

    $settings | Add-Member -NotePropertyName 'python.defaultInterpreterPath' -NotePropertyValue $VenvPython -Force
    $settings | Add-Member -NotePropertyName 'python.terminal.activateEnvironment' -NotePropertyValue $true -Force

    # BOM 없는 UTF-8 로 저장 (VS Code 설정 파일 형식)
    $json = $settings | ConvertTo-Json -Depth 50
    [IO.File]::WriteAllText($settingsFile, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok "VS Code 기본 파이썬을 .venv 로 지정했습니다. (터미널에서 streamlit 바로 사용 가능)"
}

# ------------------------------------------------------------------ 본 작업

try {

Write-Host ""
Write-Host "==================================================" -ForegroundColor White
Write-Host "  LangChain 에이전트 실습 환경을 준비합니다" -ForegroundColor White
Write-Host "  (관리자 권한 없이 진행됩니다. 창을 끄지 마세요)" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor White
Write-Info "설치 위치: $Root"

if (-not (Test-Path $Req)) {
    throw "requirements.txt 를 찾을 수 없습니다. setup.ps1 과 같은 폴더에 있어야 합니다."
}

# --- 1/5 ------------------------------------------------------------------
Write-Step 1 "Python 3.12 확인"
Update-SessionPath
if (Test-Python312) {
    Write-Ok "이미 설치되어 있습니다. 그대로 사용합니다."
} else {
    Write-Info "Python 3.12 가 없습니다. 지금 설치합니다."
    Install-Python312
    Write-Ok "Python 3.12 설치 완료."
}

# --- 2/5 ------------------------------------------------------------------
Write-Step 2 "실습 전용 파이썬 환경(.venv) 만들기"
if (Test-Path $VenvPython) {
    Write-Ok "이미 만들어져 있습니다. 그대로 사용합니다."
} else {
    & py -3.12 -m venv "$VenvDir"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        throw ".venv 폴더를 만들지 못했습니다. 이 폴더가 OneDrive 동기화 중이거나 쓰기 권한이 없을 수 있습니다."
    }
    Write-Ok ".venv 생성 완료."
}

# --- 3/5 ------------------------------------------------------------------
Write-Step 3 "실습에 필요한 라이브러리 설치"
Write-Info "인터넷 속도에 따라 3~10분 정도 걸립니다. 그냥 두세요."

& $VenvPython -m pip install --upgrade pip --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    throw "pip 을 최신으로 올리지 못했습니다. 인터넷 연결(또는 사내 프록시)을 확인해 주세요."
}

& $VenvPython -m pip install -r "$Req" --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    throw ("라이브러리 설치에 실패했습니다.`n" +
           "      사내 네트워크에서 PyPI(pypi.org) 접속이 막혀 있을 수 있습니다.`n" +
           "      다른 네트워크(개인 핫스팟 등)로 바꿔서 다시 실행해 보시고,`n" +
           "      그래도 안 되면 위에 나온 메시지를 강사에게 보여 주세요.")
}
Write-Ok "라이브러리 설치 완료."

# --- 4/5 ------------------------------------------------------------------
Write-Step 4 "주피터 노트북 커널 등록"
& $VenvPython -m ipykernel install --user --name langchain-agent --display-name "Python (LangChain Agent)"
if ($LASTEXITCODE -ne 0) {
    throw "주피터 커널 등록에 실패했습니다."
}
Write-Ok "커널 이름: Python (LangChain Agent)"

# --- 5/5 ------------------------------------------------------------------
# 이 단계는 실패해도 실습에 치명적이지 않으므로 경고만 남기고 계속 진행한다.
Write-Step 5 "VS Code 및 확장 설치"
try {
    $ErrorActionPreference = 'Continue'

    if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Info "VS Code 를 설치합니다. (몇 분 걸릴 수 있습니다)"
            & winget install --id Microsoft.VisualStudioCode -e --scope user --silent --accept-package-agreements --accept-source-agreements
        } else {
            Write-Warn2 "winget 이 없어 VS Code 를 자동 설치할 수 없습니다."
            Write-Warn2 "https://code.visualstudio.com 에서 직접 내려받아 설치해 주세요."
        }
        Update-SessionPath
        $codeBins = @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\bin'),
            (Join-Path $env:ProgramFiles 'Microsoft VS Code\bin')
        )
        foreach ($bin in $codeBins) {
            if (Test-Path $bin) { $env:Path = $env:Path + ';' + $bin }
        }
    } else {
        Write-Info "VS Code 가 이미 설치되어 있습니다."
    }

    if (Get-Command code -ErrorAction SilentlyContinue) {
        Write-Info "파이썬 / 주피터 / Continue 확장을 설치합니다."
        & code --install-extension ms-python.python --force
        & code --install-extension ms-toolsai.jupyter --force
        & code --install-extension Continue.continue --force
        Write-Ok "VS Code 준비 완료."
    } else {
        Write-Warn2 "VS Code 명령을 찾지 못했습니다. 확장은 VS Code 를 연 뒤 직접 설치해 주세요."
        Write-Warn2 "(왼쪽 확장 아이콘 -> 'Python', 'Jupyter', 'Continue' 검색 후 설치)"
    }

    $ErrorActionPreference = 'Stop'
} catch {
    $ErrorActionPreference = 'Stop'
    Write-Warn2 "VS Code 설치 단계에서 문제가 있었지만, 파이썬 실습 환경은 정상입니다."
    Write-Warn2 "( $($_.Exception.Message) )"
}

# 실습 폴더(하위 폴더 포함)를 어디서 열어도 .venv 를 쓰도록 VS Code 기본 인터프리터를 지정한다
try {
    Set-VSCodeInterpreter
} catch {
    Write-Warn2 "VS Code 기본 파이썬 설정을 바꾸지 못했습니다. ( $($_.Exception.Message) )"
    Write-Warn2 "VS Code 에서 Ctrl+Shift+P -> 'Python: Select Interpreter' -> 아래 경로를 직접 선택해 주세요."
    Write-Warn2 "$VenvPython"
}

# --- 마무리 ---------------------------------------------------------------
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  설치가 끝났습니다!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  다음 3가지만 하시면 실습 준비 완료입니다." -ForegroundColor White
Write-Host ""
Write-Host "  1) 이 폴더(agent_basic)를 VS Code 로 여세요."
Write-Host "     폴더에서 마우스 오른쪽 클릭 -> 'Code(으)로 열기'"
Write-Host ""
Write-Host "  2) .env.sample 파일을 복사해서 이름을 .env 로 바꾸고,"
Write-Host "     강사가 알려준 API 키와 주소를 붙여 넣으세요."
Write-Host ""
Write-Host "  3) 노트북(.ipynb)을 열고 오른쪽 위 '커널 선택'에서"
Write-Host "     'Python (LangChain Agent)' 를 고르세요."
Write-Host ""

} catch {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "  설치를 끝내지 못했습니다" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "  이 창을 그대로 두고 강사에게 보여 주세요." -ForegroundColor Yellow
    Write-Host ""
}

Read-Host "엔터 키를 누르면 창이 닫힙니다"
