' AGENTS HQ — double-click to start like a normal app.
' Starts the local server hidden and opens a dedicated Edge/Chrome app window.
' Close the app window to stop the server (including schedules).

Option Explicit
Dim sh, fso, root, ps1, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = root & "\launch\run-app.ps1"

If Not fso.FileExists(ps1) Then
  MsgBox "Could not find launch\run-app.ps1 next to AGENTS HQ.vbs.", vbCritical, "AGENTS HQ"
  WScript.Quit 1
End If

cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
sh.CurrentDirectory = root
sh.Run cmd, 0, False
