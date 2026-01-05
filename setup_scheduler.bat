@echo off
echo ========================================
echo   V6 Windows Task Scheduler Setup
echo ========================================
echo.
echo 이 스크립트는 관리자 권한이 필요합니다.
echo.

REM 오전 6시 서버 시작 작업 등록
echo [1/2] 오전 6:00 서버 시작 작업 등록 중...
schtasks /create /tn "V6_Server_Start" /tr "C:\Users\DSAI\Desktop\매장자동화\run_v6_server.bat" /sc daily /st 06:00 /f /rl highest
if %errorlevel% equ 0 (
    echo     ✅ 시작 작업 등록 완료
) else (
    echo     ❌ 시작 작업 등록 실패 - 관리자 권한으로 실행하세요
)

echo.

REM 오후 5시 서버 종료 작업 등록
echo [2/2] 오후 5:00 서버 종료 작업 등록 중...
schtasks /create /tn "V6_Server_Stop" /tr "C:\Users\DSAI\Desktop\매장자동화\stop_v6_server.bat" /sc daily /st 17:00 /f /rl highest
if %errorlevel% equ 0 (
    echo     ✅ 종료 작업 등록 완료
) else (
    echo     ❌ 종료 작업 등록 실패 - 관리자 권한으로 실행하세요
)

echo.
echo ========================================
echo   등록된 작업 확인
echo ========================================
schtasks /query /tn "V6_Server_Start" /fo list 2>nul
schtasks /query /tn "V6_Server_Stop" /fo list 2>nul

echo.
echo 완료! 매일 오전 6시에 자동 시작, 오후 5시에 자동 종료됩니다.
pause
