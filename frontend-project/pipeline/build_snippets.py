#!/usr/bin/env python3
# build_snippets.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, shutil, tempfile
from pathlib import Path
from common import (
    eprint, load_json, save_json,
    extract_zip, detect_project_root, locate_file,
    read_file_lines, build_snippet
)

def process(review: dict, project_root: Path, context: int):
    issues = review.get("issues", [])
    for issue in issues:
        rel = issue.get("file") or issue.get("path") or ""
        line = issue.get("line", 1)

        resolved = locate_file(project_root, rel) if rel else None
        if not resolved:
            issue["snippet"] = []
            issue["highlight"] = None
            issue["file_resolved"] = None
            continue

        lines = read_file_lines(resolved) or []
        snippet, hi, start, end = build_snippet(lines, line, context)

        issue["snippet"] = snippet
        issue["highlight"] = hi
        issue["file_resolved"] = str(resolved.relative_to(project_root))
        issue["snippet_range"] = {"start": start, "end": end}

    return review

def main():
    ap = argparse.ArgumentParser(description="Собрать сниппеты по проекту и обновить autoreview.json")
    ap.add_argument("--json", required=True, type=Path, help="Путь к autoreview.json")
    ap.add_argument("--project", type=Path, help="Папка проекта (если уже распакована)")
    ap.add_argument("--zip", type=Path, help="Архив проекта (.zip)")
    ap.add_argument("--out-json", required=True, type=Path, help="Куда сохранить autoreview_with_snippets.json")
    ap.add_argument("--context", type=int, default=5, help="Контекст строк сверху/снизу")
    args = ap.parse_args()

    review = load_json(args.json)
    root_hint = review.get("root", "")

    temp_dir = None
    if args.project and args.project.exists():
        base = args.project.resolve()
    elif args.zip and args.zip.is_file():
        temp_dir = Path(tempfile.mkdtemp(prefix="proj_extract_"))
        base = extract_zip(args.zip, temp_dir)
    else:
        eprint("[ERR] Укажите --project или --zip")
        raise SystemExit(2)

    project_root = detect_project_root(base, root_hint)
    print(f"[INFO] root: {project_root}")

    updated = process(review, project_root, args.context)
    save_json(args.out_json, updated)
    print(f"[OK] updated JSON: {args.out_json}")

    # Чистим временную распаковку
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()

