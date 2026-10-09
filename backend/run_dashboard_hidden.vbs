' Starts the local dashboard with no window at all (run.ps1 calls this).
' Same reason as run_publish_hidden.vbs: wscript.exe isn't a console program,
' so PowerShell started from here with window style 0 never shows a console,
' and python inherits that hidden console. Doesn't wait for it to finish.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & here & "\run_dashboard.ps1"""
shell.Run cmd, 0, False
