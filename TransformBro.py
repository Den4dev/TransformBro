# -*- coding: utf-8 -*-
"""TransformBro — единый конвертационный комбайн: изображения, PDF, видео/аудио."""

import os
import re
import sys
import ctypes
import uuid
import shutil
import tempfile
import zipfile
import threading
import subprocess
from html import unescape, escape as escape_html
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Callable, Optional

from PySide6.QtCore import (
    Qt, QObject, Signal, Slot, QRunnable, QThreadPool, QSize, QUrl, QTimer
)
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QDesktopServices, QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QProgressBar, QScrollArea,
    QFileDialog, QFrame, QMessageBox, QSizePolicy, QStackedLayout
)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

APP_VERSION = "1.1.0"


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent / relative


# ==============================================================================
# 1. ЯДРО (CORE LAYER)
# ==============================================================================

class TaskStatus(Enum):
    PENDING = "Ожидание"
    PROCESSING = "В работе"
    COMPLETED = "Готово"
    ERROR = "Ошибка"
    CANCELED = "Отменено"


@dataclass
class ActionOption:
    id: str
    title: str
    target_ext: str
    handler_name: str
    params: Dict = field(default_factory=dict)


@dataclass
class FileTask:
    id: str
    source_path: Path
    category: str
    available_actions: List[ActionOption]
    selected_action: Optional[ActionOption] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    output_path: Optional[Path] = None
    error_message: str = ""
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def request_cancel(self):
        self._cancel.set()

    def is_canceled(self) -> bool:
        return self._cancel.is_set()


