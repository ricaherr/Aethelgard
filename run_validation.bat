@echo off
cd /d "C:\Users\Jose Herrera\Documents\Proyectos\Aethelgard"

echo ======================================== > validation_result.txt
echo FASE 1 VALIDATION RESULTS >> validation_result.txt
echo ======================================== >> validation_result.txt
echo. >> validation_result.txt

echo [1/3] Git Status... >> validation_result.txt
git status --short >> validation_result.txt 2>&1
echo. >> validation_result.txt

echo [2/3] Running Tests... >> validation_result.txt
python -m pytest tests\test_position_manager_regime.py -v --tb=short >> validation_result.txt 2>&1
set TEST_RESULT=%ERRORLEVEL%
echo Test Exit Code: %TEST_RESULT% >> validation_result.txt
echo. >> validation_result.txt

echo [3/3] Running validate_all... >> validation_result.txt
python scripts\validate_all.py >> validation_result.txt 2>&1
set VALIDATE_RESULT=%ERRORLEVEL%
echo Validate Exit Code: %VALIDATE_RESULT% >> validation_result.txt
echo. >> validation_result.txt

echo ======================================== >> validation_result.txt
if %TEST_RESULT%==0 if %VALIDATE_RESULT%==0 (
    echo STATUS: ALL VALIDATIONS PASSED >> validation_result.txt
) else (
    echo STATUS: SOME VALIDATIONS FAILED >> validation_result.txt
)
echo ======================================== >> validation_result.txt

type validation_result.txt
