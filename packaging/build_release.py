# -*- coding: utf-8 -*-
"""Собирает релиз TransformBro: установщик NSIS + portable ZIP (с FFmpeg и без) + заметки.

Запуск:  .venv\\Scripts\\python.exe packaging\\build_release.py [--skip-build] [--no-ffmpeg]
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PAYLOAD = ROOT / "payload"
RELEASE = ROOT / "release"
CACHE = RELEASE / "ffmpeg-cache"
APP = ROOT / "TransformBro.py"

# официальная сборка FFmpeg для Windows: ~30 МБ в архиве вместо 214 МБ у full-сборки из PATH
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_MAX_BYTES = 150 * 1024 * 1024


def read_version() -> str:
    m = re.search(r'^APP_VERSION = "([^"]+)"', APP.read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit("Не нашли APP_VERSION в TransformBro.py")
    return m.group(1)


def find_makensis() -> Path:
    cands = []
    if os.environ.get("NSIS_MKENSIS"):
        cands.append(Path(os.environ["NSIS_MKENSIS"]))
    cands += sorted(ROOT.glob("tools/nsis-*/makensis.exe"))
    for pf in ("C:/Program Files (x86)/NSIS/makensis.exe", "C:/Program Files/NSIS/makensis.exe"):
        cands.append(Path(pf))
    which = shutil.which("makensis")
    if which:
        cands.append(Path(which))
    for c in cands:
        if c.exists():
            return c
    sys.exit("makensis.exe не найден. Распакуйте NSIS в tools/ или задайте NSIS_MKENSIS.")


def download_ffmpeg() -> Path:
    """Тянет ffmpeg.exe из официальной essentials-сборки. Архив кэшируется в release/ffmpeg-cache."""
    target = PAYLOAD / "ffmpeg.exe"
    if target.exists() and target.stat().st_size <= FFMPEG_MAX_BYTES:
        print(f"ffmpeg уже в payload ({target.stat().st_size / 1024 / 1024:.0f} МБ)")
        return target
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / Path(FFMPEG_URL).name
    if not archive.exists():
        if target.exists():
            target.unlink()
        print(f"Скачиваем {FFMPEG_URL}")
        t0 = time.time()
        urllib.request.urlretrieve(FFMPEG_URL, archive.with_suffix(".part"))
        archive.with_suffix(".part").rename(archive)
        print(f"  {archive.stat().st_size / 1024 / 1024:.0f} МБ за {time.time() - t0:.0f} с")
    with zipfile.ZipFile(archive) as z:
        exe = next((n for n in z.namelist()
                    if n.replace("\\", "/").endswith("/bin/ffmpeg.exe")), None)
        if not exe:
            sys.exit(f"в {archive.name} нет bin/ffmpeg.exe")
        if target.exists():
            target.unlink()
        target.write_bytes(z.read(exe))
    print(f"ffmpeg.exe в payload: {target.stat().st_size / 1024 / 1024:.0f} МБ")
    return target


def copy_system_ffmpeg() -> Path:
    """Запасной вариант: ffmpeg.exe из PATH (обычно это full-сборка, она большая)."""
    target = PAYLOAD / "ffmpeg.exe"
    if target.exists():
        return target
    src = shutil.which("ffmpeg")
    if not src:
        for p in Path(os.environ.get("LOCALAPPDATA", ""),
                      "Microsoft/WinGet/Packages").glob("*ffmpeg*/bin/ffmpeg.exe"):
            src = str(p)
            break
    if not src or not Path(src).exists():
        sys.exit("ffmpeg не найден и не скачался — положите ffmpeg.exe в payload/ вручную.")
    print(f"Копируем ffmpeg из системы: {src} ({Path(src).stat().st_size / 1024 / 1024:.0f} МБ)")
    PAYLOAD.mkdir(exist_ok=True)
    shutil.copy2(src, target)
    return target


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_zip(out: Path, exe: Path, with_ffmpeg: bool) -> Path:
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(exe, f"TransformBro/{exe.name}")
        for f in sorted(PAYLOAD.iterdir()):
            if not f.is_file():
                continue
            if not with_ffmpeg and "ffmpeg" in f.name.lower():
                continue
            z.write(f, f"TransformBro/{f.name}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="не запускать PyInstaller")
    ap.add_argument("--no-ffmpeg", action="store_true",
                    help="не включать FFmpeg: установщик и архив будут только с текстом/картинками/PDF")
    ap.add_argument("--system-ffmpeg", action="store_true",
                    help="взять ffmpeg.exe из PATH, а не скачивать essentials-сборку")
    args = ap.parse_args()

    version = read_version()
    print(f"TransformBro {version}")

    if not args.skip_build:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "TransformBro.spec")], cwd=ROOT)

    exe = DIST / "TransformBro.exe"
    if not exe.exists():
        sys.exit("dist/TransformBro.exe не собран")
    print(f"exe: {exe.stat().st_size / 1024 / 1024:.1f} МБ, {time.ctime(exe.stat().st_mtime)}")

    RELEASE.mkdir(exist_ok=True)
    if args.no_ffmpeg:
        if (PAYLOAD / "ffmpeg.exe").exists():
            (PAYLOAD / "ffmpeg.exe").unlink()
    elif args.system_ffmpeg:
        copy_system_ffmpeg()
    else:
        download_ffmpeg()

    has_ffmpeg = (PAYLOAD / "ffmpeg.exe").exists()
    docs = [f for f in sorted(PAYLOAD.iterdir()) if f.is_file() and f.name != "ffmpeg.exe"]
    size_kb = sum(f.stat().st_size for f in [exe, *docs, *([PAYLOAD / 'ffmpeg.exe'] if has_ffmpeg else [])]) // 1024

    artifacts = []

    if has_ffmpeg:
        makensis = find_makensis()
        setup = RELEASE / f"TransformBro-{version}-Setup.exe"
        if setup.exists():
            setup.unlink()
        t0 = time.time()
        run([str(makensis), f"/DINSTALL_SIZE_KB={size_kb}", "TransformBro.nsi"], cwd=ROOT / "packaging")
        if not setup.exists():
            sys.exit("makensis отработал, но установщик не появился")
        print(f"установщик: {setup.stat().st_size / 1024 / 1024:.1f} МБ за {time.time() - t0:.0f} с")
        artifacts.append(setup)

    full_zip = make_zip(RELEASE / f"TransformBro-{version}-win64.zip", exe, has_ffmpeg)
    print(f"portable:   {full_zip.stat().st_size / 1024 / 1024:.1f} МБ")
    artifacts.append(full_zip)

    lite_zip = make_zip(RELEASE / f"TransformBro-{version}-win64-lite.zip", exe, False)
    print(f"без FFmpeg: {lite_zip.stat().st_size / 1024 / 1024:.1f} МБ")
    artifacts.append(lite_zip)

    notes = RELEASE / "RELEASE_NOTES.md"
    lines = [
        f"## TransformBro {version}",
        "",
        "Конвертер изображений, документов, текста, аудио и видео в одном окне. Windows 10/11 x64.",
        "",
        "**Что скачать**",
        "",
    ]
    if has_ffmpeg:
        lines += [
            f"- `TransformBro-{version}-Setup.exe` — установщик в ваш профиль, права администратора не нужны.",
            f"- `TransformBro-{version}-win64.zip` — portable: распаковать и запустить `TransformBro.exe`.",
            "",
            "В оба варианта включён `ffmpeg.exe` (essentials-сборка), поэтому видео и аудио работают сразу.",
        ]
    else:
        lines += [f"- `TransformBro-{version}-win64-lite.zip` — portable без FFmpeg:",
                  "  изображения, PDF, документы и текст; для видео/аудио положите ffmpeg.exe рядом с программой."]
    lines += [
        "",
        f"Лёгкий вариант без кодеков: `TransformBro-{version}-win64-lite.zip` "
        "(только изображения, PDF, документы, текст).",
        "",
        "### Поддерживается",
        "- изображения: JPG/PNG/WEBP/BMP/GIF/TIFF/ICO/AVIF — конвертация, сжатие для Web, "
        "уменьшение до 1920/1080 px, удаление EXIF и GPS;",
        "- PDF: извлечение текста, страницы в PNG;",
        "- документы: DOC/DOCX/DOCM/ODT/RTF/HTML — текст, а при наличии MS Word ещё DOCX и PDF с вёрсткой;",
        "- текст: TXT/MD/CSV/JSON/LOG/XML/SRT/INI/YAML — PDF, DOCX, HTML с кириллицей;",
        "- видео: MP4/MKV/AVI/MOV/WEBM/WMV/FLV/TS/MTS/3GP/VOG и др. — аудио 7 форматов, сжатие в MP4, "
        "AVI, WEBM, MKV без перекодирования, 720p/480p, GIF, кадры в PNG;",
        "- аудио: MP3/WAV/FLAC/OGG/M4A/AAC/OPUS/WMA/AIFF/AMR/AC3/APE/WV — конвертация и Loudnorm.",
        "",
        "Сборка не подписана сертификатом: при первом запуске SmartScreen — «Подробнее» → "
        "«Выполнить в любом случае».",
        "",
        "### Контрольные суммы (SHA-256)",
        "",
    ]
    lines += [f"- `{a.name}` — `{sha256(a)}`" for a in artifacts]
    notes.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("заметки релиза:", notes)
    print("\nГОТОВО. Файлы в", RELEASE)


if __name__ == "__main__":
    main()
