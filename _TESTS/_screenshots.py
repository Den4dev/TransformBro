# -*- coding: utf-8 -*-
"""Скриншоты рабочего окна: очередь смешанных файлов, процесс, результат."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import QTimer

import TransformBro as FL

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

FILES = [
    ROOT / "_TESTS" / "photo.jpg",
    ROOT / "_TESTS" / "doc.pdf",
    ROOT / "_TESTS" / "real.docx",
    ROOT / "_TESTS" / "test_long.txt",
    ROOT / "_TESTS" / "clip.mp4",
]
OUT_DIR = ROOT / "_TESTS" / "_shots"
OUT_DIR.mkdir(exist_ok=True)
for f in FILES:
    if not f.exists():
        print(f"нет файла {f}")
        sys.exit(1)

app = QApplication(sys.argv)
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(FL.QSS)
icon = FL.resource_path("assets/TransformBro.ico")
if icon.exists():
    app.setWindowIcon(QIcon(str(icon)))
win = FL.MainWindow()
win.add_paths([str(f) for f in FILES])
win.show()
shots = []


def grab(tag):
    """Qt рисует окно сам — не мешает ни одно другое окно поверх."""
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    pix = win.grab()
    p = OUT_DIR / f"{tag}.png"
    pix.save(str(p))
    shots.append(p.name)
    print("снимок:", tag, pix.width(), "x", pix.height())


def start_all():
    grab("01_queue")
    win.run_all()


def grab_running():
    grab("02_running")


def check_done():
    done = sum(1 for t in win.tasks.values() if t.status == FL.TaskStatus.COMPLETED)
    running = sum(1 for t in win.tasks.values() if t.status == FL.TaskStatus.PROCESSING)
    print(f"готово {done}/{len(win.tasks)}, в работе {running}")
    if running == 0:
        grab("03_done")
        app.quit()
    else:
        QTimer.singleShot(3000, check_done)


QTimer.singleShot(1500, start_all)
QTimer.singleShot(4000, grab_running)
QTimer.singleShot(9000, check_done)
app.exec()

print("\n=== ИТОГ ===")
for t in win.tasks.values():
    print(f"{t.source_path.name:16} {t.status.value:10} {t.output_path.name if t.output_path else t.error_message[:60]}")
