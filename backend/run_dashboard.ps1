# Runs the local dashboard with no console. Started by run_dashboard_hidden.vbs,
# which run.ps1 calls; stop it with stop.ps1 in the repo root.
Set-Location "$PSScriptRoot"
New-Item -ItemType Directory -Force "$PSScriptRoot\..\data" | Out-Null
$log = (Resolve-Path "$PSScriptRoot\..\data").Path + "\dashboard.log"
Set-Content -Path $log -Value "----- started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -----" -Encoding ascii
$env:PYTHONUNBUFFERED = "1"
cmd /c "python -m pip install --quiet --disable-pip-version-check -r requirements.txt >> `"$log`" 2>&1"
cmd /c "python app.py >> `"$log`" 2>&1"