def human_size(n: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def get_safe_output_path(source_path: Path, target_ext: str, suffix: str = "") -> Path:
    parent = source_path.parent
    stem = source_path.stem
    ext = target_ext if (not target_ext or target_ext.startswith(".")) else f".{target_ext}"
    base_name = f"{stem}{suffix}"
    candidate = parent / f"{base_name}{ext}"
    counter = 1
    while candidate == source_path or candidate.exists():
        candidate = parent / f"{base_name}_{counter}{ext}"
        counter += 1
    return candidate


# ==============================================================================
# 2. ОБРАБОТЧИКИ (HANDLERS LAYER)
# ==============================================================================

class BaseHandler:
    name = "base"
    title = ""
    badge = "???"
    supported_extensions: List[str] = []

    def available(self) -> bool:
        return True

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        raise NotImplementedError

    def process(self, task: FileTask, progress_cb: Callable[[int], None],
                cancel_check: Callable[[], bool]) -> Path:
        raise NotImplementedError


class ImageHandler(BaseHandler):
    name = "image"
    title = "Изображения"
    badge = "IMG"
    supported_extensions = [".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp",
                            ".gif", ".tif", ".tiff", ".ico", ".avif"]

    def available(self):
        return HAS_PIL

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        ext = file_path.suffix.lower()
        actions = []
        for target in ["webp", "png", "jpg", "bmp", "tiff", "ico"]:
            if f".{target}" != ext and not (ext == ".jpeg" and target == "jpg"):
                actions.append(ActionOption(
                    id=f"to_{target}", title=f"Конвертировать в {target.upper()}",
                    target_ext=f".{target}", handler_name=self.name,
                    params={"mode": "convert", "format": target}))
        actions.append(ActionOption(
            id="compress_web", title="Сжать для Web (WebP, 75%)",
            target_ext=".webp", handler_name=self.name,
            params={"mode": "compress", "quality": 75}))
        actions.append(ActionOption(
            id="resize_1920", title="Уменьшить до 1920 px (JPG)",
            target_ext=".jpg", handler_name=self.name,
            params={"mode": "resize", "max_side": 1920}))
        actions.append(ActionOption(
            id="resize_1080", title="Уменьшить до 1080 px (JPG)",
            target_ext=".jpg", handler_name=self.name,
            params={"mode": "resize", "max_side": 1080}))
        actions.append(ActionOption(
            id="strip_exif", title="Удалить метаданные (EXIF / GPS)",
            target_ext=ext, handler_name=self.name,
            params={"mode": "strip_exif"}))
        return actions

    def process(self, task, progress_cb, cancel_check):
        action = task.selected_action
        mode = action.params.get("mode")
        progress_cb(15)
        if cancel_check():
            raise InterruptedError("Отменено.")
        with Image.open(task.source_path) as img:
            progress_cb(40)
            if mode == "convert":
                fmt = action.params["format"]
                out_path = get_safe_output_path(task.source_path, action.target_ext)
                save_format = "JPEG" if fmt == "jpg" else fmt.upper()
                if save_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif save_format == "JPEG" and img.mode != "RGB":
                    img = img.convert("RGB")
                elif save_format == "ICO" and img.mode not in ("RGBA", "RGB"):
                    img = img.convert("RGBA")
                progress_cb(75)
                img.save(out_path, format=save_format, quality=92)
            elif mode == "compress":
                out_path = get_safe_output_path(task.source_path, ".webp", suffix="_compressed")
                if img.mode in ("P", "RGBA", "LA") and img.mode != "RGBA":
                    img = img.convert("RGBA")
                progress_cb(70)
                img.save(out_path, format="WEBP", quality=action.params.get("quality", 75),
                         optimize=True)
            elif mode == "resize":
                max_side = action.params.get("max_side", 1920)
                out_path = get_safe_output_path(task.source_path, ".jpg", suffix=f"_{max_side}")
                resized = img.convert("RGB")
                if max(resized.size) > max_side:
                    resized.thumbnail((max_side, max_side), Image.LANCZOS)
                progress_cb(75)
                resized.save(out_path, format="JPEG", quality=90)
            elif mode == "strip_exif":
                out_path = get_safe_output_path(task.source_path, action.target_ext, suffix="_clean")
                target = img
                if target.mode in ("P", "PA", "LA"):
                    target = target.convert("RGBA")
                elif target.mode == "1":
                    target = target.convert("L")
                clean = Image.new(target.mode, target.size)
                clean.putdata(list(target.getdata()))
                if out_path.suffix.lower() in (".jpg", ".jpeg", ".jfif"):
                    if clean.mode in ("RGBA", "LA"):
                        bg = Image.new("RGB", clean.size, (255, 255, 255))
                        bg.paste(clean, mask=clean.split()[-1])
                        clean = bg
                    elif clean.mode != "RGB":
                        clean = clean.convert("RGB")
                progress_cb(80)
                clean.save(out_path)
            else:
                raise ValueError(f"Неизвестный режим: {mode}")
        progress_cb(100)
        return out_path


class PDFHandler(BaseHandler):
    name = "pdf"
    title = "PDF"
    badge = "PDF"
    supported_extensions = [".pdf"]

    def available(self):
        return HAS_FITZ

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        return [
            ActionOption("pdf_to_txt", "Извлечь весь текст (.TXT)", ".txt", self.name,
                         {"mode": "extract_text"}),
            ActionOption("pdf_to_png", "Экспортировать страницы в PNG (папка)", "", self.name,
                         {"mode": "pages_to_png"}),
        ]

    def process(self, task, progress_cb, cancel_check):
        mode = task.selected_action.params.get("mode")
        doc = fitz.open(task.source_path)
        try:
            total = len(doc)
            if total == 0:
                raise ValueError("PDF пуст или повреждён.")
            if mode == "extract_text":
                out_path = get_safe_output_path(task.source_path, ".txt")
                chunks = []
                for idx, page in enumerate(doc):
                    if cancel_check():
                        raise InterruptedError("Отменено.")
                    chunks.append(f"--- Страница {idx + 1} ---\n{page.get_text()}")
                    progress_cb(int((idx + 1) / total * 100))
                out_path.write_text("\n\n".join(chunks), encoding="utf-8")
                return out_path
            elif mode == "pages_to_png":
                out_dir = get_safe_output_path(task.source_path, "", suffix="_pages")
                out_dir.mkdir(parents=True, exist_ok=True)
                try:
                    for idx, page in enumerate(doc):
                        if cancel_check():
                            raise InterruptedError("Отменено.")
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        pix.save(str(out_dir / f"page_{idx + 1:03d}.png"))
                        progress_cb(int((idx + 1) / total * 100))
                except BaseException:
                    shutil.rmtree(out_dir, ignore_errors=True)
                    raise
                return out_dir
            raise ValueError(f"Неизвестный режим: {mode}")
        finally:
            doc.close()


WORD_LOCK = threading.Lock()


def _word_installed() -> bool:
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application"))
        return True
    except OSError:
        return False


def _word_open(src: Path):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    # Word резолвит относительные пути от своего cwd (system32) — только absolute
    try:
        doc = word.Documents.Open(os.path.abspath(str(src)), False, True, False)
    except Exception:
        try:
            word.Quit()
        except Exception:
            pass
        raise
    return word, doc


def _word_cleanup(word, doc):
    try:
        if doc is not None:
            doc.Close(False)
    except Exception:
        pass
    try:
        if word is not None:
            word.Quit()
    except Exception:
        pass
    try:
        import pythoncom
        pythoncom.CoUninitialize()
    except Exception:
        pass


def word_extract_text(src: Path) -> str:
    with WORD_LOCK:
        word = doc = None
        try:
            word, doc = _word_open(src)
            return doc.Content.Text
        finally:
            _word_cleanup(word, doc)


def word_saveas(src: Path, out: Path, fmt: int):
    with WORD_LOCK:
        word = doc = None
        try:
            word, doc = _word_open(src)
            doc.SaveAs2(os.path.abspath(str(out)), FileFormat=fmt)
        finally:
            _word_cleanup(word, doc)


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace")
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


class DocHandler(BaseHandler):
    """Документы: DOCX/ODT/RTF/HTML разбираем нативно, бинарный DOC — через MS Word (COM),
    если Word нет — crude-экстракция текста из потока WordDocument."""
    name = "doc"
    title = "Документы"
    badge = "DOC"
    supported_extensions = [".doc", ".docx", ".docm", ".odt", ".rtf", ".html", ".htm"]

    def __init__(self):
        self.has_word = _word_installed()

    def available(self):
        return True

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        ext = file_path.suffix.lower()
        actions = [ActionOption(
            "doc_to_txt", "Извлечь текст (.TXT)", ".txt", self.name,
            {"mode": "extract_text"})]
        if self.has_word:
            if ext in (".doc", ".docm"):
                actions.append(ActionOption(
                    "doc_to_docx", "Сохранить как .DOCX (через MS Word)", ".docx", self.name,
                    {"mode": "word_saveas", "fmt": 16}))
            actions.append(ActionOption(
                "doc_to_pdf", "Сохранить как PDF с вёрсткой (MS Word)", ".pdf", self.name,
                {"mode": "word_saveas", "fmt": 17}))
        return actions

    # --- нативные экстракторы ---

    @staticmethod
    def _docx_text(path: Path) -> str:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        paras = []
        for chunk in re.split(r"</w:p>", xml):
            runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", chunk, re.S)
            tabs = re.findall(r"<w:tab/>", chunk)
            text = unescape("".join(runs))
            if tabs and not text.strip():
                continue
            if text.strip():
                paras.append(text)
        return "\n".join(paras)

    @staticmethod
    def _odt_text(path: Path) -> str:
        with zipfile.ZipFile(path) as z:
            xml = z.read("content.xml").decode("utf-8", "replace")
        body = xml[xml.find("<office:body>"):] if "<office:body>" in xml else xml
        body = re.sub(r"<text:line-break[^>]*/>", "\n", body)
        body = re.sub(r"<text:tab[^>]*/>", "\t", body)
        paras = []
        for chunk in re.split(r"</text:p>|</text:h>", body):
            text = unescape(re.sub(r"<[^>]+>", "", chunk))
            if text.strip():
                paras.append(text)
        return "\n".join(paras)

    @staticmethod
    def _rtf_text(path: Path) -> str:
        raw = path.read_bytes().decode("latin-1", "replace")
        raw = re.sub(r"\{\\\*[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", raw)
        raw = re.sub(r"\\par[d]?\b", "\n", raw)
        raw = re.sub(r"\\tab\b", "\t", raw)

        def _hex(m):
            return bytes([int(m.group(1), 16)]).decode("cp1251", "replace")
        raw = re.sub(r"\\'([0-9a-fA-F]{2})", _hex, raw)

        def _uni(m):
            n = int(m.group(1))
            return chr(n if n >= 0 else n + 65536)
        raw = re.sub(r"\\u(-?\d+)\??", _uni, raw)
        raw = re.sub(r"\\[a-zA-Z]{1,32}-?\d{0,5} ?", "", raw)
        raw = raw.replace("{", "").replace("}", "")
        return raw

    @staticmethod
    def _html_text(path: Path) -> str:
        raw = read_text_file(path)
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
        raw = re.sub(r"<br\s*/?>|</p>|</div>|</h[1-6]>|</li>|</tr>", "\n", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
        return unescape(raw)

    @staticmethod
    def _doc_text_crude(path: Path) -> str:
        import olefile
        if not olefile.isOleFile(str(path)):
            raise ValueError("Файл не является бинарным DOC (OLE). Установите MS Word для точной конвертации.")
        ole = olefile.OleFileIO(str(path))
        try:
            data = ole.openstream("WordDocument").read()
        finally:
            ole.close()
        text = data.decode("cp1251", "ignore")
        runs = re.findall(r"[\t\r\n\x20-\x7E\xa0-\xFF]{6,}", text)
        return "\n".join(runs)

    def process(self, task, progress_cb, cancel_check):
        mode = task.selected_action.params.get("mode")
        ext = task.source_path.suffix.lower()
        action = task.selected_action
        progress_cb(10)
        if cancel_check():
            raise InterruptedError("Отменено.")

        if mode == "extract_text":
            if ext in (".docx", ".docm"):
                text = self._docx_text(task.source_path)
            elif ext == ".odt":
                text = self._odt_text(task.source_path)
            elif ext == ".rtf":
                text = self._rtf_text(task.source_path)
            elif ext in (".html", ".htm"):
                text = self._html_text(task.source_path)
            else:  # .doc
                if self.has_word:
                    text = word_extract_text(task.source_path)
                else:
                    text = self._doc_text_crude(task.source_path)
            text = text.replace("\r", "\n").replace("\x07", "\t")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if not text:
                raise ValueError("В документе не найден текст (возможно, это скан или таблицы без текста).")
            out_path = get_safe_output_path(task.source_path, ".txt")
            progress_cb(85)
            out_path.write_text(text, encoding="utf-8")
            progress_cb(100)
            return out_path

        if mode == "word_saveas":
            if not self.has_word:
                raise RuntimeError("MS Word не найден — конвертация с вёрсткой недоступна.")
            fmt = action.params["fmt"]
            out_path = get_safe_output_path(
                task.source_path, action.target_ext,
                suffix="" if fmt == 16 else "_pdf")
            progress_cb(30)
            word_saveas(task.source_path, out_path, fmt)
            if not out_path.exists():
                raise RuntimeError("Word не создал файл — проверьте, что документ не повреждён.")
            progress_cb(100)
            return out_path

        raise ValueError(f"Неизвестный режим: {mode}")


class TextHandler(BaseHandler):
    """Текстовые файлы: конвертация в PDF (кириллический моношрифт) и DOCX (нативно)."""
    name = "text"
    title = "Текст"
    badge = "TXT"
    supported_extensions = [".txt", ".md", ".csv", ".json", ".log", ".xml", ".srt",
                            ".ini", ".yaml", ".yml", ".cfg", ".nfo", ".tex"]

    _FONT_CANDIDATES = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def available(self):
        return True

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        return [
            ActionOption("text_to_pdf", "Сохранить как PDF", ".pdf", self.name,
                         {"mode": "to_pdf"}),
            ActionOption("text_to_docx", "Сохранить как DOCX", ".docx", self.name,
                         {"mode": "to_docx"}),
            ActionOption("text_to_html", "Сохранить как HTML", ".html", self.name,
                         {"mode": "to_html"}),
        ]

    @staticmethod
    def _font_path() -> Optional[str]:
        for f in TextHandler._FONT_CANDIDATES:
            if Path(f).exists():
                return f
        return None

    @staticmethod
    def _write_docx(out_path: Path, text: str):
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

        def esc(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        body = "".join(
            f'<w:p><w:r><w:t xml:space="preserve">{esc(line)}</w:t></w:r></w:p>'
            for line in (text.splitlines() or [""]))
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.document.main+xml"/></Types>')
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{body}<w:sectPr/></w:body></w:document>')
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", document)

    def _write_pdf(self, out_path: Path, text: str, progress_cb, cancel_check=None):
        import pymupdf
        font_path = self._font_path()
        font = pymupdf.Font(fontfile=font_path) if font_path else None
        W, H, M, FS, LH = 595, 842, 50, 10, 14.5
        usable = W - 2 * M

        def text_len(s):
            return font.text_length(s, fontsize=FS) if font else len(s) * FS * 0.5

        lines = []
        for raw in (text.splitlines() or [""]):
            raw = raw.expandtabs(4)
            if not raw.strip():
                lines.append("")
                continue
            cur = ""
            for word in raw.split(" "):
                candidate = f"{cur} {word}" if cur else word
                if text_len(candidate) <= usable:
                    cur = candidate
                    continue
                if cur:
                    lines.append(cur)
                while text_len(word) > usable and len(word) > 1:
                    cut = len(word)
                    while cut > 1 and text_len(word[:cut]) > usable:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                cur = word
            if cur:
                lines.append(cur)

        doc = pymupdf.open()
        page = None
        y = M
        embedded = False
        step = max(1, len(lines) // 20)
        for i, ln in enumerate(lines):
            if cancel_check and i % 200 == 0 and cancel_check():
                doc.close()
                raise InterruptedError("Отменено.")
            if page is None or y > H - M - LH:
                page = doc.new_page(width=W, height=H)
                y = M
                embedded = False
            if ln:
                kwargs = {"fontname": "F0"} if embedded else {}
                if not embedded and font_path:
                    page.insert_font(fontname="F0", fontfile=font_path)
                    embedded = True
                    kwargs = {"fontname": "F0"}
                page.insert_text((M, y), ln, fontsize=FS, **kwargs)
            y += LH
            if i % step == 0:
                progress_cb(10 + int(80 * i / max(1, len(lines))))
        if not page:
            doc.new_page(width=W, height=H)
        doc.save(str(out_path))
        doc.close()

    def process(self, task, progress_cb, cancel_check):
        text = read_text_file(task.source_path)
        if cancel_check():
            raise InterruptedError("Отменено.")
        progress_cb(5)
        mode = task.selected_action.params.get("mode")
        out_path = get_safe_output_path(task.source_path, task.selected_action.target_ext)
        if mode == "to_docx":
            progress_cb(40)
            self._write_docx(out_path, text)
        elif mode == "to_pdf":
            self._write_pdf(out_path, text, progress_cb, cancel_check)
        elif mode == "to_html":
            progress_cb(40)
            body = (text.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
            html_doc = (
                '<!DOCTYPE html>\n<html lang="ru"><head><meta charset="utf-8">'
                f'<title>{escape_html(task.source_path.stem)}</title>'
                '<style>body{background:#1e1e2e;color:#cdd6f4;margin:2em;}'
                'pre{font:14px/1.5 Consolas,monospace;white-space:pre-wrap;}</style>'
                f'</head><body><pre>{body}</pre></body></html>')
            out_path.write_text(html_doc, encoding="utf-8")
        else:
            raise ValueError(f"Неизвестный режим: {mode}")
        progress_cb(100)
        return out_path


class MediaHandler(BaseHandler):
    name = "media"
    title = "Видео / Аудио"
    badge = "AV"
    video_exts = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".m4v", ".flv",
                  ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".3gp", ".ogv", ".vob", ".f4v"]
    audio_exts = [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma",
                  ".aiff", ".aif", ".amr", ".ac3", ".mka", ".alac", ".ape", ".wv"]
    supported_extensions = video_exts + audio_exts

    _AUDIO_TARGETS = [
        ("mp3", "MP3 192 kbps", ["-acodec", "libmp3lame", "-b:a", "192k"]),
        ("wav", "WAV (PCM)", ["-acodec", "pcm_s16le"]),
        ("flac", "FLAC (без потерь)", ["-acodec", "flac"]),
        ("m4a", "M4A (AAC 192 kbps)", ["-acodec", "aac", "-b:a", "192k"]),
        ("ogg", "OGG (Vorbis)", ["-acodec", "libvorbis", "-q:a", "5"]),
        ("opus", "OPUS 128 kbps", ["-acodec", "libopus", "-b:a", "128k"]),
        ("aac", "AAC 192 kbps", ["-acodec", "aac", "-b:a", "192k"]),
    ]

    def __init__(self):
        self.ffmpeg_bin = self._find_ffmpeg()

    @staticmethod
    def _find_ffmpeg():
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).parent
        else:
            app_dir = Path(__file__).resolve().parent
        for name in ("ffmpeg.exe", "ffmpeg"):
            local = app_dir / name
            if local.exists():
                return str(local)
        return shutil.which("ffmpeg") or shutil.which("avconv")

    def available(self):
        return bool(self.ffmpeg_bin)

    def get_actions(self, file_path: Path) -> List[ActionOption]:
        ext = file_path.suffix.lower()
        actions = []
        if ext in self.video_exts:
            for fmt, title, codec in self._AUDIO_TARGETS:
                actions.append(ActionOption(
                    f"extract_{fmt}", f"Извлечь аудио → {title}", f".{fmt}", self.name,
                    {"args": ["-vn", *codec], "suffix": "_audio"}))
            actions += [
                ActionOption("compress_mp4", "Видео → MP4 (H.264, CRF 23)", ".mp4", self.name,
                             {"args": ["-vcodec", "libx264", "-crf", "23",
                                       "-preset", "fast", "-acodec", "aac"],
                              "suffix": ""}),
                ActionOption("to_avi", "Видео → AVI (MPEG-4 + MP3)", ".avi", self.name,
                             {"args": ["-vcodec", "mpeg4", "-q:v", "4",
                                       "-acodec", "libmp3lame", "-b:a", "192k"],
                              "suffix": "_avi"}),
                ActionOption("to_webm", "Видео → WEBM (VP9 + Opus)", ".webm", self.name,
                             {"args": ["-vcodec", "libvpx-vp9", "-crf", "32", "-b:v", "0",
                                       "-acodec", "libopus", "-b:a", "128k"],
                              "suffix": "_webm"}),
                ActionOption("to_mkv_copy", "Видео → MKV (без перекодирования)", ".mkv", self.name,
                             {"args": ["-c", "copy"], "suffix": "_copy"}),
                ActionOption("to_720p", "Уменьшить до 720p (MP4)", ".mp4", self.name,
                             {"args": ["-vf", "scale=-2:720", "-vcodec", "libx264",
                                       "-crf", "23", "-preset", "fast", "-acodec", "aac"],
                              "suffix": "_720p"}),
                ActionOption("to_480p", "Уменьшить до 480p (MP4)", ".mp4", self.name,
                             {"args": ["-vf", "scale=-2:480", "-vcodec", "libx264",
                                       "-crf", "23", "-preset", "fast", "-acodec", "aac"],
                              "suffix": "_480p"}),
                ActionOption("to_gif", "GIF (первые 10 с, 320px)", ".gif", self.name,
                             {"args": ["-t", "10", "-vf",
                                       "fps=12,scale=320:-1:flags=lanczos", "-loop", "0"],
                              "suffix": "_gif"}),
                ActionOption("frames", "Кадры PNG (1 кадр/сек, папка)", "", self.name,
                             {"mode": "frames"}),
            ]
        else:
            for fmt, title, codec in self._AUDIO_TARGETS:
                if f".{fmt}" != ext:
                    actions.append(ActionOption(
                        f"audio_to_{fmt}", f"Конвертировать в {title}",
                        f".{fmt}", self.name, {"args": codec, "suffix": "_converted"}))
            actions.append(ActionOption(
                "normalize", "Выровнять громкость (MP3, Loudnorm)", ".mp3", self.name,
                {"args": ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                          "-acodec", "libmp3lame", "-b:a", "192k"], "suffix": "_norm"}))
        return actions

    @staticmethod
    def _cleanup_target(path: Path):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)

    def _run_ffmpeg(self, src: Path, args, out, cleanup, progress_cb, cancel_check):
        cmd = [self.ffmpeg_bin, "-nostdin", "-y", "-i", str(src), *args, str(out)]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            creationflags=creation_flags)
        duration_re = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
        time_re = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
        total_sec = None
        last_reported = -5
        tail = []
        try:
            for line in proc.stderr:
                tail.append(line.rstrip())
                del tail[:-8]
                if cancel_check():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise InterruptedError("Отменено.")
                if total_sec is None:
                    m = duration_re.search(line)
                    if m:
                        total_sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                m = time_re.search(line)
                if m and total_sec:
                    cur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                    pct = max(0, min(99, int(cur / total_sec * 100)))
                    if pct - last_reported >= 5:
                        progress_cb(pct)
                        last_reported = pct
            rc = proc.wait()
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
            self._cleanup_target(cleanup)
            raise
        if rc != 0:
            self._cleanup_target(cleanup)
            detail = " | ".join(l for l in tail if l.strip())[-300:]
            raise RuntimeError(f"FFmpeg (код {rc}). {detail}")
        progress_cb(100)

    def process(self, task, progress_cb, cancel_check):
        if not self.ffmpeg_bin:
            raise RuntimeError("FFmpeg не найден. Положите ffmpeg.exe рядом с программой.")
        action = task.selected_action
        params = action.params

        if params.get("mode") == "frames":
            out_dir = get_safe_output_path(task.source_path, "", suffix="_frames")
            out_dir.mkdir(parents=True, exist_ok=True)
            pattern = out_dir / "frame_%04d.png"
            self._run_ffmpeg(task.source_path, ["-vf", "fps=1"], pattern,
                             out_dir, progress_cb, cancel_check)
            if not any(out_dir.iterdir()):
                shutil.rmtree(out_dir, ignore_errors=True)
                raise RuntimeError("FFmpeg не выдал ни одного кадра.")
            return out_dir

        out_path = get_safe_output_path(
            task.source_path, action.target_ext, suffix=params.get("suffix", "_processed"))
        self._run_ffmpeg(task.source_path, params["args"], out_path,
                         out_path, progress_cb, cancel_check)
        if not out_path.exists():
            raise RuntimeError("FFmpeg не создал файл.")
        return out_path


