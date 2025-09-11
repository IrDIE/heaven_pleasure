#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import argparse, json, html, tempfile, shutil
from pathlib import Path
from collections import defaultdict, Counter
import zipfile

SEVERITIES = ("critical", "major", "minor", "info")

# ---------- utils ----------
def esc(s): return html.escape(str(s)) if s is not None else ""
def norm_sev(s): s=(s or "").strip().lower(); return s if s in SEVERITIES else "minor"

def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    subs = [p for p in dest.iterdir() if p.is_dir()]
    return subs[0] if len(subs)==1 else dest

def detect_project_root(base: Path, hint: str = "") -> Path:
    if hint:
        cand = (base / hint).resolve()
        if cand.exists(): return cand
    subs = [p for p in base.iterdir() if p.is_dir()]
    return subs[0] if len(subs)==1 else base

def read_asset(path: Path) -> str:
    try: return path.read_text(encoding="utf-8")
    except FileNotFoundError: return ""

# ---------- data ----------
def gather_issues_by_file(review: dict):
    per_file = defaultdict(list)
    for it in review.get("issues", []):
        rel = (it.get("file_resolved") or it.get("file") or it.get("path") or "").replace("\\","/").lstrip("./")
        it["_sev"]   = norm_sev(it.get("severity"))
        it["_title"] = it.get("title") or it.get("name") or it.get("rule") or it.get("id") or "Issue"
        it["_desc"]  = it.get("message") or it.get("description") or ""
        per_file[rel].append(it)
    return per_file

def build_fs_list(project_root: Path):
    return [str(p.relative_to(project_root)).replace("\\","/") for p in project_root.rglob("*") if p.is_file()]

def tree_insert(tree, parts, is_file=False):
    node = tree
    for i,part in enumerate(parts):
        last = i==len(parts)-1
        if part not in node["children"]:
            node["children"][part]={"name":part,"children":{},"is_file":last and is_file,"counts":Counter()}
        node = node["children"][part]
        if last and is_file: node["is_file"]=True
    return node

def aggregate_counts(node):
    tot = Counter(node.get("counts", {}))
    for ch in node["children"].values():
        aggregate_counts(ch); tot.update(ch["counts"])
    node["counts"]=tot

def to_dict(node):
    dirs, files = [], []
    for name,ch in node["children"].items():
        d={"name":ch["name"],"is_file":ch["is_file"],"counts":dict(ch["counts"]), "children":[]}
        if ch["is_file"]: files.append(d)
        else: d["children"]=to_dict(ch); dirs.append(d)
    dirs.sort(key=lambda x:x["name"].lower()); files.sort(key=lambda x:x["name"].lower())
    return dirs+files

def build_tree_json(per_file: dict, project_root: Path|None):
    root_name = project_root.name if project_root else "project"
    root = {"name":root_name,"children":{},"is_file":False,"counts":Counter()}

    fs_files=[]
    if project_root:
        fs_files = build_fs_list(project_root)
        for rel in fs_files:
            node = tree_insert(root, rel.split("/"), is_file=True)
            cnt = Counter(norm_sev(i.get("severity")) for i in per_file.get(rel, []))
            node["counts"].update(cnt)

    for rel in per_file.keys():
        if (not project_root) or (rel not in fs_files):
            node = tree_insert(root, rel.split("/"), is_file=True)
            cnt = Counter(norm_sev(i.get("severity")) for i in per_file[rel])
            node["counts"].update(cnt)

    aggregate_counts(root)
    return {"name":root_name,"is_file":False,"counts":dict(root["counts"]), "children":to_dict(root)}

def get_overall(data: dict) -> str:
    # допускаем как строку в корне, так и в data["meta"]["overall"]
    if isinstance(data.get("overall"), str):
        return data["overall"]
    meta = data.get("meta") or {}
    return meta.get("overall") or ""

def get_highlights(data: dict) -> list[str]:
    # допускаем как массив в корне, так и в data["meta"]["highlights"]
    hl = data.get("highlights")
    if isinstance(hl, list):
        return [str(x) for x in hl if x]
    meta = data.get("meta") or {}
    hl = meta.get("highlights") or []
    return [str(x) for x in hl if x]

# ---------- HTML ----------

