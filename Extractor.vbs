' Arrancador del Extractor de matriz (doble clic).
' Se actualiza solo al abrir y se cierra al cerrar la ventana. Sin consola.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
raiz = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = raiz & "\extractor-matriz\Extractor.ps1"
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, False