# --- Реестр ---

HANDLERS: Dict[str, BaseHandler] = {}


def register_handler(handler: BaseHandler):
    HANDLERS[handler.name] = handler


def find_handler(file_path: Path) -> Optional[BaseHandler]:
    ext = file_path.suffix.lower()
    for h in HANDLERS.values():
        if ext in h.supported_extensions:
            return h
    return None


register_handler(ImageHandler())
register_handler(PDFHandler())
register_handler(DocHandler())
register_handler(TextHandler())
register_handler(MediaHandler())


# ==============================================================================
# 3. MНОГОПОТОЧНОСТЬ (WORKER LAYER)
# ==============================================================================

class TaskSignals(QObject):
    progress = Signal(str, int)        # task_id, percent
    finished = Signal(str, str)        # task_id, output_path
    failed = Signal(str, str)          # task_id, error message
    done = Signal(str)                 # task_id — finished or failed


class TaskRunnable(QRunnable):
    def __init__(self, task: FileTask, handler: BaseHandler):
        super().__init__()
        self.task = task
        self.handler = handler
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self):
        task = self.task
        try:
            out = self.handler.process(
                task,
                lambda pct: self.signals.progress.emit(task.id, pct),
                task.is_canceled)
            self.signals.finished.emit(task.id, str(out))
        except InterruptedError as e:
            self.signals.failed.emit(task.id, str(e) or "Отменено")
        except Exception as e:
            self.signals.failed.emit(task.id, f"{type(e).__name__}: {e}")
        finally:
            self.signals.done.emit(task.id)


