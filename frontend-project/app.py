from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import sqlite3
import datetime, time
import threading
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import glob, tempfile, shutil, sys
from typing import Optional
import subprocess

debug_local = True

# --- подключаем твой пайплайн как модули ---
PIPELINE_DIR = Path(__file__).parent / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import common as pcommon                   # pipeline/common.py
import build_snippets as bs                # pipeline/build_snippets.py
import render_review_html as rrh           # pipeline/render_review_html.py

# --- пути ---
PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR     = PROJECT_ROOT / "data"
ASSETS_DIR   = PROJECT_ROOT / "public" / "assets"
REPORTS_DIR  = PROJECT_ROOT / "review_reports"

SNIPPET_CONTEXT = int(os.environ.get("SNIPPET_CONTEXT", "6"))

def _fmt_dt_for_title(value) -> str:
    # SQLite отдаёт ISO-строку вида "YYYY-MM-DD HH:MM:SS"
    import datetime as _dt
    try:
        if isinstance(value, _dt.datetime):
            dt = value
        else:
            dt = _dt.datetime.fromisoformat(str(value).replace("Z",""))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value) if value is not None else ""


from pathlib import Path
import glob, tempfile, shutil, sys
from typing import Optional, Tuple

# --- подключаем твой пайплайн как модули ---
PIPELINE_DIR = Path(__file__).parent / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import common as pcommon                   # pipeline/common.py
import build_snippets as bs                # pipeline/build_snippets.py
import render_review_html as rrh           # pipeline/render_review_html.py

# --- пути ---
PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR     = PROJECT_ROOT / "data"
ASSETS_DIR   = PROJECT_ROOT / "public" / "assets"
REPORTS_DIR  = PROJECT_ROOT / "review_reports"

SNIPPET_CONTEXT = int(os.environ.get("SNIPPET_CONTEXT", "6"))

import zipfile
from tools.linters import analyze_repository   # если функция в другом файле — поправьте импорт
from src.llm.multiagent import get_reviewer_singleton

LINTERS_JSON = DATA_DIR / "linters.json"
MULTIAGENT_JSON = DATA_DIR / "multiagent.json"

REVIEWER = get_reviewer_singleton(
    WORKSPACE_DIR=str(DATA_DIR / "workspace"),
)

# Create directories and files
DATA_DIR.mkdir(parents=True, exist_ok=True)
if not LINTERS_JSON.exists():
    LINTERS_JSON.write_text("[]", encoding="utf-8")
if not MULTIAGENT_JSON.exists():
    MULTIAGENT_JSON.write_text("{}", encoding="utf-8")

def _fmt_dt_for_title(value) -> str:
    # SQLite отдаёт ISO-строку вида "YYYY-MM-DD HH:MM:SS"
    import datetime as _dt
    try:
        if isinstance(value, _dt.datetime):
            dt = value
        else:
            dt = _dt.datetime.fromisoformat(str(value).replace("Z",""))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value) if value is not None else ""


# Configuration
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "zip"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# In-memory user storage (replace with a real database in production)
users = {"t": {"password": "t", "name": "Test User"}}

htmls_path = "./public/"


