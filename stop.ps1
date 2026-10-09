# Stops the local dashboard started by run.ps1. Only touches the process
# listening on port 5057 and the chain that launched it (python app.py, its
# reloader, the hidden PowerShell, or an old-style run.ps1 window), never
# other python.exe processes such as a publish run.
$conns = Get-NetTCPConnection -LocalPort 5057 -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "The dashboard isn't running."
    exit 0
}
foreach ($c in $conns) {
    $top = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)"
    if (-not $top) { continue }
    while ($true) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($top.ParentProcessId)"
        if ($parent -and $parent.CommandLine -match 'app\.py|run_dashboard\.ps1|\\run\.ps1') { $top = $parent } else { break }
    }
    taskkill /T /F /PID $top.ProcessId | Out-Null
}
Write-Host "Dashboard stopped."
