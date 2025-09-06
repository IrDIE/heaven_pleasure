from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import sqlite3
import datetime, time
import threading
from werkzeug.utils import secure_filename

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

    if username in users and users[username]["password"] == password:
        return jsonify(
            {
                "success": True,
                "message": "Login successful",
                "user": {"username": username, "name": users[username]["name"]},
            }
        )
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
    print(f"\n\nGOT NEW USER  {username}, {password}\n\n")

    # Validation
    if not username or not password:
        return (
            jsonify(
                {"success": False, "message": "Username and password are required"}
            ),
            400,
        )

    if username in users:
        return jsonify({"success": False, "message": "Username already exists"}), 409

    # Store new user
    users[username] = {"password": password}

    return jsonify({"success": True, "message": "Account created successfully"})


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
                "created_at": project["created_at"],
                "review_type": project["review_type"],
            }
        )

    return jsonify({"success": True, "projects": projects_list})


@app.route("/api/my_last_review", methods=["POST"])
def my_last_review():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    print(f"\n\nGOT from logit {username}, {password}\n\n")

    if username in users and users[username]["password"] == password:
        return jsonify(
            {
                "success": True,
                "message": "Login successful",
                "user": {"username": username, "name": users[username]["name"]},
            }
        )
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


def llm_simulator(data):
    # Simulate LLM processing
    time.sleep(10)  # Simulate processing delay
    return {
        "summary": f"Simulated summary for project '{data.get('project_name', 'N/A')}'",
        "issues": [
            "Issue 1: Code structure could be improved",
            "Issue 2: Missing documentation",
            "Issue 3: Potential performance bottlenecks",
        ],
        "suggestions": [
            "Suggestion A: Refactor into smaller functions",
            "Suggestion B: Add comments for complex logic",
            "Suggestion C: Consider caching for repeated operations",
        ],
    }


def llm_answer_to_html_simulator(answer):
    # Convert LLM answer to HTML format
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Project Review Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
            h2 {{ color: #333; }}
            h3 {{ color: #555; margin-top: 20px; }}
            ul {{ margin-left: 20px; }}
            li {{ margin-bottom: 8px; }}
        </style>
    </head>
    <body>
        <h2>Project Review Summary</h2>
        <p>{answer['summary']}</p>
        <h3>Identified Issues:</h3>
        <ul>
    """
    for issue in answer["issues"]:
        html_content += f"<li>{issue}</li>"

    html_content += """
        </ul>
        <h3>Suggestions:</h3>
        <ul>
    """
    for suggestion in answer["suggestions"]:
        html_content += f"<li>{suggestion}</li>"

    html_content += """
        </ul>
    </body>
    </html>
    """
    return html_content


def process_review_async(project_id, project_data):
    """Process review asynchronously in a separate thread"""

    def review_task():
        # Simulate LLM processing
        review_result = llm_simulator(project_data)

        # Convert to HTML
        html_content = llm_answer_to_html_simulator(review_result)

        # Save HTML report
        reports_dir = "review_reports"
        os.makedirs(reports_dir, exist_ok=True)
        report_filename = f"review_{project_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = os.path.join(reports_dir, report_filename)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Update database with review results
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """UPDATE projects 
                     SET status = ?, review_html_path = ?, review_completed_at = ?, updated_at = ?
                     WHERE id = ?""",
            (
                "completed",
                report_path,
                datetime.datetime.now(),
                datetime.datetime.now(),
                project_id,
            ),
        )
        conn.commit()
        conn.close()

        print(f"Review completed for project {project_id}")

    # Start the review process in a separate thread
    thread = threading.Thread(target=review_task)
    thread.daemon = True
    thread.start()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
