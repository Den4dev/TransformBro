# -*- coding: utf-8 -*-
"""GUI-проверки без человека: папка, скрытые файлы, закрытие во время работы."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import TransformBro as FL

DROP = ROOT / "_TESTS" / "_drop"
if DROP.exists():
    import shutil
    shutil.rmtree(DROP)
(DROP / "sub").mkdir(parents=True)
(DROP / ".hidden").mkdir()
import shutil as _sh
_sh.copy2(ROOT / "_TESTS" / "photo.jpg", DROP / "photo.jpg")
_sh.copy2(ROOT / "_TESTS" / "sample.png", DROP / "sub" / "sample.png")
_sh.copy2(ROOT / "_TESTS" / "real.rtf", DROP / "sub" / "real.rtf")
(DROP / "test.txt").write_text("тест", encoding="utf-8")
(DROP / ".hidden" / "secret.txt").write_text("hidden", encoding="utf-8")
(DROP / "noext").write_text("x", encoding="utf-8")

app = QApplication(sys.argv)
win = FL.MainWindow()

results = []

# 1) папка раскрывается, скрытые пропускаются, без расширения — тоже
win.add_paths([str(DROP)])
names = sorted(t.source_path.name for t in win.tasks.values())
results.append(("folder_expand", names == ["photo.jpg", "real.rtf", "sample.png", "test.txt"], names))
results.append(("summary", win.summary_label.text().startswith("Всего: 4"), win.summary_label.text()))

# 2) запуск длинной задачи и закрытие окна
clip = ROOT / "_TESTS" / "clip.mp4"
_sh.copy2(clip, DROP / "clip.mp4")
win.add_paths([str(DROP / "clip.mp4")])
task = list(win.tasks.values())[-1]
task.selected_action = next(a for a in task.available_actions if a.id == "to_webm")
win.run_task(task.id)
results.append(("task_started", task.status == FL.TaskStatus.PROCESSING, task.status.value))

def close_and_quit():
    win.close()
    app.quit()


QTimer.singleShot(600, close_and_quit)
t0 = time.time()
app.exec()
elapsed = time.time() - t0
results.append(("close_fast", elapsed < 9, f"{elapsed:.1f}s"))
results.append(("cancel_flag", task._cancel.is_set(), "запрошен отмена"))
partial = list((DROP).glob("clip_webm*.webm"))
results.append(("no_partial", not partial, [p.name for p in partial]))

import subprocess
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"],
                     capture_output=True).stdout
results.append(("no_ffmpeg_left", b"ffmpeg.exe" not in out, ""))

print("\n=== GUI CHECKS ===")
bad = 0
for name, ok, detail in results:
    print(("PASS" if ok else "FAIL"), name, detail)
    if not ok:
        bad += 1
print(f"провалов: {bad}")
sys.exit(1 if bad else 0)
