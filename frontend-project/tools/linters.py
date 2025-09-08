#!/usr/bin/env python3
"""Code analyzer: clones (or copies) a repo into a per-user timestamped tmp folder,
runs linters (flake8, cppcheck, eslint, htmlhint, stylelint, checkstyle) when available,
collects and normalizes results into a single JSON file saved to the same tmp folder.

Usage:
  python analyze_repo.py --repo <repo_url_or_local_path> [--keep]

If --repo is omitted, the current working directory is analyzed (copied into tmp session folder).
Set --keep to preserve tmp folder for debugging / CI artifact upload.
"""

from __future__ import annotations
import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple, List, Dict, Any

try:
    import git
except Exception:
    git = None

# Optional IPython display for notebooks (not required)
try:
    from IPython.display import display, JSON as IPYJSON
except Exception:
    display = None
    IPYJSON = None

CHECKSTYLE_JAR_PATH = os.path.abspath("checkstyle-all.jar")

# ------------------------- utilities -------------------------

def is_tool_available(tool_name: str) -> bool:
    """Check if a command-line tool is available in PATH."""
    from shutil import which
    return which(tool_name) is not None


def _run_subprocess_capture(cmd: List[str], timeout: int = 300, cwd: str | None = None) -> Tuple[str, int]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        out = proc.stdout.strip()
        if not out:
            out = proc.stderr.strip()
        return out, proc.returncode
    except subprocess.TimeoutExpired:
        return "", 124


# ------------------------- detectors / parsers -------------------------

def detect_language(file_path: str) -> str | None:
    ext = os.path.splitext(file_path)[1].lower()
    language_map = {
        '.cpp': 'cpp', '.cxx': 'cpp', '.cc': 'cpp', '.c': 'cpp',
        '.hpp': 'cpp', '.h': 'cpp',
        '.py': 'python', '.pyw': 'python',
        '.html': 'html', '.htm': 'html', '.xhtml': 'html',
        '.java': 'java',
        '.js': 'javascript', '.jsx': 'javascript',
        '.ts': 'typescript', '.tsx': 'typescript',
        '.css': 'css', '.scss': 'css', '.sass': 'css'
    }
    if ext in language_map:
        return language_map[ext]

    try:
        with open(file_path, 'r', errors='ignore', encoding='utf-8') as f:
            head = f.read(4096)
            if 'public class ' in head or 'package ' in head:
                return 'java'
            if 'function ' in head or 'console.log' in head or '=> ' in head or 'import ' in head:
                return 'javascript'
            if '<!DOCTYPE html' in head or '<html' in head or '<head' in head or '<body' in head:
                return 'html'
            if 'def ' in head and ('import ' in head or 'from ' in head):
                return 'python'
            if '#include' in head and ('<iostream>' in head or '<vector>' in head):
                return 'cpp'
    except Exception:
        pass
    return None


# ------------------------- cppcheck -------------------------

def run_cppcheck(files: List[str], output_path: str, cwd: str | None = None) -> str:
    if not files:
        return ""
    try:
        cmd = ['cppcheck', '--enable=all', '--language=c++', '--xml', '--xml-version=2'] + files
        xml_out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_out)
        if not xml_out:
            print("cppcheck returned no output. returncode=", rc)
        return xml_out
    except Exception as e:
        print("Error running cppcheck:", e)
        return ""


