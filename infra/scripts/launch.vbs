Set objShell = CreateObject("WScript.Shell")
' 0 Parametresi pencereyi tamamen gizli (hidden) modda açar
objShell.Run "powershell.exe -ExecutionPolicy Bypass -File scripts\launcher.ps1", 0, False