# ==============================================================================
# 4. ДИЗАЙН (STYLE / CATPPUCCIN MOCHA)
# ==============================================================================

C = {
    "crust":    "#11111b",
    "mantle":   "#181825",
    "base":     "#1e1e2e",
    "surface0": "#313244",
    "surface1": "#45475a",
    "text":     "#cdd6f4",
    "subtext":  "#a6adc8",
    "overlay":  "#6c7086",
    "lavender": "#b4befe",
    "blue":     "#89b4fa",
    "mauve":    "#cba6f7",
    "green":    "#a6e3a1",
    "red":      "#f38ba8",
    "peach":    "#fab387",
    "yellow":   "#f9e2af",
}

def _chevron_url() -> str:
    try:
        from PIL import Image as _Img, ImageDraw as _Draw
        p = Path(tempfile.gettempdir()) / "transformbro_chevron.png"
        if not p.exists():
            img = _Img.new("RGBA", (20, 20), (0, 0, 0, 0))
            _Draw.Draw(img).polygon([(5, 7), (15, 7), (10, 14)], fill=(166, 173, 200, 255))
            img.save(p)
        return p.as_posix()
    except Exception:
        return ""


_CHEVRON = _chevron_url()
_CHEVRON_RULE = f'image: url("{_CHEVRON}");' if _CHEVRON else ""

