; TransformBro — скрипт установщика для NSIS 3
; Сборка: makensis packaging\TransformBro.nsi   (или python packaging\build_release.py)

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME    "TransformBro"
!define APP_VERSION "1.1.0"
!define APP_PUB     "Den4dev"
!define EXE_NAME    "TransformBro.exe"
!define UNREG_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

!ifndef INSTALL_SIZE_KB
  !define INSTALL_SIZE_KB 0
!endif

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\release\TransformBro-${APP_VERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "Path"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ShowInstDetails show
ShowUninstDetails show
Unicode true
XPStyle on

!define MUI_ICON "..\assets\TransformBro.ico"
!define MUI_UNICON "..\assets\TransformBro.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Установка ${APP_NAME} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Конвертер изображений, документов, текста, аудио и видео.$\r$\n$\r$\nFFmpeg уже в комплекте — доустанавливать кодеки не нужно.$\r$\n$\r$\nПрограмма ставится в ваш профиль, права администратора не требуются."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить ${APP_NAME} сейчас"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\ПРОЧТИ_МЕНЯ.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Открыть инструкции"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "English"

LangString DESC_SecMain    ${LANG_RUSSIAN} "Сама программа и FFmpeg."
LangString DESC_SecMain    ${LANG_ENGLISH} "The application and FFmpeg."
LangString DESC_SecDesktop ${LANG_RUSSIAN} "Ярлык на рабочем столе."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Desktop shortcut."
LangString DESC_SecOpen    ${LANG_RUSSIAN} "TransformBro появится в списке «Открыть с помощью» для поддерживаемых файлов."
LangString DESC_SecOpen    ${LANG_ENGLISH} "Add TransformBro to the $\"Open with$\" menu."

Section "${APP_NAME} (обязательно)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "..\dist\${EXE_NAME}"
  File /r "..\payload\*.*"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Инструкции.lnk" "$INSTDIR\ПРОЧТИ_МЕНЯ.txt"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Удалить ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${UNREG_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNREG_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNREG_KEY}" "Publisher" "${APP_PUB}"
  WriteRegStr HKCU "${UNREG_KEY}" "DisplayIcon" "$INSTDIR\${EXE_NAME}"
  WriteRegStr HKCU "${UNREG_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNREG_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNREG_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNREG_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNREG_KEY}" "NoRepair" 1
  !if ${INSTALL_SIZE_KB} != 0
    WriteRegDWORD HKCU "${UNREG_KEY}" "EstimatedSize" ${INSTALL_SIZE_KB}
  !endif

  WriteRegStr HKCU "Software\${APP_NAME}" "Path" "$INSTDIR"
  WriteRegStr HKCU "Software\${APP_NAME}" "Version" "${APP_VERSION}"
SectionEnd

Section /o "Ярлык на рабочем столе" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
SectionEnd

Section "«Открыть с помощью ${APP_NAME}»" SecOpen
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}" "FriendlyAppName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\shell\open\command" "" '"$INSTDIR\${EXE_NAME}" "%1"'
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".jpg" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".jpeg" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".png" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".webp" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".bmp" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".gif" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".tif" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".pdf" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".doc" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".docx" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".txt" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".mp4" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".mkv" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".avi" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".mp3" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".wav" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE_NAME}\SupportedTypes" ".flac" ""
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_SecMain)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecOpen}    $(DESC_SecOpen)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  ${If} ${FileExists} "$INSTDIR\${EXE_NAME}"
    RMDir /r "$INSTDIR"
  ${EndIf}
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Инструкции.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Удалить ${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  DeleteRegKey HKCU "${UNREG_KEY}"
  DeleteRegKey HKCU "Software\Classes\Applications\${EXE_NAME}"
  DeleteRegKey HKCU "Software\${APP_NAME}"
SectionEnd