def page_html(tree_json, issues_by_file, styles: str, script: str, title: str, overall: str = "", highlights: list[str] = None):
    from collections import Counter
    highlights = highlights or []
    counts = Counter()
    for lst in issues_by_file.values():
        counts.update(norm_sev(i.get("severity")) for i in lst)

    # чипы-статистика
    chips=[]
    if counts.get("critical"): chips.append(f'<span class="chip b-crit"><b>{counts["critical"]}</b> critical</span>')
    if counts.get("major"):    chips.append(f'<span class="chip b-major"><b>{counts["major"]}</b> major</span>')
    if counts.get("minor"):    chips.append(f'<span class="chip b-minor"><b>{counts["minor"]}</b> minor</span>')
    if counts.get("info"):     chips.append(f'<span class="chip b-info"><b>{counts["info"]}</b> info</span>')

    # блок Overall (если есть)
    overall_block = ""
    if overall:
        overall_block = f"""
        <section class="card" style="margin-top:12px">
          <div class="card__hd"><h3 class="card__title">Overall</h3></div>
          <div class="card__bd"><p style="margin:0; color:var(--muted)">{esc(overall)}</p></div>
        </section>"""

    # блок Highlights (если есть)
    highlights_block = ""
    if highlights:
        pills = "".join(f'<span class="chip">{esc(h)}</span>' for h in highlights)
        highlights_block = f"""
        <section class="card" style="margin-top:12px">
          <div class="card__hd"><h3 class="card__title">Highlights</h3></div>
          <div class="card__bd"><div class="chips">{pills}</div></div>
        </section>"""

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>{styles}</style>
</head>
<body>
  <div class="container">
    <h1 class="h1">{esc(title)}</h1>
    <p class="sub">Select a file on the left to see issues and code snippets.</p>

    <div class="chips" style="margin-top:12px">{''.join(chips)}</div>
    {overall_block}
    {highlights_block}

    <div class="grid" style="margin-top:16px">
      <!-- left: file tree -->
      <section class="card">
        <div class="card__hd"><h3 class="card__title">Project Files</h3></div>
        <div class="card__bd"><div id="tree"></div></div>
      </section>

      <!-- right: issues -->
      <section class="card">
        <div class="card__hd"><h3 class="card__title">Review Details</h3></div>
        <div class="card__bd" id="content">
          <p class="empty">Select a file on the left to see issues and code snippets.</p>
        </div>
      </section>
    </div>
  </div>

  <script id="__TREE__" type="application/json">{json.dumps(tree_json, ensure_ascii=False)}</script>
  <script id="__ISSUES__" type="application/json">{json.dumps(issues_by_file, ensure_ascii=False)}</script>
  <script>{script}</script>
</body>
</html>"""

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Render single HTML report in 'Upload page' style with tree")
    ap.add_argument("--json", required=True, type=Path, help="autoreview_with_snippets.json")
    ap.add_argument("--out", required=True, type=Path, help="report.html")
    ap.add_argument("--title", default="AutoReview — Project Dashboard")
    grp = ap.add_mutually_exclusive_group(required=False)
    grp.add_argument("--project", type=Path, help="project folder OR .zip")
    grp.add_argument("--zip", type=Path, help="project.zip")
    ap.add_argument("--assets-dir", type=Path, default=Path(__file__).parent.parent / "assets",
                    help="folder with upload_theme.css and tree.js")
    args = ap.parse_args()

    data = load_json(args.json)

    overall = get_overall(data)
    highlights = get_highlights(data)

    # styles & script
    # приоритет: upload_theme.css, иначе styles.css
    up_css = (args.assets_dir / "upload_theme.css")
    styles = read_asset(up_css) if up_css.exists() else read_asset(args.assets_dir / "styles.css")
    script = read_asset(args.assets_dir / "tree.js")

    # optional real FS
    project_root = None; temp = None
    if args.project:
        p = args.project.resolve()
        if p.is_dir(): project_root = p
        elif p.is_file() and p.suffix.lower()==".zip":
            temp = Path(tempfile.mkdtemp(prefix="proj_extract_"))
            project_root = detect_project_root(extract_zip(p, temp), data.get("root",""))
        else:
            raise SystemExit(f"[ERR] --project must be a folder or .zip, got: {p}")
    elif args.zip:
        z = args.zip.resolve()
        if not z.is_file(): raise SystemExit(f"[ERR] ZIP not found: {z}")
        temp = Path(tempfile.mkdtemp(prefix="proj_extract_"))
        project_root = detect_project_root(extract_zip(z, temp), data.get("root",""))

    per_file = gather_issues_by_file(data)
    tree_json = build_tree_json(per_file, project_root)

    html_text = page_html(tree_json, per_file, styles, script, args.title, overall=overall, highlights=highlights)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_text, encoding="utf-8")
    print(f"[OK] saved: {args.out}")

    if temp and temp.exists(): shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    main()