def parse_cppcheck_results(xml_content: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not xml_content:
        return errors
    try:
        root = ET.fromstring(xml_content)
        for error_elem in root.findall('.//error'):
            file_path = error_elem.get('file')
            line = error_elem.get('line')
            column = error_elem.get('column')
            if not file_path:
                loc = error_elem.find('location')
                if loc is not None:
                    file_path = loc.get('file')
                    line = loc.get('line')
                    column = loc.get('column')
            if not file_path:
                continue
            errors.append({
                "file": os.path.relpath(file_path, repo_path),
                "line": line,
                "column": column,
                "message": error_elem.get('msg') or (error_elem.text or "").strip(),
                "severity": error_elem.get('severity'),
                "tool": "cppcheck"
            })
    except ET.ParseError as e:
        print("Error parsing cppcheck output:", e, "preview:\n", xml_content[:2000])
    return errors


# ------------------------- flake8 -------------------------

def parse_flake8_text(text_output: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not text_output:
        return errors
    for line in text_output.splitlines():
        # Expected: filename:line:col: CODE message
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        fname, line_no, col_no, rest = parts
        rest = rest.strip()
        if " " in rest:
            code, msg = rest.split(" ", 1)
        else:
            code, msg = rest, ""
        errors.append({
            "file": os.path.relpath(fname, repo_path),
            "line": int(line_no) if line_no.isdigit() else line_no,
            "column": int(col_no) if col_no.isdigit() else col_no,
            "message": msg,
            "code": code,
            "tool": "flake8"
        })
    return errors


def run_flake8(files: List[str], output_path: str, cwd: str | None = None) -> str:
    if not files:
        return "[]"
    try:
        # First try to get JSON output (requires flake8-json or similar plugin)
        cmd = [sys.executable, "-m", "flake8", "--format=json", "--max-line-length=120"] + files
        out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(out)

        # If output is valid JSON, return it
        try:
            json.loads(out)
            return out
        except Exception:
            # fallback to plain text parsing
            print("flake8 didn't return JSON, falling back to text parser")
            cmd = [sys.executable, "-m", "flake8", "--max-line-length=120"] + files
            out2, rc2 = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(out2)
            return out2

    except Exception as e:
        print("Error running flake8:", e)
        return "[]"


def parse_flake8_results(json_or_text: str, repo_path: str) -> List[Dict[str, Any]]:
    # Try JSON first
    if not json_or_text:
        return []
    try:
        data = json.loads(json_or_text)
        errors: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            for filename, file_errs in data.items():
                for e in file_errs:
                    errors.append({
                        "file": os.path.relpath(filename, repo_path),
                        "line": e.get("line_number") or e.get("line"),
                        "column": e.get("column_number") or e.get("column"),
                        "message": e.get("text") or "",
                        "code": e.get("code"),
                        "tool": "flake8"
                    })
        elif isinstance(data, list):
            for e in data:
                fname = e.get("filename") or e.get("path")
                errors.append({
                    "file": os.path.relpath(fname, repo_path) if fname else None,
                    "line": e.get("line_number") or e.get("line"),
                    "column": e.get("column_number") or e.get("column"),
                    "message": e.get("text") or "",
                    "code": e.get("code"),
                    "tool": "flake8"
                })
        else:
            # unexpected format
            return []
        return errors
    except Exception:
        # fallback to text parser
        return parse_flake8_text(json_or_text, repo_path)


# ------------------------- htmlhint -------------------------

def run_htmlhint(files: List[str], output_path: str, config_path: str, cwd: str | None = None) -> str:
    if not files:
        return "[]"
    try:
        cmd = ['htmlhint', '--config', config_path, '--format', 'json'] + files
        out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(out)
        if not out:
            print("htmlhint returned no output. returncode=", rc)
            return ""
        return out
    except Exception as e:
        print("Error running htmlhint:", e)
        return ""


def parse_htmlhint_results(json_content: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not json_content:
        return errors
    try:
        data = json.loads(json_content)
        if isinstance(data, list):
            for file_errors in data:
                rel_path = os.path.relpath(file_errors.get("file", ""), repo_path)
                for err in file_errors.get("errors", []):
                    errors.append({
                        "file": rel_path,
                        "line": err.get("line"),
                        "column": err.get("col"),
                        "message": err.get("message"),
                        "rule": err.get("rule"),
                        "tool": "htmlhint"
                    })
    except Exception as e:
        print("Error parsing htmlhint:", e)
    return errors


# ------------------------- checkstyle (Java) -------------------------

def run_checkstyle(files: List[str], output_path: str, config_path: str, checkstyle_jar_path: str = CHECKSTYLE_JAR_PATH, cwd: str | None = None) -> str:
    if not files:
        return ""
    if not os.path.exists(checkstyle_jar_path):
        print(f"Checkstyle jar not found at {checkstyle_jar_path}. Skipping Java checks.")
        return ""
    try:
        cmd = ['java', '-jar', checkstyle_jar_path, '-c', config_path, '-f', 'xml'] + files
        out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(out)
        return out
    except Exception as e:
        print("Error running checkstyle:", e)
        return ""


def parse_checkstyle_results(xml_content: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not xml_content:
        return errors
    try:
        root = ET.fromstring(xml_content)
        for file_elem in root.findall('.//file'):
            file_name = file_elem.get('name')
            rel = os.path.relpath(file_name, repo_path) if file_name else None
            for error_elem in file_elem.findall('.//error'):
                errors.append({
                    "file": rel,
                    "line": error_elem.get('line'),
                    "column": error_elem.get('column'),
                    "message": error_elem.get('message'),
                    "severity": error_elem.get('severity'),
                    "source": error_elem.get('source'),
                    "tool": "checkstyle"
                })
    except Exception as e:
        print("Error parsing checkstyle:", e)
    return errors


# ------------------------- eslint -------------------------

def run_eslint(files: List[str], output_path: str, repo_path: str, config_filename: str) -> str:
    if not files:
        return "[]"
    try:
        rel_files = [os.path.relpath(f, repo_path) for f in files]
        cmd = ['eslint', '-c', config_filename, '-f', 'json'] + rel_files
        out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=repo_path)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(out)
        if not out:
            print("eslint returned no output. returncode=", rc)
            return ""
        if not out.lstrip().startswith('['):
            print("eslint returned non-JSON output; preview:\n", out[:2000])
            return ""
        return out
    except Exception as e:
        print("Error running eslint:", e)
        return ""


def parse_eslint_results(json_content: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not json_content:
        return errors
    try:
        data = json.loads(json_content)
        for file_report in data:
            fname = file_report.get('filePath') or file_report.get('file') or file_report.get('fileName')
            rel = os.path.relpath(fname, repo_path) if fname else None
            for msg in file_report.get('messages', []):
                errors.append({
                    "file": rel,
                    "line": msg.get('line'),
                    "column": msg.get('column'),
                    "message": msg.get('message'),
                    "ruleId": msg.get('ruleId'),
                    "severity": msg.get('severity'),
                    "tool": "eslint"
                })
    except Exception as e:
        print("Error parsing eslint:", e)
    return errors


# ------------------------- stylelint -------------------------

def run_stylelint(files: List[str], output_path: str, config_path: str, cwd: str | None = None) -> str:
    if not files:
        return "[]"
    try:
        cmd = ['stylelint', '--config', config_path, '--formatter', 'json'] + files
        out, rc = _run_subprocess_capture(cmd, timeout=300, cwd=cwd)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(out)
        if not out:
            print("stylelint returned no output. returncode=", rc)
            return "[]"
        return out
    except Exception as e:
        print("Error running stylelint:", e)
        return "[]"


def parse_stylelint_results(json_content: str, repo_path: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if not json_content:
        return errors
    try:
        data = json.loads(json_content)
        for file_report in data:
            file_path = file_report.get('source')
            for warning in file_report.get('warnings', []):
                errors.append({
                    "file": os.path.relpath(file_path, repo_path) if file_path else None,
                    "line": warning.get('line'),
                    "column": warning.get('column'),
                    "message": warning.get('text'),
                    "rule": warning.get('rule'),
                    "severity": warning.get('severity'),
                    "tool": "stylelint"
                })
    except Exception as e:
        print("Error parsing stylelint:", e)
    return errors


# ------------------------- main analyzer -------------------------

def analyze_repository(repo: str, keep: bool = False, verbose: bool = True) -> Tuple[List[Dict[str, Any]], str]:
    """Clone or copy the repository into a per-user timestamped tmp folder,
    run linters available in the environment, save individual linter outputs
    and a unified code_analysis_results.json in that folder.

    Returns (all_errors, result_path).
    """
    user = os.getenv('USER') or os.getenv('USERNAME') or 'unknown_user'
    timestamp = int(time.time())
    tmp_base = os.path.join(tempfile.gettempdir(), f"{user}_{timestamp}")
    repo_path = os.path.join(tmp_base, 'repo')
    os.makedirs(tmp_base, exist_ok=True)

    # Clone or copy
    if os.path.isdir(repo):
        if verbose:
            print(f"Copying local repo {repo} -> {repo_path} ...")
        shutil.copytree(repo, repo_path)
    else:
        if git is None:
            raise RuntimeError("GitPython is required for cloning remote repositories. Install GitPython or pass a local path.")
        if verbose:
            print(f"Cloning {repo} -> {repo_path} ...")
        git.Repo.clone_from(repo, repo_path)

    # exclude dirs
    exclude_dirs = ['.git', '.github', '.vscode', '__pycache__', 'node_modules', 'venv', 'env', 'dist', 'build']

    files_by_language = {
        'cpp': [], 'python': [], 'html': [], 'java': [],
        'javascript': [], 'typescript': [], 'css': []
    }

    if verbose:
        print("Scanning repository files...")
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        for fname in files:
            if fname.startswith('.'):
                continue
            fpath = os.path.join(root, fname)
            lang = detect_language(fpath)
            if lang and lang in files_by_language:
                files_by_language[lang].append(fpath)

    if verbose:
        for lang, fl in files_by_language.items():
            if fl:
                print(f"Found {len(fl)} files ({lang}), sample:")
                for file_path in fl[:3]:
                    print("  -", os.path.relpath(file_path, repo_path))

    # write small configs into tmp_base
    checkstyle_config = """<?xml version="1.0"?>\n<!DOCTYPE module PUBLIC\n  "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"\n  "https://checkstyle.org/dtds/configuration_1_3.dtd">\n<module name="Checker">\n    <module name="TreeWalker">\n        <module name="AvoidStarImport"/>\n        <module name="ConstantName"/>\n        <module name="EmptyBlock"/>\n        <module name="EmptyStatement"/>\n        <module name="EqualsHashCode"/>\n        <module name="IllegalImport"/>\n        <module name="InnerAssignment"/>\n        <module name="MagicNumber"/>\n        <module name="MethodLength">\n            <property name="max" value="50"/>\n        </module>\n        <module name="MissingOverride"/>\n        <module name="ModifierOrder"/>\n        <module name="MultipleVariableDeclarations"/>\n        <module name="NeedBraces"/>\n        <module name="OneStatementPerLine"/>\n        <module name="OneTopLevelClass"/>\n        <module name="OperatorWrap"/>\n        <module name="OuterTypeFilename"/>\n        <module name="ParameterAssignment"/>\n        <module name="RedundantImport"/>\n        <module name="RedundantModifier"/>\n        <module name="SimplifyBooleanExpression"/>\n        <module name="SimplifyBooleanReturn"/>\n        <module name="StringLiteralEquality"/>\n        <module name="UnusedImports"/>\n        <module name="VisibilityModifier"/>\n    </module>\n</module>\n"""

    eslint_config = """module.exports = {\n  env: {\n    browser: true,\n    node: true,\n    es2021: true\n  },\n  extends: "eslint:recommended",\n  parserOptions: {\n    ecmaVersion: 12,\n    sourceType: "module"\n  },\n  rules: {\n    "no-unused-vars": "error",\n    "no-console": "error",\n    "no-alert": "error",\n    "no-eval": "error",\n    "no-undef": "error",\n    "no-unreachable": "error",\n    "no-duplicate-case": "error",\n    "no-empty": "error",\n    "no-extra-semi": "error",\n    "no-invalid-regexp": "error",\n    "no-irregular-whitespace": "error",\n    "no-sparse-arrays": "error",\n    "no-unexpected-multiline": "error",\n    "valid-typeof": "error",\n    "prefer-const": "error",\n    "no-var": "error"\n  },\n  ignorePatterns: ["**/.*"]\n};"""

    htmlhint_config = """{\n  "tagname-lowercase": true,\n  "attr-lowercase": true,\n  "attr-value-double-quotes": true,\n  "doctype-first": true,\n  "tag-pair": true,\n  "spec-char-escape": true,\n  "id-unique": true,\n  "src-not-empty": true,\n  "attr-no-duplication": true,\n  "title-require": true,\n  "alt-require": true,\n  "space-tab-mixed-disabled": "space",\n  "id-class-value": "dash",\n  "attr-no-unnecessary-whitespace": true,\n  "head-script-disabled": true,\n  "style-disabled": true,\n  "inline-style-disabled": true,\n  "inline-script-disabled": true\n}\n"""

    stylelint_config = """{\n  "extends": "stylelint-config-standard",\n  "rules": {\n    "length-zero-no-unit": true,\n    "selector-max-id": 0,\n    "selector-class-pattern": "^[a-z][a-zA-Z0-9]+$",\n    "alpha-value-notation": "percentage",\n    "color-function-notation": "modern",\n    "color-hex-length": "short",\n    "value-keyword-case": "lower"\n  }\n}\n"""

    # write configs
    config_path = os.path.join(tmp_base, "checkstyle.xml")
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(checkstyle_config)
    stylelint_config_path = os.path.join(tmp_base, "stylelint-config.json")
    with open(stylelint_config_path, 'w', encoding='utf-8') as f:
        f.write(stylelint_config)
    htmlhint_config_path = os.path.join(tmp_base, "htmlhint-config.json")
    with open(htmlhint_config_path, 'w', encoding='utf-8') as f:
        f.write(htmlhint_config)

    all_errors: List[Dict[str, Any]] = []

    # cpp
    if files_by_language['cpp']:
        if is_tool_available("cppcheck"):
            if verbose: print("Running cppcheck...")
            cpp_xml = run_cppcheck(files_by_language['cpp'], os.path.join(tmp_base, "cppcheck.xml"), cwd=repo_path)
            all_errors += parse_cppcheck_results(cpp_xml, repo_path)
        else:
            if verbose: print("WARN: cppcheck not installed, skipping C++ checks")

    # python
    if files_by_language['python']:
        if is_tool_available("flake8"):
            if verbose: print("Running flake8...")
            flake_out = run_flake8(files_by_language['python'], os.path.join(tmp_base, "flake8.json"), cwd=repo_path)
            all_errors += parse_flake8_results(flake_out, repo_path)
        else:
            if verbose: print("WARN: flake8 not installed, skipping Python checks")

    # html
    if files_by_language['html']:
        if is_tool_available("htmlhint"):
            if verbose: print("Running htmlhint...")
            html_out = run_htmlhint(files_by_language['html'], os.path.join(tmp_base, "htmlhint.json"), htmlhint_config_path, cwd=repo_path)
            all_errors += parse_htmlhint_results(html_out, repo_path)
        else:
            if verbose: print("WARN: htmlhint not installed, skipping HTML checks")

    # java
    if files_by_language['java']:
        if is_tool_available("java"):
            if verbose: print("Running checkstyle...")
            check_xml = run_checkstyle(files_by_language['java'], os.path.join(tmp_base, "checkstyle.out.xml"), config_path, checkstyle_jar_path=CHECKSTYLE_JAR_PATH, cwd=repo_path)
            all_errors += parse_checkstyle_results(check_xml, repo_path)
        else:
            if verbose: print("WARN: java not installed, skipping Java checks")

    # css
    if files_by_language['css']:
        if is_tool_available("stylelint"):
            if verbose: print("Running stylelint...")
            stylelint_out = run_stylelint(files_by_language['css'], os.path.join(tmp_base, "stylelint.json"), stylelint_config_path, cwd=repo_path)
            all_errors += parse_stylelint_results(stylelint_out, repo_path)
        else:
            if verbose: print("WARN: stylelint not installed, skipping CSS checks")

    # js/ts -> eslint
    js_files = files_by_language['javascript'] + files_by_language['typescript']
    if js_files:
        if is_tool_available("eslint"):
            if verbose:
                print("Preparing .eslintrc.cjs in the repo root...")
            eslint_config_path = os.path.join(repo_path, ".eslintrc.cjs")
            with open(eslint_config_path, 'w', encoding='utf-8') as f:
                f.write(eslint_config)
            if verbose: print("Running eslint...")
            eslint_out = run_eslint(js_files, os.path.join(tmp_base, "eslint.json"), repo_path, ".eslintrc.cjs")
            all_errors += parse_eslint_results(eslint_out, repo_path)
        else:
            if verbose: print("WARN: eslint not installed, skipping JS/TS checks")

    # write unified result
    result_path = os.path.join(tmp_base, "code_analysis_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_errors, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"Results saved to {result_path}")

    # cleanup
    if not keep:
        # keep the result file path for return but remove the rest
        try:
            # move result to a safe temp path while cleaning
            final_result_path = result_path
            # no special move; we'll delete entire tmp_base if desired
            shutil.rmtree(repo_path, ignore_errors=True)
            # if you want to remove whole tmp_base uncomment the next line
            # shutil.rmtree(tmp_base, ignore_errors=True)
        except Exception as e:
            if verbose: print("Warning during cleanup:", e)

    return all_errors, result_path


# ------------------------- CLI -------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run code analyzer on a repository or local folder")
    parser.add_argument("--repo", help="Git repo URL or local path to analyze (if omitted, analyze cwd)", default=None)
    parser.add_argument("--keep", action="store_true", help="Keep tmp folder (do not cleanup) - useful for debugging / CI artifact upload")
    parser.add_argument("--quiet", action="store_true", help="Quiet mode")
    args = parser.parse_args()

    target = args.repo or os.getcwd()
    results, out_path = analyze_repository(target, keep=args.keep, verbose=not args.quiet)

    print(f"\nTotal issues found: {len(results)}")
    if results and display and IPYJSON:
        display(IPYJSON(results))
    else:
        # print small preview
        import pprint
        pprint.pprint(results[:200])

    print(f"Results JSON: {out_path}")