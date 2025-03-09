@echo off
echo Starting Steam Game Unlocker...

rem 判断是否有清除缓存参数
if "%1"=="clean" (
    echo Cleaning cache files...
    if exist branch_cache.json del /f branch_cache.json
    echo Cache cleaned.
    echo.
)

python app1.py
pause 