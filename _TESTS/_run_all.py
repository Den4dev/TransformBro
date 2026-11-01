# -*- coding: utf-8 -*-
"""Headless прогон всех действий TransformBro на тестовых файлах."""
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import TransformBro as FL

OUT = ROOT / "_TESTS" / "_out"
IN = OUT / "in"
SRC = ROOT / "_TESTS"


def prep():
    if OUT.exists():
        shutil.rmtree(OUT)
    IN.mkdir(parents=True)
    for name in ("photo.jpg", "sample.png", "doc.pdf", "real.doc", "real.docx", "real.rtf",
                 "clip.mp4"):
        shutil.copy2(SRC / name, IN / name)
    shutil.copy2(SRC / "real.docx", IN / "real.docm")
    (IN / "test.txt").write_text(
        "Проверка текстового конвертера.\n"
        + "Очень длинная строка: " + "кириллица и латиница ABCDEFGHIJ " * 20 + "\n"
        + "Спецсимволы <tag> & \"quotes\" 'single'.\n"
        + "Табы:\tколонка1\tколонка2\n\n\n\nКонец.",
        encoding="utf-8")
    (IN / "test.html").write_text(
        "<html><head><style>body{color:red}</style><script>var x=1;</script></head>"
        "<body><h1>Заголовок</h1><p>Первый абзац.</p><p>Второй &amp; последний.</p></body></html>",
        encoding="utf-8")
    (IN / "test.csv").write_text("name,value\nтест,1\n", encoding="utf-8")


def run_one(path: Path, action_id: str, results: list) -> bool:
    handler = FL.find_handler(path)
    if not handler:
        results.append((path.name, action_id, "FAIL", "нет обработчика"))
        return False
    actions = handler.get_actions(path)
    action = next((a for a in actions if a.id == action_id), None)
    if not action:
        results.append((path.name, action_id, "FAIL", "действие не найдено"))
        return False
    task = FL.FileTask(
        id=uuid.uuid4().hex, source_path=path, category=handler.name,
        available_actions=actions, selected_action=action)
    t0 = time.time()
    try:
        out = handler.process(task, lambda p: None, lambda: False)
        ok = out.exists() and (out.is_dir() and any(out.iterdir()) if out.is_dir() else out.stat().st_size > 0)
        detail = f"{out.name} {out.stat().st_size if out.is_file() else len(list(out.iterdir()))} B" \
            if out.exists() else "нет файла"
        results.append((path.name, action_id, "OK" if ok else "FAIL", detail))
        return ok
    except Exception as e:
        results.append((path.name, action_id, "FAIL", f"{type(e).__name__}: {e}"))
        return False
    finally:
        results.append((path.name, action_id, "TIME", f"{time.time() - t0:.1f}s"))


def main():
    prep()
    results = []
    cases = [
        ("photo.jpg", "to_webp"), ("photo.jpg", "to_png"), ("photo.jpg", "to_bmp"),
        ("photo.jpg", "to_tiff"), ("photo.jpg", "to_ico"), ("photo.jpg", "compress_web"),
        ("photo.jpg", "resize_1080"), ("photo.jpg", "strip_exif"),
        ("sample.png", "to_jpg"), ("sample.png", "strip_exif"),
        ("doc.pdf", "pdf_to_txt"), ("doc.pdf", "pdf_to_png"),
        ("real.doc", "doc_to_txt"), ("real.doc", "doc_to_docx"), ("real.doc", "doc_to_pdf"),
        ("real.docx", "doc_to_txt"), ("real.docx", "doc_to_pdf"),
        ("real.docm", "doc_to_txt"),
        ("real.rtf", "doc_to_txt"),
        ("test.html", "doc_to_txt"),
        ("test.txt", "text_to_pdf"), ("test.txt", "text_to_docx"), ("test.txt", "text_to_html"),
        ("test.csv", "text_to_pdf"),
        ("clip.mp4", "extract_mp3"),
    ]
    # video-действия на малом клипе
    for aid in ("extract_wav", "extract_flac", "extract_m4a", "extract_ogg",
                "extract_opus", "extract_aac", "compress_mp4", "to_avi", "to_webm",
                "to_mkv_copy", "to_720p", "to_480p", "to_gif", "frames"):
        cases.append(("clip.mp4", aid))
    # аудио-действия на извлечённом mp3
    for aid in ("audio_to_wav", "audio_to_flac", "audio_to_m4a", "audio_to_ogg",
                "audio_to_opus", "audio_to_aac", "normalize"):
        cases.append(("clip_audio.mp3", aid))

    failures = 0
    for name, aid in cases:
        path = IN / name
        if not path.exists():
            results.append((name, aid, "SKIP", "нет входного файла"))
            continue
        before = len(results)
        ok = run_one(path, aid, results)
        msgs = [r for r in results[before:] if r[2] != "TIME"]
        print(f"{'PASS' if ok else 'FAIL'} {name} :: {aid} :: {msgs[0][3] if msgs else ''}")
        if not ok:
            failures += 1

    # AVI как вход: получаем из to_avi и конвертим в mp4
    avi = next(IN.glob("clip_avi.avi"), None)
    if avi:
        ok = run_one(avi, "compress_mp4", results)
        print(f"{'PASS' if ok else 'FAIL'} {avi.name} :: compress_mp4")
        if not ok:
            failures += 1

    print("\n=== SUMMARY ===")
    for name, aid, status, detail in results:
        if status in ("FAIL", "SKIP"):
            print(f"{status:4} {name:18} {aid:16} {detail}")
    total = sum(1 for r in results if r[2] in ("OK", "FAIL"))
    print(f"Всего действий: {total}, провалов: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
