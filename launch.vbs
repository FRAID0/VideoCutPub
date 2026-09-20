Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

If fso.FileExists(strPath & "\venv\Scripts\pythonw.exe") Then
    WshShell.Run """" & strPath & "\venv\Scripts\pythonw.exe"" main.py", 0, False
Else
    WshShell.Run "cmd /c launch.bat", 0, False
End If
