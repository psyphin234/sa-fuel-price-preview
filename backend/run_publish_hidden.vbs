' Task Scheduler entry point: runs run_publish.ps1 with no window at all.
' powershell.exe -WindowStyle Hidden still flashes a console (and steals focus)
' because Windows creates the window before PowerShell can hide it; wscript.exe
' is not a console program, so starting PowerShell from here with window style 0
' never shows one. python and git inherit that hidden console.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & here & "\run_publish.ps1"""
WScript.Quit shell.Run(cmd, 0, True)
