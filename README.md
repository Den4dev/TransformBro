# TransformBro

Конвертер файлов в одном окне: изображения, PDF, документы, текст, аудио и видео.
Windows 10/11 x64. Работает без интернета; FFmpeg уже в комплекте релиза.

## Что умеет

| Категория | Вход | Действия |
|---|---|---|
| Изображения | JPG, JPEG, PNG, WEBP, BMP, GIF, TIFF, ICO, AVIF | в WEBP / PNG / JPG / BMP / TIFF / ICO, сжатие для Web (75%), уменьшение до 1920 и 1080 px, удаление EXIF/GPS |
| PDF | PDF | извлечение текста, страницы в PNG |
| Документы | DOC, DOCX, DOCM, ODT, RTF, HTML | извлечение текста; при наличии MS Word — DOCX и PDF с вёрсткой |
| Текст | TXT, MD, CSV, JSON, LOG, XML, SRT, INI, YAML, CFG, NFO, TEX | в PDF, DOCX, HTML (кириллица сохраняется) |
| Видео | MP4, MKV, AVI, MOV, WEBM, WMV, M4V, FLV, MPG, MPEG, TS, MTS, M2TS, 3GP, OGV, VOB, F4V | извлечение аудио (MP3, WAV, FLAC, M4A, OGG, OPUS, AAC), сжатие в MP4 (H.264), в AVI, в WEBM (VP9), в MKV без перекодирования, 720p / 480p, GIF, кадры в PNG |
| Аудио | MP3, WAV, FLAC, OGG, M4A, AAC, OPUS, WMA, AIFF, AMR, AC3, MKA, ALAC, APE, WV | конвертация между форматами, выравнивание громкости (Loudnorm) |

Файлы можно бросать в окно по одному или целой папкой (скрытые файлы пропускаются,
лимит 500 за раз). Результат кладётся рядом с исходником, ничего не перезаписывается.

## Установка

### Из релиза (то, что нужно большинству)

1. Откройте страницу релизов: `https://github.com/Den4dev/TransformBro/releases/latest`.
2. Скачайте `TransformBro-<версия>-Setup.exe` — в релизе один файл. Ставится в
   `C:\Users\<вы>\AppData\Local\Programs\TransformBro`, права администратора не нужны,
   создаёт ярлык в меню «Пуск», uninstaller появляется в «Параметры → Приложения».
   Поддерживается тихая установка: `TransformBro-<версия>-Setup.exe /S`.
   Нужен portable-вариант без установки — соберите его локально (`Собрать_Релиз.bat`),
   он положит рядом `TransformBro-<версия>-win64.zip` и `-win64-lite.zip`.
3. При первом запуске SmartScreen может написать «Неизвестный издатель» — сборка не
   подписана сертификатом. Нажмите «Подробнее» → «Выполнить в любом случае».

### Из исходников

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv\Scripts\python.exe TransformBro.py            :: запуск
.venv\Scripts\python.exe -m PyInstaller --noconfirm TransformBro.spec   :: exe в dist\
```

Собирать нужно из чистого `.venv`: системный Python с ML-пакетами увеличивает exe
в разы. Для видео и аудио нужен `ffmpeg.exe` в PATH или рядом с `TransformBro.exe`.

## Как собрать релиз локально

```bat
.venv\Scripts\python.exe _make_icon.py                      :: иконка (нужна один раз)
.venv\Scripts\python.exe -m PyInstaller --noconfirm TransformBro.spec
copy /y dist\TransformBro.exe TransformBro.exe                    :: exe в корень проекта
.venv\Scripts\python.exe packaging\build_release.py --skip-build
```

`build_release.py` скачивает официальный essentials-архив FFmpeg (~30 МБ, кэш в
`release\ffmpeg-cache`) и кладёт `ffmpeg.exe` в `payload/`, собирает установщик через
NSIS (`tools\nsis-3.12\makensis.exe` или из `Program Files (x86)\NSIS`) и складывает
в `release/`: `TransformBro-<версия>-Setup.exe`, `TransformBro-<версия>-win64.zip`,
`TransformBro-<версия>-win64-lite.zip`, `RELEASE_NOTES.md` с SHA-256.
Флаги: `--no-ffmpeg` — пакет без кодеков, `--system-ffmpeg` — взять ffmpeg.exe из PATH
(учтите: локальная full-сборка весит ~214 МБ и раздувает релиз).

## Как выложить релиз на GitHub

```bat
git init && git add -A && git commit -m "TransformBro 1.1.0"
git remote add origin https://github.com/<логин>/TransformBro.git
git push -u origin main
git tag v1.1.0 && git push origin v1.1.0
```

Тег `v*` запускает `.github/workflows/release.yml`: CI собирает exe, скачивает
FFmpeg, делает установщик и публикует его в релиз. Локальные файлы из `release/`
при этом не нужны.

## Структура

```
TransformBro.py                 приложение (обработчики, GUI, FFmpeg/Word/PDF)
TransformBro.spec               сборка PyInstaller (onefile, иконка, версия)
assets/TransformBro.ico         иконка, генерируется _make_icon.py
packaging/TransformBro.nsi      установщик NSIS (per-user, ярлыки, «Открыть с помощью»)
packaging/build_release.py   exe → установщик + 2 portable zip + заметки релиза
packaging/version_info.txt   метаданные Windows для exe
payload/                     ffmpeg.exe + ПРОЧТИ_МЕНЯ.txt + LICENSE-FFmpeg.txt
.github/workflows/release.yml CI: тег v* → релиз с установщиком и архивами
_TESTS/                      тестовые файлы и прогоны: _run_all.py, _gui_checks.py,
                             _installer_checks.py
Собрать_EXE.bat              быстрая пересборка exe (кладёт его в корень)
Собрать_Релиз.bat            exe + установщик + portable zip
```

## Лицензии

Код — MIT. FFmpeg в составе релиза — GPL/LGPL, см. `payload/LICENSE-FFmpeg.txt`.
