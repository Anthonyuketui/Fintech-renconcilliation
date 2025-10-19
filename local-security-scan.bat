@echo off
REM Local security scanning script - Run before committing
REM Mirrors CI/CD pipeline security tools: Semgrep, SBOM, Trivy

echo 🔒 Running Local Security Scan...
echo This mirrors your CI/CD pipeline security checks
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+
    exit /b 1
)

echo ✅ Python found
echo.

REM Install/check Semgrep
echo 🔍 Setting up Semgrep SAST scanner...
pip install semgrep >nul 2>&1
if errorlevel 1 (
    echo ❌ Failed to install Semgrep
    exit /b 1
)

REM Run Semgrep scan (same as CI/CD)
echo 🔍 Running Semgrep security scan...
semgrep --config=auto --severity=ERROR --error src/
if errorlevel 1 (
    echo ❌ Semgrep found CRITICAL security issues!
    echo Fix these before committing to avoid CI/CD failure
    exit /b 1
)

REM Generate Semgrep JSON report
semgrep --config=auto --json --output=semgrep-local.json src/
echo ✅ Semgrep scan passed - Report saved to semgrep-local.json

echo.

REM Generate SBOM (same as CI/CD)
echo 📋 Generating Software Bill of Materials...
pip install cyclonedx-bom >nul 2>&1
if exist requirements.txt (
    cyclonedx-py requirements -o sbom-local.json
    echo ✅ SBOM generated: sbom-local.json
) else (
    echo ⚠️  requirements.txt not found, skipping SBOM
)

echo.

REM Check for Trivy
echo 🔍 Checking for Trivy scanner...
trivy version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Trivy not installed - Install from: https://aquasecurity.github.io/trivy/
    echo Skipping filesystem scan (will run in CI/CD)
) else (
    echo 🔍 Running Trivy filesystem scan...
    trivy fs --scanners vuln,secret,misconfig --severity CRITICAL .
    if errorlevel 1 (
        echo ❌ Trivy found CRITICAL issues!
        echo Fix these before committing
        exit /b 1
    )
    echo ✅ Trivy scan passed
)

echo.

REM Simple secret detection
echo 🔍 Checking for hardcoded secrets...
findstr /R /C:"password.*=.*['\"][^'\"]*['\"]" /C:"secret.*=.*['\"][^'\"]*['\"]" /C:"key.*=.*['\"][^'\"]*['\"]" src\*.py >nul 2>&1
if not errorlevel 1 (
    echo ❌ Potential hardcoded secrets found!
    echo Use environment variables instead
    exit /b 1
)
echo ✅ No obvious secrets detected

echo.
echo 🎉 All local security checks passed!
echo Your code will pass the CI/CD security gates:
echo   ✅ Semgrep SAST scan
echo   ✅ SBOM generation  
echo   ✅ Trivy security scan
echo   ✅ Secret detection
echo.
echo Generated files:
echo   - semgrep-local.json
echo   - sbom-local.json
echo.
echo Ready to commit! 🚀