QSS = f"""
QWidget {{
    background: {C['base']};
    color: {C['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}}
QMainWindow, #central {{ background: {C['base']}; }}

#headerBar {{ background: {C['mantle']}; border-bottom: 1px solid {C['surface0']}; }}
#appTitle {{
    font-size: 21px; font-weight: 800; color: {C['text']};
    background: transparent; border: none; letter-spacing: -0.3px;
}}
#appSubtitle {{
    font-size: 12px; color: {C['overlay']}; background: transparent; border: none;
}}
#pillOk, #pillWarn {{
    font-size: 11px; font-weight: 700; border: none; border-radius: 11px;
    padding: 4px 12px; background: {C['surface0']}; color: {C['subtext']};
    max-height: 22px;
}}
#pillOk {{ background: rgba(166,227,161,0.14); color: {C['green']}; }}
#pillWarn {{ background: rgba(243,139,168,0.14); color: {C['red']}; }}

#dropZone {{
    background: {C['mantle']};
    border: 2px dashed {C['surface1']};
    border-radius: 16px;
}}
#dropZone[hover="true"] {{
    border: 2px dashed {C['mauve']};
    background: rgba(203,166,247,0.07);
}}
#dropTitle {{ font-size: 15px; font-weight: 700; color: {C['subtext']}; background: transparent; border: none; }}
#dropHint {{ font-size: 12px; color: {C['overlay']}; background: transparent; border: none; }}

QPushButton#primary {{
    background: {C['mauve']}; color: {C['crust']};
    border: none; border-radius: 10px;
    padding: 10px 20px; font-weight: 700; font-size: 14px;
}}
QPushButton#primary:hover {{ background: {C['lavender']}; }}
QPushButton#primary:pressed {{ background: {C['blue']}; }}
QPushButton#primary:disabled {{ background: {C['surface0']}; color: {C['overlay']}; }}

QPushButton#ghost {{
    background: {C['surface0']}; color: {C['text']};
    border: 1px solid {C['surface1']}; border-radius: 10px;
    padding: 9px 16px; font-weight: 600;
}}
QPushButton#ghost:hover {{ background: {C['surface1']}; border-color: {C['overlay']}; }}
QPushButton#ghost:disabled {{ color: {C['overlay']}; }}

QPushButton#danger {{
    background: transparent; color: {C['red']};
    border: 1px solid rgba(243,139,168,0.35); border-radius: 8px;
    padding: 5px 12px; font-weight: 600; font-size: 12px;
}}
QPushButton#danger:hover {{ background: rgba(243,139,168,0.12); }}

QPushButton#link {{
    background: transparent; color: {C['blue']}; border: none;
    font-size: 12px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#link:hover {{ color: {C['lavender']}; }}

QComboBox {{
    background: {C['surface0']}; color: {C['text']};
    border: 1px solid {C['surface1']}; border-radius: 8px;
    padding: 7px 12px; font-size: 13px;
    combobox-popup: 0;
}}
QComboBox:hover {{ border-color: {C['overlay']}; }}
QComboBox::drop-down {{
    border: none; width: 28px;
    subcontrol-origin: padding; subcontrol-position: center right;
}}
QComboBox::down-arrow {{
    {_CHEVRON_RULE}
    width: 12px; height: 12px;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {C['surface0']}; color: {C['text']};
    border: 1px solid {C['surface1']}; border-radius: 8px;
    selection-background-color: {C['surface1']}; outline: none; padding: 4px;
}}

#card {{
    background: {C['mantle']};
    border: 1px solid {C['surface0']};
    border-radius: 14px;
}}
#card[state="running"] {{ border-color: rgba(137,180,250,0.45); }}
#card[state="done"] {{ border-color: rgba(166,227,161,0.45); }}
#card[state="error"] {{ border-color: rgba(243,139,168,0.45); }}

#badge {{
    background: {C['surface0']}; color: {C['lavender']};
    border-radius: 8px; font-size: 10px; font-weight: 800;
    padding: 6px 0px; min-width: 42px; max-width: 42px;
    border: none;
}}
#fileName {{ font-size: 14px; font-weight: 700; color: {C['text']}; background: transparent; border: none; }}
#fileMeta {{ font-size: 12px; color: {C['overlay']}; background: transparent; border: none; }}
#statusLabel {{ font-size: 12px; font-weight: 600; background: transparent; border: none; }}

QProgressBar {{
    background: {C['surface0']}; border: none; border-radius: 5px;
    text-align: center; text-inversion: true;
    height: 10px; font-size: 9px; font-weight: 700; color: {C['crust']};
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C['blue']}, stop:1 {C['mauve']});
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['surface1']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['overlay']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QStatusBar {{ background: {C['mantle']}; color: {C['subtext']}; border-top: 1px solid {C['surface0']}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{
    background: {C['surface0']}; color: {C['text']};
    border: 1px solid {C['surface1']}; border-radius: 6px; padding: 6px 8px;
}}
"""