# Database initialization
def init_db_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  last_login TIMESTAMP)''')
    conn.commit()
    conn.close()
    print("\n\n -->>>> Database USER initialized.")

# Initialize the database
init_db_users()

def get_db_connection_users():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn



@app.route("/")
def serve_indexroot():
    return send_from_directory(".", os.path.join(htmls_path, "index.html"))


@app.route("/create-account")
def serve_create_acc():
    return send_from_directory(".", os.path.join(htmls_path, "create-account.html"))


@app.route("/login")
def serve_login():
    return send_from_directory(".", os.path.join(htmls_path, "index.html"))


@app.route("/index")
def serve_index():
    return send_from_directory(".", os.path.join(htmls_path, "index.html"))


@app.route("/main_page")
def serve_main_page():
    return send_from_directory(".", os.path.join(htmls_path, "main_page.html"))


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(".", path)


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    print(f"\n\nGOT from logit {username}, {password}\n\n")

    conn = get_db_connection_users()
    c = conn.cursor()
    
    # Get user from database
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        # Update last login time
        conn = get_db_connection_users()
        c = conn.cursor()
        c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": {
                "username": username, 
                "name": username
            }
        })
    else:
        return (
            jsonify({"success": False, "message": "Invalid username or password"}),
            401,
        )


@app.route("/api/create-account", methods=["POST"])
def create_account():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    print(f"\n\nCreating new user: {username, password}\n\n")

    # Validation
    if not username or not password:
        return (
            jsonify({
                "success": False, 
                "message": "Username and password are required"
            }),
            400,
        )

    if len(username) < 3:
        return (
            jsonify({
                "success": False, 
                "message": "Username must be at least 3 characters long"
            }),
            400,
        )

    if len(password) < 6:
        return (
            jsonify({
                "success": False, 
                "message": "Password must be at least 6 characters long"
            }),
            400,
        )

    conn = get_db_connection_users()
    c = conn.cursor()
    
    # Check if username already exists
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Username already exists"}), 409

    # Hash password and store new user
    password_hash = generate_password_hash(password)
    
    try:
        c.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True, 
            "message": "Account created successfully",
            "user": {
                "username": username,
                "name": username
            }
        })
    except sqlite3.Error as e:
        conn.close()
        return jsonify({
            "success": False, 
            "message": f"Database error: {str(e)}"
        }), 500


# Initialize database
def init_db():
    conn = sqlite3.connect("projects.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_name TEXT NOT NULL,
                  description TEXT,
                  project_type TEXT NOT NULL,
                  file_path TEXT,
                  project_url TEXT,
                  username TEXT NOT NULL,
                  status TEXT DEFAULT 'pending',
                  review_type TEXT DEFAULT 'system',
                  review_html_path TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  sent_for_review_at TIMESTAMP,
                  review_completed_at TIMESTAMP)"""
    )
    conn.commit()
    conn.close()
    print("\n\n -->>>> Database initialized.")


init_db()



def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    conn = sqlite3.connect("projects.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/api/upload-project", methods=["POST"])
def upload_project():
    # Check if user is logged in
    # You might want to implement proper session management

    # Check if it's a file upload or link submission
    if request.content_type.startswith("multipart/form-data"):
        # File upload handling
        if "files" not in request.files:
            return jsonify({"success": False, "message": "No files provided"}), 400

        files = request.files.getlist("files")
        project_name = request.form.get("project_name")
        description = request.form.get("description", "")
        username = request.form.get("username", "anonymous")

        if not project_name:
            return (
                jsonify({"success": False, "message": "Project name is required"}),
                400,
            )

        # Process each file
        saved_files = []
        for file in files:
            if file.filename == "":
                continue

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Create user directory if it doesn't exist
                user_dir = os.path.join(
                    app.config["UPLOAD_FOLDER"], username, str(time.time())
                )
                os.makedirs(user_dir, exist_ok=True)

                filepath = os.path.join(user_dir, filename)
                file.save(filepath)
                saved_files.append(filename)

        if not saved_files:
            return (
                jsonify({"success": False, "message": "No valid files uploaded"}),
                400,
            )

        # Save project info to database
        conn = get_db_connection()
        c = conn.cursor()

        # For multiple files, we'll store the first file path and note there are multiple
        file_path = os.path.join(username, saved_files[0]) if saved_files else None

        c.execute(
            """INSERT INTO projects 
                    (project_name, description, project_type, file_path, username, status)
                    VALUES (?, ?, ?, ?, ?, ?)""",
            (project_name, description, "file", file_path, username, "uploaded"),
        )

        project_id = c.lastrowid

        # If multiple files, you might want to create a separate table for file attachments
        if len(saved_files) > 1:
            # Create a table for additional files if needed
            pass

        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "message": f'Project "{project_name}" uploaded successfully with {len(saved_files)} file(s)',
                "project_id": project_id,
                "files": saved_files,
            }
        )

    else:
        # Link submission handling
        data = request.get_json()
        project_url = data.get("project_url")
        project_name = data.get("project_name")
        description = data.get("description", "")
        username = data.get("username", "anonymous")

        if not project_url:
            return (
                jsonify({"success": False, "message": "Project URL is required"}),
                400,
            )

        if not project_name:
            return (
                jsonify({"success": False, "message": "Project name is required"}),
                400,
            )

        # Validate URL format (simple validation)
        if not (
            project_url.startswith("http://") or project_url.startswith("https://")
        ):
            return jsonify({"success": False, "message": "Invalid URL format"}), 400

        # Сохраняем ссылку в файл
        user_dir = os.path.join(
            app.config["UPLOAD_FOLDER"], username, str(time.time())
        )
        os.makedirs(user_dir, exist_ok=True)
        
        # Создаем файл с ссылкой
        link_file = os.path.join(user_dir, "project.git")
        with open(link_file, 'w') as f:
            f.write(project_url)

        # Save project info to database
        conn = get_db_connection()
        c = conn.cursor()

        c.execute(
            """INSERT INTO projects 
                    (project_name, description, project_type, project_url, username, status)
                    VALUES (?, ?, ?, ?, ?, ?)""",
            (project_name, description, "link", project_url, username, "uploaded"),
        )

        project_id = c.lastrowid
        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "message": f'Project "{project_name}" link submitted successfully',
                "project_id": project_id,
                "url": project_url,
            }
        )


# New endpoint to get user's projects from database
@app.route("/api/user-projects", methods=["GET"])
def get_user_projects():
    username = request.args.get("username")

    if not username:
        return jsonify({"success": False, "message": "Username is required"}), 400

    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """SELECT id, project_name, description, project_type, status, 
                 created_at, review_type FROM projects 
                 WHERE username = ? ORDER BY created_at DESC""",
        (username,),
    )

    projects = c.fetchall()
    conn.close()

    # Convert to list of dictionaries
    projects_list = []
    for project in projects:
        projects_list.append(
            {
                "id": project["id"],
                "project_name": project["project_name"],
                "description": project["description"],
                "project_type": project["project_type"],
                "status": project["status"],
                # исходное значение как есть
                "created_at": project["created_at"],
                # удобная строка с секундами
                "created_at_hms": _fmt_dt_for_title(project["created_at"]),
                "review_type": project["review_type"],
            }
        )

    return jsonify({"success": True, "projects": projects_list})


@app.route("/api/my_last_review", methods=["POST"])
def my_last_review():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    print(f"\n\nLast review request for user: {username}\n\n")

    conn = get_db_connection_users()
    c = conn.cursor()
    
    # Verify user credentials
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        # Here you would typically fetch the user's last review from a reviews table
        # For now, we'll return a mock response
        return jsonify({
            "success": True,
            "message": "Last review retrieved successfully",
            "review": {
                "id": 1,
                "title": "Sample Review",
                "date": "2023-12-15",
                "status": "completed"
            },
            "user": {
                "username": username, 
                "name": username
            }
        })
    else:
        return (
            jsonify({"success": False, "message": "Invalid username or password"}),
            401,
        )


# Endpoint to send project for review
@app.route("/api/send-for-review", methods=["POST"])
def send_for_review():
    data = request.get_json()
    username = data.get("username")

    if not username:
        return jsonify({"success": False, "message": "Username is required"}), 400

    # Get the latest project for this user
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """SELECT * FROM projects 
                 WHERE username = ? 
                 ORDER BY created_at DESC LIMIT 1""",
        (username,),
    )

    project = c.fetchone()

    if not project:
        return (
            jsonify({"success": False, "message": "No projects found for this user"}),
            404,
        )

    # Update project status to "in_review"
    c.execute(
        """UPDATE projects 
                 SET status = ?, sent_for_review_at = ?, updated_at = ?
                 WHERE id = ?""",
        ("in_review", datetime.datetime.now(), datetime.datetime.now(), project["id"]),
    )

    conn.commit()
    conn.close()

    # Prepare data for LLM processing
    project_data = {
        "project_name": project["project_name"],
        "description": project["description"],
        "project_type": project["project_type"],
        "username": project["username"],
        "uploaded_at": project["created_at"],   # <— добавили
    }


    # Start async review process
    process_review_async(project["id"], project_data)

    return jsonify(
        {
            "success": True,
            "message": "Project sent for review",
            "project_id": project["id"],
        }
    )


# Endpoint to get review report
@app.route("/api/review-report/<int:project_id>", methods=["GET"])
def get_review_report(project_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))

    project = c.fetchone()
    conn.close()

    if not project:
        return jsonify({"success": False, "message": "Project not found"}), 404

    if project["status"] != "completed" or not project["review_html_path"]:
        return jsonify({"success": False, "message": "Review not completed yet"}), 404

    # Serve the HTML report
    try:
        return send_from_directory(
            os.path.dirname(project["review_html_path"]),
            os.path.basename(project["review_html_path"]),
        )
    except FileNotFoundError:
        return jsonify({"success": False, "message": "Report file not found"}), 404

def _normalize_linter_issues(raw: list[dict]) -> list[dict]:
    """Приводим линовские ошибки к формату issues, понятному рендеру."""
    out = []
    for it in raw or []:
        rel = (it.get("file") or "").replace("\\", "/").lstrip("./")
        sev_raw = (it.get("severity") or "").lower()
        sev = "major" if sev_raw in ("error", "fatal") else "minor"
        out.append({
            "id": it.get("rule") or "lint",
            "file": rel,
            "line": int(it.get("line") or 1),
            "column": it.get("column"),
            "severity": sev,
            "title": it.get("rule") or (it.get("message") or "Lint issue")[:80],
            "message": it.get("message") or "",
            "source": it.get("tool") or "linters",
            # для рендера / бейджа:
            "_source": "Linters",
            "_sev": sev,
            "_title": it.get("rule") or (it.get("message") or "Lint issue")[:80],
            "_desc": it.get("message") or "",
        })
    return out

def _merge_per_file(*dicts: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Склеиваем словари {file: [issues]} с сохранением порядка."""
    merged: dict[str, list[dict]] = {}
    for d in dicts:
        for rel, items in (d or {}).items():
            merged.setdefault(rel, []).extend(items)
    return merged

def llm_simulator(data):
    """
    Заглушка: просто читает data/autoreview.json и возвращает его содержимое.
    """
    time.sleep(10)
    src = DATA_DIR / "autoreview.json"
    try:
        with src.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[llm_simulator] не удалось прочитать {src}: {e}")
        # безопасный минимум
        return {"issues": [], "meta": {"overall": "", "highlights": []}}



def _find_latest_project(username: Optional[str] = None) -> Optional[Path]:
    """
    Ищет последний проект: ZIP-архив или Git-репозиторий в директории пользователя.
    """
    base = PROJECT_ROOT / UPLOAD_FOLDER
    if username:
        base = base / username
    
    # Ищем ZIP-архивы
    zip_patterns = [str(base / "**" / "project.zip"), str(base / "**" / "*.zip")]
    zip_candidates = []
    for pat in zip_patterns:
        zip_candidates.extend(glob.glob(pat, recursive=True))
    
    # Ищем файлы с Git-ссылками
    git_patterns = [str(base / "**" / "*.git"), str(base / "**" / "*.txt")]
    git_candidates = []
    for pat in git_patterns:
        git_candidates.extend(glob.glob(pat, recursive=True))
    
    # Объединяем кандидатов
    all_candidates = zip_candidates + git_candidates
    cand_paths = [Path(p) for p in set(all_candidates) if os.path.isfile(p)]
    
    if not cand_paths:
        return None
    
    # Сортируем по времени изменения
    cand_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cand_paths[0]

def _run_linters_for_user(username: Optional[str]) -> dict:
    """
    Обрабатывает последний проект (ZIP или Git), запускает линтеры и сохраняет результат.
    """
    project_path = _find_latest_project(username=username)
    if not project_path:
        raise FileNotFoundError("Не найден проект для запуска линтеров")

    tmp_dir = Path(tempfile.mkdtemp(prefix="linters_"))
    repo_dir = tmp_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Обработка ZIP-архива
        if project_path.suffix == '.zip':
            with zipfile.ZipFile(project_path, 'r') as z:
                z.extractall(repo_dir)
        # Обработка Git-репозитория
        elif project_path.suffix in ('.git', '.txt'):
            # Читаем URL из файла
            with open(project_path, 'r') as f:
                git_url = f.read().strip()
            # Клонируем репозиторий
            subprocess.run(['git', 'clone', git_url, repo_dir], check=True, capture_output=True)
        else:
            raise ValueError("Неподдерживаемый формат проекта")

        issues, _ = analyze_repository(str(repo_dir), keep=False, verbose=False)

        with open(LINTERS_JSON, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)

        return {"linters_count": len(issues), "linters_json": str(LINTERS_JSON)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_repo_to_tmp_for_user(
    username: Optional[str] = None,
    limit: int = 100
) -> Tuple[Path, Path, list[Path]]:
    """
    Распаковывает последний проект (ZIP или Git) для пользователя, 
    чистит от мусорных директорий и бинарников,
    возвращает (tmp_dir, repo_dir, список исходников).
    """
    project_path = _find_latest_project(username=username)
    if not project_path:
        raise FileNotFoundError("Не найден проект для анализа мультиагентами")

    tmp_dir = Path(tempfile.mkdtemp(prefix="ma_repo_"))
    repo_dir = tmp_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    bad_dirs = (
        "__pycache__/", ".venv/", "venv/", "node_modules/", ".mypy_cache/",
        ".pytest_cache/", ".git/", "dist/", "build/", "target/", "out/"
    )
    binary_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".exe", ".dll", ".so", ".dylib",
        ".zip", ".tar", ".gz", ".rar", ".7z", ".mp4", ".mp3", ".woff", ".woff2",
        ".otf", ".ttf", ".svg", ".yaml"
    }
    
    # Добавьте исключение для Git служебных файлов
    git_ignore_patterns = (
        ".git/", ".gitignore", ".gitattributes", ".gitmodules",
        "*.sample",  # Исключаем все .sample файлы (Git hooks)
    )

    # Обработка ZIP-архива
    if project_path.suffix == '.zip':
        with zipfile.ZipFile(project_path, "r") as z:
            for member in z.namelist():
                # Пропускаем служебные файлы Git
                if any(pattern in member for pattern in git_ignore_patterns):
                    continue
                if any(part in member for part in bad_dirs):
                    continue
                z.extract(member, repo_dir)
    # Обработка Git-репозитория
    elif project_path.suffix in ('.git', '.txt'):
        with open(project_path, 'r') as f:
            git_url = f.read().strip()
        # Клонируем репозиторий, но исключаем служебные файлы
        subprocess.run(['git', 'clone', git_url, repo_dir], check=True, capture_output=True)
        
        # Удаляем служебные файлы Git после клонирования
        for pattern in git_ignore_patterns:
            for file_path in repo_dir.rglob(pattern):
                if file_path.is_file():
                    file_path.unlink()
                elif file_path.is_dir():
                    shutil.rmtree(file_path, ignore_errors=True)
    else:
        raise ValueError("Неподдерживаемый формат проекта")

    # Собрать список файлов, исключая служебные
    files: list[Path] = []
    for p in repo_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in binary_exts:
            continue
        # Дополнительная проверка на служебные файлы Git
        if any(pattern in str(p) for pattern in git_ignore_patterns):
            continue
        files.append(p)
        if len(files) >= limit:
            break

    return tmp_dir, repo_dir, files



def llm_analyze_repo_per_file(
    username: Optional[str],
    *,
    out_path: Path = MULTIAGENT_JSON,
    limit: int = 100,
    run_tests: bool = False
) -> dict:
    """
    Гоняет REVIEWER по файлам, агрегирует результаты в ОДИН общий dict 'autoreview'
    и пишет его в out_path.
    """
    # имя архива (для поля archive)
    try:
        z = _find_latest_project(username=username)
        archive_name = z.name if z else None
    except Exception:
        archive_name = None

    tmp_dir, repo_dir, files = _extract_repo_to_tmp_for_user(username, limit)

    # хелперы
    def top_level_dir(relpath: str) -> Optional[str]:
        parts = relpath.split("/")
        return parts[0] if parts and len(parts) > 1 else None

    def dedup_seq(seq, key):
        seen = set(); out = []
        for x in seq or []:
            k = key(x)
            if k in seen: 
                continue
            seen.add(k); out.append(x)
        return out

    agg_positives: list[dict] = []
    agg_issues: list[dict] = []
    agg_highlights: list[str] = []
    overall_parts: list[str] = []
    roots: list[str] = []

    try:
        for path in files:
            rel = path.relative_to(repo_dir).as_posix()
            root = top_level_dir(rel)
            if root:
                roots.append(root)

            # читаем текст
            try:
                code_text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                # добавим мягкое сообщение в overall
                overall_parts.append(f"Не удалось прочитать {rel}: {e}")
                continue

            # ревью
            try:
                review = REVIEWER.review_code(
                    code=code_text,
                    filename=path.name,
                    run_tests=run_tests,
                )
                payload = review if isinstance(review, dict) else json.loads(json.dumps(review, default=str))
            except Exception as e:
                overall_parts.append(f"Ошибка review для {rel}: {e}")
                continue

            # собираем
            if payload.get("overall"):
                overall_parts.append(str(payload["overall"]).strip())

            # highlights
            hl = (((payload.get("summary") or {}).get("highlights")) or [])
            agg_highlights.extend([str(h).strip() for h in hl if h])

            # positives / issues
            agg_positives.extend(payload.get("positives") or [])
            agg_issues.extend(payload.get("issues") or [])

        # root: самый частый верхний каталог
        root_value = None
        if roots:
            from collections import Counter
            root_value = Counter(roots).most_common(1)[0][0]

        # дедупликации
        agg_highlights = dedup_seq(agg_highlights, key=lambda s: s)[:10]
        agg_positives = dedup_seq(
            agg_positives,
            key=lambda x: (x.get("file"), x.get("line"), x.get("message"))
        )
        agg_issues = dedup_seq(
            agg_issues,
            key=lambda x: (x.get("id"), x.get("file"), x.get("line"), x.get("message"))
        )

        # подсчёт major/minor (critical считаем как major)
        major = minor = 0
        for it in agg_issues:
            sev = (it.get("severity") or "").lower()
            if sev in ("critical", "major"):
                major += 1
            else:
                minor += 1

        overall_text = " | ".join(dedup_seq(
            [p for p in (s.strip() for s in overall_parts) if p],
            key=lambda s: s
        ))

        # финальный единственный объект
        final_payload = {
            "agent": "autoreview",
            "role": "reviewer",
            "name": "AutoReview",
            "archive": archive_name,
            "root": root_value,
            "summary": {
                "issue_counts": {"major": major, "minor": minor},
                "highlights": agg_highlights
            },
            "overall": overall_text,
            "positives": agg_positives,
            "issues": agg_issues
        }

        # запись ОДНОГО dict
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(final_payload, f, ensure_ascii=False, indent=2)

        return {"success": True, "files": len(files), "output": str(out_path)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # чистим workspace, сохраняя .log
        try:
            workspace_dir = DATA_DIR / "workspace"
            if workspace_dir.exists():
                for p in workspace_dir.iterdir():
                    try:
                        if p.is_dir():
                            shutil.rmtree(p, ignore_errors=True)
                        elif p.is_file() and p.suffix != ".log":
                            p.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass


def llm_answer_to_html_simulator(
    answer, *, username: Optional[str] = None,
    project_id: Optional[int] = None,
    project_name: Optional[str] = None,
    uploaded_at: Optional[str] = None
) -> str:

    print("[PIPE] llm_answer_to_html_simulator: using pipeline renderer")
    project_path = _find_latest_project(username=username)
    if not project_path:
        raise FileNotFoundError("В uploads/ не найден проект")

    tempdir = Path(tempfile.mkdtemp(prefix="report_"))
    try:
        # Обработка ZIP-архива
        if project_path.suffix == '.zip':
            base = pcommon.extract_zip(project_path, tempdir)
        # Обработка Git-репозитория
        elif project_path.suffix in ('.git', '.txt'):
            # Читаем URL из файла
            with open(project_path, 'r') as f:
                git_url = f.read().strip()
            # Клонируем репозиторий
            repo_dir = tempdir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', git_url, repo_dir], check=True, capture_output=True)
            base = repo_dir
        else:
            raise ValueError("Неподдерживаемый формат проекта")

        project_root = pcommon.detect_project_root(base, (answer or {}).get("root", ""))

        # 1) LLM-issues → добавляем сниппеты
        llm_raw = json.loads((MULTIAGENT_JSON).read_text(encoding="utf-8")) if MULTIAGENT_JSON.exists() else {}
        review_llm = bs.process(llm_raw, project_root, context=SNIPPET_CONTEXT)

        # 2) Linters → читаем, нормализуем и тоже добавляем сниппеты
        linters_raw = json.loads((LINTERS_JSON).read_text(encoding="utf-8")) if LINTERS_JSON.exists() else []
        linters_norm = _normalize_linter_issues(linters_raw)
        # прогоняем через тот же билд-сниппетов (обёртываем во временный review-словарь)
        linters_review_like = {"issues": linters_norm}
        linters_with_snips = bs.process(linters_review_like, project_root, context=SNIPPET_CONTEXT)

        # 3) Собираем per_file отдельно и склеиваем (LLM + Linters)
        per_file_llm     = rrh.gather_issues_by_file(review_llm)
        per_file_linters = rrh.gather_issues_by_file(linters_with_snips)
        per_file_all     = _merge_per_file(per_file_llm, per_file_linters)

        # 4) Строим дерево по объединённым данным
        tree_json = rrh.build_tree_json(per_file_all, project_root)

        # 5) Текстовые блоки из LLM
        overall    = rrh.get_overall(review_llm)
        highlights = rrh.get_highlights(review_llm)

        # 6) Статика
        css_path = ASSETS_DIR / "assets" / "upload_theme.css" if (ASSETS_DIR / "assets").exists() else ASSETS_DIR / "upload_theme.css"
        # на случай, если assets у тебя лежат в public/assets — пробуем оба варианта
        if not css_path.exists():
            css_path = PROJECT_ROOT / "assets" / "upload_theme.css"
        styles = (css_path.read_text(encoding="utf-8")
                  if css_path.exists()
                  else (PROJECT_ROOT / "assets" / "styles.css").read_text(encoding="utf-8"))
        # tree.js также пробуем по обоим путям
        script_path = ASSETS_DIR / "assets" / "tree.js" if (ASSETS_DIR / "assets").exists() else ASSETS_DIR / "tree.js"
        if not script_path.exists():
            script_path = PROJECT_ROOT / "assets" / "tree.js"
        script = script_path.read_text(encoding="utf-8")

        # 7) Заголовок
        pname = (project_name or "").strip()
        when  = _fmt_dt_for_title(uploaded_at)
        suffix = " ".join(filter(None, [pname, f"({when})" if when else ""]))
        title = f"AutoReview — {suffix}" if suffix else "AutoReview — отчёт по проекту"

        # 8) Рендер
        html_text = rrh.page_html(tree_json, per_file_all, styles, script, title,
                                  overall=overall, highlights=highlights)

        # 9) Сохраняем
        reports_d = REPORTS_DIR / username
        reports_d.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = reports_d / f"review_{project_id or 'latest'}_{ts}.html"

        out.write_text(html_text, encoding="utf-8")
        print(f"[PIPE] saved: {out}")
        return str(out.resolve())
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def process_review_async(project_id, project_data):
    """Process review asynchronously in a separate thread"""

    def review_task():
        # A) СНАЧАЛА прогоняем линтеры и сохраняем data/linters.json
        try:
            linters_res = _run_linters_for_user(project_data.get("username"))
            print(f"[linters] saved: {linters_res}")
        except Exception as e:
            print(f"[linters] warning: {e}")

        # B) Потом — LLM
        review_result = llm_analyze_repo_per_file(project_data.get("username"))

        # C) Генерация HTML-отчёта пайплайном
        try:
            report_path = llm_answer_to_html_simulator(
                None,  # Первый параметр больше не используется
                username=project_data.get("username"),
                project_id=project_id,
                project_name=project_data.get("project_name"),
                uploaded_at=project_data.get("uploaded_at"),
            )
        except Exception as e:
            print(f"[review_task] ошибка генерации отчёта: {e}")
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                ("error", datetime.datetime.now(), project_id),
            )
            conn.commit(); conn.close()
            return

        # D) Обновляем БД
        conn = get_db_connection()
        c = conn.cursor()
        print(f"UPDATE review_html_path")
        c.execute(
            """UPDATE projects 
               SET status = ?, review_html_path = ?, review_completed_at = ?, updated_at = ?
               WHERE id = ?""",
            ("completed", report_path, datetime.datetime.now(), datetime.datetime.now(), project_id),
        )
        conn.commit()
        conn.close()

        print(f"Review completed for project {project_id} -> {report_path}")

    thread = threading.Thread(target=review_task)
    thread.daemon = True
    thread.start()



if __name__ == "__main__":
    if debug_local:
        app.run(debug=True, port=5000)
    else:
        app.run(debug=True, host='0.0.0.0',port='8080')
