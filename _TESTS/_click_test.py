# -*- coding: utf-8 -*-
"""Клик мышью по кнопке «Конвертировать» в собранном exe: полный end-to-end без человека."""
import ctypes
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "TransformBro.exe"

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

BUTTON = (977, 352)  # координаты внутри окна, снятые со скриншота


def find_windows(title):
    found = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == title:
                found.append(hwnd)
        return True

    cb_ref = proc(cb)
    user32.EnumWindows(cb_ref, 0)
    return found


def click_at(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


def main():
    if not EXE.exists():
        sys.exit("нет TransformBro.exe в корне")
    subprocess.run(["taskkill", "/IM", "TransformBro.exe", "/F"], capture_output=True)
    work = Path(__file__).resolve().parent / "_click"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    src = work / "photo.jpg"
    shutil.copy2(ROOT / "_TESTS" / "photo.jpg", src)
    clip = work / "clip.mp4"
    shutil.copy2(ROOT / "_TESTS" / "clip.mp4", clip)

    p = subprocess.Popen([str(EXE), str(src), str(clip)])
    time.sleep(15)
    wins = find_windows("TransformBro")
    if not wins:
        print("FAIL окно не найдено")
        subprocess.run(["taskkill", "/IM", "TransformBro.exe", "/F"], capture_output=True)
        return 1
    hwnd = wins[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(1)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    print(f"окно {r.left},{r.top} — {r.right - r.left}x{r.bottom - r.top}")

    # клик по «Конвертировать» у первой карточки (JPG → WEBP)
    click_at(r.left + BUTTON[0], r.top + BUTTON[1])
    time.sleep(4)
    webp = work / "photo.webp"
    ok1 = webp.exists() and webp.stat().st_size > 1000
    print(("PASS" if ok1 else "FAIL"), "клик JPG→WEBP", webp.stat().st_size if ok1 else "")

    # вторая карточка (видео → MP3) лежит ниже на 120 px
    click_at(r.left + BUTTON[0], r.top + BUTTON[1] + 120)
    time.sleep(12)
    mp3 = work / "clip_audio.mp3"
    ok2 = mp3.exists() and mp3.stat().st_size > 1000
    print(("PASS" if ok2 else "FAIL"), "клик видео→MP3", mp3.stat().st_size if ok2 else "")

    subprocess.run(["taskkill", "/IM", "TransformBro.exe", "/F"], capture_output=True)
    p.wait(timeout=15)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
