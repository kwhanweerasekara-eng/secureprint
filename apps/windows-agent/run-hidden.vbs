' Launches agent.bat with no visible console window - use this (instead of
' agent.bat directly) for a shortcut in shell:startup, so the agent starts
' silently at logon. The tray icon and toast notifications still work
' normally; only the console window is hidden.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run """" & folder & "\agent.bat""", 0, False
