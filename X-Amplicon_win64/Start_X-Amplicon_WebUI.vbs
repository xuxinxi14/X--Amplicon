Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = root & "\Start_X-Amplicon_WebUI.ps1"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """ -ManagedApp"
shell.Run command, 0, False
