# common.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, zipfile, sys, os
from pathlib import Path
from typing import List, Tuple, Optional

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    # если внутри архива единственная папка — используем её как корень
    subs = [p for p in dest.iterdir() if p.is_dir()]
    return subs[0] if len(subs) == 1 else dest

def detect_project_root(base: Path, hint: str = "") -> Path:
    if hint:
        cand = (base / hint).resolve()
        if cand.exists():
            return cand
    subs = [p for p in base.iterdir() if p.is_dir()]
    return subs[0] if len(subs) == 1 else base

def read_file_lines(full_path: Path) -> Optional[List[str]]:
    if not full_path.is_file():
        return None
    try:
        return full_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return full_path.read_text(encoding="cp1251", errors="replace").splitlines()

def locate_file(project_root: Path, rel_path: str) -> Optional[Path]:
    """
    Сначала пробуем относительный путь из JSON, иначе ищем по имени файла.
    """
    if not rel_path:
        return None
    norm = rel_path.replace("\\", "/").lstrip("./")
    direct = (project_root / norm)
    if direct.is_file():
        return direct
    fname = Path(norm).name
    for p in project_root.rglob(fname):
        if p.is_file():
            return p
    return None

def build_snippet(lines: List[str], center_line: int, context: int) -> Tuple[List[str], int, int, int]:
    """
    Возвращает (snippet_lines, highlight_index, start, end)
    где start/end — номера строк в исходнике (1-based).
    """
    n = len(lines)
    if n == 0:
        return [], 0, 0, 0
    center = max(1, min(int(center_line or 1), n))
    start = max(1, center - context)
    end = min(n, center + context)
    snippet = lines[start-1:end]
    highlight_idx = center - start
    return snippet, highlight_idx, start, end
