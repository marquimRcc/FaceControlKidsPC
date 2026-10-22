Option Explicit
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "cmd.exe /d /c ""C:\ProgramData\FaceKids\iniciar-filhos-agent.bat""", 0, False
