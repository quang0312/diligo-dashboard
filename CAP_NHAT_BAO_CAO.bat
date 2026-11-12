@echo off
chcp 65001 >nul
set "SCRIPT=%~dp0Diligo_Auto_Dashboard.py"

python --version >nul 2>&1
if %errorlevel%==0 (
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=py"
)

%PYTHON_CMD% "%SCRIPT%" --input "D:\Data_Input" --output "D:\Diligo_Dashboard_Output"
if errorlevel 1 (
  echo.
  echo Co loi. Chup man hinh cua so nay de gui ho tro.
  echo Neu bao thieu baseline_v25.json: chep file nay tu thu muc V39 vao thu muc hien tai roi chay lai.
  pause
  exit /b 1
)

echo.
echo DA CAP NHAT XONG: D:\Diligo_Dashboard_Output\index.html
echo KHO LICH SU: D:\Diligo_Dashboard_Output\HistoryStore_v2.json
echo Sau khi da thay XONG, ban co the xoa file raw trong Data_Input neu muon.
echo KHONG XOA HistoryStore_v2.json.
start "" "D:\Diligo_Dashboard_Output\index.html"
pause
