# Starts the local dashboard (http://127.0.0.1:5057) in the background with no
# window, then opens it in the browser. Stop it with .\stop.ps1.
# Its output goes to data\dashboard.log (started fresh on every launch).
$listening = { Get-NetTCPConnection -LocalPort 5057 -State Listen -ErrorAction SilentlyContinue }
if (& $listening) {
    Write-Host "The dashboard is already running."
} else {
    Write-Host "Starting SA Basic Fuel Price Preview in the background ..."
    Start-Process wscript.exe -ArgumentList "`"$PSScriptRoot\backend\run_dashboard_hidden.vbs`""
    for ($i = 0; $i -lt 90 -and -not (& $listening); $i++) { Start-Sleep -Seconds 1 }
    if (-not (& $listening)) {
        Write-Host "It didn't start within 90 seconds; see data\dashboard.log."
        exit 1
    }
}
Start-Process "http://127.0.0.1:5057"
Write-Host "Running at http://127.0.0.1:5057 (no window). Stop it with .\stop.ps1"
