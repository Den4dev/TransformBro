# -*- coding: utf-8 -*-
"""Тихая установка Setup.exe, проверка файлов/ярлыков/реестра, запуск, скриншот, удаление."""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
VERSION = "1.1.0"
SETUP = RELEASE / f"TransformBro-{VERSION}-Setup.exe"
TARGET = Path(os.environ["TEMP"]) / "fl_install_test"
APPDATA_LOCAL = Path(os.environ["LOCALAPPDATA"])
checks = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def transformbro_windows():
    """Верхние окна с заголовком TransformBro (у onefile окно принадлежит дочернему процессу)."""
    user32 = ctypes.windll.user32
    found = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value.startswith("TransformBro"):
                found.append(hwnd)
        return True

    user32.EnumWindows(proc_type(cb), 0)
    return found


def screenshot_window(hwnd, out: Path):
    import ctypes.wintypes as wt
    from PIL import ImageGrab
    r = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
    img.save(out)
    return img.size


def main():
    if not SETUP.exists():
        sys.exit(f"нет {SETUP}")
    subprocess.run(["taskkill", "/IM", "TransformBro.exe", "/F"], capture_output=True)
    if TARGET.exists():
        shutil.rmtree(TARGET, ignore_errors=True)

    t0 = time.time()
    r = subprocess.run([str(SETUP), "/S", f"/D={TARGET}"], capture_output=True, timeout=600)
    check("silent_install", r.returncode == 0, f"код {r.returncode}, {time.time() - t0:.0f}с")

    exe = TARGET / "TransformBro.exe"
    check("app_exe", exe.exists(), f"{exe.stat().st_size / 1024 / 1024:.0f} МБ" if exe.exists() else "нет")
    check("ffmpeg_next_to_exe", (TARGET / "ffmpeg.exe").exists())
    check("readme", (TARGET / "ПРОЧТИ_МЕНЯ.txt").exists())
    check("uninstaller", (TARGET / "Uninstall.exe").exists())

    sm = (Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/TransformBro")
    if not sm.exists():
        sm = APPDATA_LOCAL / "Microsoft/Windows/Start Menu/Programs/TransformBro"
    lnk = sorted(p.name for p in sm.glob("*.lnk")) if sm.exists() else []
    check("start_menu", len(lnk) == 3, lnk)
    check("no_desktop_shortcut_by_default",
          not (Path(os.environ["USERPROFILE"]) / "Desktop" / "TransformBro.lnk").exists())

    ok, detail = False, ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TransformBro") as k:
            name = winreg.QueryValueEx(k, "DisplayName")[0]
            loc = winreg.QueryValueEx(k, "InstallLocation")[0]
            ver = winreg.QueryValueEx(k, "DisplayVersion")[0]
            size = winreg.QueryValueEx(k, "EstimatedSize")[0]
        ok = (name == "TransformBro" and Path(loc) == TARGET and ver == VERSION and size > 100000)
        detail = f"{name} {ver} → {loc} · {size // 1024} МБ"
    except OSError as e:
        detail = str(e)
    check("uninstall_registry", ok, detail)

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Classes\Applications\TransformBro.exe\shell\open\command") as k:
        cmd = winreg.QueryValueEx(k, "")[0]
    check("open_with_reg", str(TARGET).lower() in cmd.lower(), cmd)

    # запуск установленного приложения на реальном файле + скриншот
    work = Path(os.environ["TEMP"]) / "fl_run"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    target_file = work / "photo.jpg"
    shutil.copy2(ROOT / "_TESTS" / "photo.jpg", target_file)
    out_file = work / "photo.webp"
    p = subprocess.Popen([str(exe), str(target_file)])
    time.sleep(16)
    wins = transformbro_windows()
    check("installed_app_window", bool(wins), f"{len(wins)} окно(ок)")
    shot = ROOT / "_TESTS" / "_installed.png"
    if wins:
        try:
            w, h = screenshot_window(wins[0], shot)
            print(f"INFO снимок окна установленного: {w}x{h} → {shot.name}")
        except Exception as e:
            print("INFO снимок не получился:", e)
    check("app_process_alive", p.poll() is None, f"pid {p.pid}")
    subprocess.run(["taskkill", "/IM", "TransformBro.exe", "/F"], capture_output=True)
    p.wait(timeout=15)

    # удаление
    t0 = time.time()
    r = subprocess.run([str(TARGET / "Uninstall.exe"), "/S"], capture_output=True, timeout=300)
    time.sleep(4)
    check("silent_uninstall", r.returncode == 0, f"код {r.returncode}, {time.time() - t0:.0f}с")
    left = [x.name for x in TARGET.glob("*")] if TARGET.exists() else []
    check("folder_removed", not (TARGET / "TransformBro.exe").exists(), left[:3])
    for key, label in ((r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TransformBro",
                        "registry_removed"),
                       (r"Software\Classes\Applications\TransformBro.exe", "open_with_removed"),
                       (r"Software\TransformBro", "app_settings_removed")):
        gone = True
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
            gone = False
        except OSError:
            pass
        check(label, gone)
    check("start_menu_removed", not sm.exists() or not list(sm.glob("*.lnk")),
          [p.name for p in sm.glob("*.lnk")] if sm.exists() else "")

    bad = [c for c in checks if not c[1]]
    print(f"\n=== ИТОГО: {len(checks)} проверок, провалов {len(bad)} ===")
    for n, _, d in bad:
        print("FAIL", n, d)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