# ==============================================================================
# 5. ВИДЖЕТЫ (UI LAYER)
# ==============================================================================

class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(4)
        title = QLabel("Перетащите файлы сюда")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("или нажмите — документы · изображения · PDF · видео · аудио")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addWidget(hint)

    def mousePressEvent(self, event):
        self._browse()

    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите файлы", os.path.expanduser("~"),
            "Все файлы (*)")
        if paths:
            self.files_dropped.emit(paths)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("hover", "true")
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("hover", "false")
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("hover", "false")
        self.style().polish(self)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)


class FileCard(QFrame):
    run_requested = Signal(str)          # task_id
    cancel_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, task: FileTask, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("card")
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)

        badge_text = {"image": "IMG", "pdf": "PDF", "doc": "DOC",
                      "text": "TXT", "media": "AV"}.get(task.category, "FILE")
        self.badge = QLabel(badge_text)
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedWidth(48)
        top.addWidget(self.badge, 0, Qt.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.name_label = QLabel(task.source_path.name)
        self.name_label.setObjectName("fileName")
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fm = task.source_path.stat().st_size if task.source_path.exists() else 0
        self.meta_label = QLabel(
            f"{human_size(fm)} · {task.source_path.suffix.lstrip('.').upper() or 'без расширения'}")
        self.meta_label.setObjectName("fileMeta")
        info.addWidget(self.name_label)
        info.addWidget(self.meta_label)
        top.addLayout(info, 1)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(250)
        self.combo.setMaximumWidth(320)
        for i, a in enumerate(task.available_actions):
            self.combo.addItem(a.title, i)
        if task.available_actions:
            task.selected_action = task.available_actions[0]
        else:
            self.combo.addItem(task.error_message or "Действия недоступны", -1)
            self.combo.setEnabled(False)
        self.combo.currentIndexChanged.connect(self._action_changed)
        top.addWidget(self.combo, 0, Qt.AlignVCenter)

        self.run_btn = QPushButton("Конвертировать")
        self.run_btn.setObjectName("primary")
        self.run_btn.setEnabled(bool(task.available_actions))
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.task.id))
        top.addWidget(self.run_btn, 0, Qt.AlignVCenter)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task.id))
        top.addWidget(self.cancel_btn, 0, Qt.AlignVCenter)

        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("link")
        self.remove_btn.setToolTip("Убрать из очереди")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.task.id))
        top.addWidget(self.remove_btn, 0, Qt.AlignVCenter)

        outer.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setVisible(False)
        bottom.addWidget(self.progress, 1)

        self.status_label = QLabel(TaskStatus.PENDING.value)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet(f"color: {C['overlay']};")
        bottom.addWidget(self.status_label, 0, Qt.AlignRight)

        self.open_btn = QPushButton("Открыть результат")
        self.open_btn.setObjectName("link")
        self.open_btn.setVisible(False)
        bottom.addWidget(self.open_btn, 0, Qt.AlignRight)

        outer.addLayout(bottom)

    def _action_changed(self, index: int):
        data = self.combo.itemData(index)
        if data is not None and data >= 0 and data < len(self.task.available_actions):
            self.task.selected_action = self.task.available_actions[data]

    def set_state(self, status: TaskStatus, detail: str = ""):
        self.task.status = status
        state_map = {
            TaskStatus.PENDING: ("pending", C['overlay']),
            TaskStatus.PROCESSING: ("running", C['blue']),
            TaskStatus.COMPLETED: ("done", C['green']),
            TaskStatus.ERROR: ("error", C['red']),
            TaskStatus.CANCELED: ("error", C['peach']),
        }
        state, color = state_map[status]
        self.setProperty("state", state)
        self.style().polish(self)
        self.status_label.setText((detail or status.value))
        self.status_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        running = status == TaskStatus.PROCESSING
        finished = status in (TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELED)
        self.run_btn.setVisible(not running)
        self.run_btn.setText("Ещё раз" if finished else "Конвертировать")
        self.run_btn.setEnabled(not running and bool(self.task.available_actions))
        self.cancel_btn.setVisible(running)
        self.combo.setEnabled(not running)
        self.progress.setVisible(running or (finished and self.progress.value() > 0))
        self.open_btn.setVisible(status == TaskStatus.COMPLETED)
        if finished and not running:
            self.progress.setTextVisible(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TransformBro")
        self.resize(1150, 760)
        self.setMinimumSize(880, 560)
        self.setAcceptDrops(True)
        self.tasks: Dict[str, FileTask] = {}
        self.cards: Dict[str, FileCard] = {}
        self.card_order: List[str] = []
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(3)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body_wrap = QWidget()
        body = QVBoxLayout(body_wrap)
        body.setContentsMargins(22, 18, 22, 12)
        body.setSpacing(14)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self.add_paths)
        body.addWidget(self.drop_zone)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.convert_all_btn = QPushButton("Обработать всё")
        self.convert_all_btn.setObjectName("primary")
        self.convert_all_btn.clicked.connect(self.run_all)
        toolbar.addWidget(self.convert_all_btn)

        self.clear_btn = QPushButton("Очистить завершённые")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.clicked.connect(self.clear_finished)
        toolbar.addWidget(self.clear_btn)

        toolbar.addStretch(1)
        self.summary_label = QLabel("Очередь пуста")
        self.summary_label.setStyleSheet(f"color: {C['overlay']}; background: transparent;")
        toolbar.addWidget(self.summary_label)
        body.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(2, 2, 10, 2)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_container)
        body.addWidget(self.scroll, 1)

        root.addWidget(body_wrap, 1)

        self.statusBar().showMessage("Готово")
        self.statusBar().setStyleSheet(f"QStatusBar {{ color: {C['subtext']}; }}")

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("headerBar")
        bar.setFixedHeight(72)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.setSpacing(14)

        title = QLabel("TransformBro")
        title.setObjectName("appTitle")
        lay.addWidget(title, 0, Qt.AlignVCenter)

        sub = QLabel(f"конвертация файлов без установки офисов и кодеков · v{APP_VERSION}")
        sub.setObjectName("appSubtitle")
        lay.addWidget(sub, 0, Qt.AlignVCenter)
        lay.addSpacing(8)

        lay.addStretch(1)

        media = HANDLERS["media"]
        ffmpeg_ok = getattr(media, "ffmpeg_bin", None)
        pills = []
        pill_ff = QLabel("FFmpeg ✓" if ffmpeg_ok else "FFmpeg не найден")
        pill_ff.setObjectName("pillOk" if ffmpeg_ok else "pillWarn")
        pills.append(pill_ff)
        pill_pil = QLabel("Pillow ✓" if HAS_PIL else "Pillow ✕")
        pill_pil.setObjectName("pillOk" if HAS_PIL else "pillWarn")
        pills.append(pill_pil)
        pill_pdf = QLabel("PyMuPDF ✓" if HAS_FITZ else "PyMuPDF ✕")
        pill_pdf.setObjectName("pillOk" if HAS_FITZ else "pillWarn")
        pills.append(pill_pdf)
        for p in pills:
            p.setFixedHeight(22)
            lay.addWidget(p, 0, Qt.AlignVCenter)
        return bar

    # --- очередь ---

    def add_paths(self, paths: List[str]):
        expanded: List[Path] = []
        folders = 0
        for raw in paths:
            p = Path(raw)
            if p.is_file():
                expanded.append(p)
            elif p.is_dir():
                folders += 1
                for child in sorted(p.rglob("*")):
                    if child.is_file() and not any(
                            part.startswith(".") for part in child.relative_to(p).parts):
                        expanded.append(child)
                        if len(expanded) >= 500:
                            break
        added, skipped, unsupported = 0, 0, 0
        for p in expanded:
            already = any(t.source_path == p for t in self.tasks.values())
            if already:
                skipped += 1
                continue
            handler = find_handler(p)
            if not handler:
                unsupported += 1
                continue
            available = handler.available()
            actions = handler.get_actions(p) if available else []
            task = FileTask(
                id=uuid.uuid4().hex,
                source_path=p,
                category=handler.name if handler else "unknown",
                available_actions=actions,
            )
            if not available:
                task.error_message = {
                    "image": "Pillow не установлен",
                    "pdf": "PyMuPDF не установлен",
                    "doc": "Word не найден и нет встроенного парсера",
                    "media": "FFmpeg не найден",
                }.get(handler.name, "Нет нужной библиотеки")
            self.tasks[task.id] = task
            card = FileCard(task)
            card.run_requested.connect(self.run_task)
            card.cancel_requested.connect(self.cancel_task)
            card.remove_requested.connect(self.remove_task)
            card.open_btn.clicked.connect(lambda _, t=task: self._open_output(t))
            self.list_layout.insertWidget(len(self.card_order), card)
            self.cards[task.id] = card
            self.card_order.append(task.id)
            if not actions:
                card.set_state(TaskStatus.ERROR,
                               task.error_message or "Действия недоступны")
                card.setToolTip(task.error_message or "")
            added += 1
        if added or unsupported:
            parts = [f"Добавлено: {added}"]
            if folders:
                parts.append(f"папок: {folders}")
            if skipped:
                parts.append(f"дублей: {skipped}")
            if unsupported:
                parts.append(f"без обработчика: {unsupported}")
            self.statusBar().showMessage(" · ".join(parts))
            QTimer.singleShot(4000, lambda: self.statusBar().clearMessage())
        self._update_summary()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    def closeEvent(self, event):
        running = [t for t in self.tasks.values() if t.status == TaskStatus.PROCESSING]
        for t in running:
            t.request_cancel()
        if running:
            self.pool.waitForDone(8000)
        event.accept()

    def _update_summary(self):
        total = len(self.tasks)
        if total == 0:
            self.summary_label.setText("Очередь пуста")
            return
        done = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        err = sum(1 for t in self.tasks.values() if t.status in (TaskStatus.ERROR, TaskStatus.CANCELED))
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PROCESSING)
        parts = [f"Всего: {total}"]
        if running:
            parts.append(f"В работе: {running}")
        if done:
            parts.append(f"Готово: {done}")
        if err:
            parts.append(f"Ошибок: {err}")
        self.summary_label.setText(" · ".join(parts))

    def run_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task or task.status == TaskStatus.PROCESSING:
            return
        handler = HANDLERS.get(task.selected_action.handler_name if task.selected_action else "")
        if handler is None:
            return
        task._cancel.clear()
        task.status = TaskStatus.PROCESSING
        task.progress = 0
        task.output_path = None
        card = self.cards[task_id]
        card.progress.setValue(0)
        card.set_state(TaskStatus.PROCESSING, "В работе")

        runnable = TaskRunnable(task, handler)
        runnable.signals.progress.connect(self._on_progress)
        runnable.signals.finished.connect(self._on_finished)
        runnable.signals.failed.connect(self._on_failed)
        self.pool.start(runnable)
        self._update_summary()

    def run_all(self):
        started = 0
        for tid in self.card_order:
            task = self.tasks.get(tid)
            if task and task.status == TaskStatus.PENDING and task.selected_action:
                self.run_task(tid)
                started += 1
        if started == 0:
            self.statusBar().showMessage("Нечего обрабатывать — добавьте файлы")
            QTimer.singleShot(2500, lambda: self.statusBar().clearMessage())

    def cancel_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task and task.status == TaskStatus.PROCESSING:
            task.request_cancel()
            self.cards[task_id].set_state(TaskStatus.PROCESSING, "Отменяю…")

    def remove_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        if task.status == TaskStatus.PROCESSING:
            task.request_cancel()
        card = self.cards.pop(task_id, None)
        if card:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self.tasks.pop(task_id, None)
        if task_id in self.card_order:
            self.card_order.remove(task_id)
        self._update_summary()

    def clear_finished(self):
        for tid in list(self.card_order):
            task = self.tasks.get(tid)
            if task and task.status in (TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELED):
                self.remove_task(tid)

    @Slot(str, int)
    def _on_progress(self, task_id: str, pct: int):
        card = self.cards.get(task_id)
        task = self.tasks.get(task_id)
        if card and task and task.status == TaskStatus.PROCESSING:
            card.progress.setValue(pct)

    @Slot(str, str)
    def _on_finished(self, task_id: str, out_path: str):
        task = self.tasks.get(task_id)
        card = self.cards.get(task_id)
        if task and card:
            task.output_path = Path(out_path)
            task.progress = 100
            card.progress.setValue(100)
            card.setToolTip(str(task.output_path))
            card.set_state(TaskStatus.COMPLETED, f"Готово → {Path(out_path).name}")
        self._update_summary()

    @Slot(str, str)
    def _on_failed(self, task_id: str, message: str):
        task = self.tasks.get(task_id)
        card = self.cards.get(task_id)
        if task and card:
            if "Отмен" in message:
                task.status = TaskStatus.CANCELED
                card.set_state(TaskStatus.CANCELED, message)
            else:
                task.error_message = message
                card.set_state(TaskStatus.ERROR, message[:90])
                card.setToolTip(message)
        self._update_summary()

    def _open_output(self, task: FileTask):
        if task.output_path and task.output_path.exists():
            if task.output_path.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.output_path)))
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.output_path.parent)))


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("TransformBro")
    app.setApplicationVersion(APP_VERSION)
    icon_path = resource_path("assets/TransformBro.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(QSS)
    win = MainWindow()
    initial = [a for a in sys.argv[1:] if Path(a).is_file()]
    if initial:
        win.add_paths(initial)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
