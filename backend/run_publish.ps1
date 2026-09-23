# Wrapper for Task Scheduler: runs publish.py with the right working directory
# and logs output, since Task Scheduler runs with no console to see it.
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot"
$logFile = "$PSScriptRoot\..\data\publish.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "----- $timestamp -----" -Encoding utf8
try {
    $output = & "C:\Users\Kevin\AppData\Local\Python\pythoncore-3.14-64\python.exe" publish.py 2>&1 | Out-String
    Add-Content -Path $logFile -Value $output -Encoding utf8
    Write-Output $output
} catch {
    Add-Content -Path $logFile -Value "ERROR: $_" -Encoding utf8
}
