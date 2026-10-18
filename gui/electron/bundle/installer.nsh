; electron-builder の NSIS に足す処理（package.json の build.nsis.include）。中身は install_cli.py。

!macro customInstall
  DetailPrint "ECOBuild を準備しています…"
  nsExec::ExecToLog '"$INSTDIR\resources\python\python.exe" "$INSTDIR\resources\setup\install_cli.py" install "$INSTDIR"'
  Pop $0
  StrCmp $0 "0" +2 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "ECOBuild の準備に失敗しました（$0）。もう一度インストールしてください。"
!macroend

!macro customUnInstall
  nsExec::ExecToLog '"$INSTDIR\resources\python\python.exe" "$INSTDIR\resources\setup\install_cli.py" uninstall "$INSTDIR"'
  Pop $0
!macroend
