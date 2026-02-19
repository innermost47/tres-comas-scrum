import os
import re
import json
from typing import Optional
from tools import tool_write_file, tool_exec_code
from config import STDLIB_IMPORTS
from logger import log

def sort_by_dependencies(filepaths):
    import re
    deps = {}
    for fpath in filepaths:
        deps[fpath] = set()
        try:
            with open(fpath) as fp:
                content = fp.read()
            for match in re.findall(r'from \.([\w]+) import|from framework\.([\w]+) import|from src\.([\w]+) import', content):
                dep_name = match[0] or match[1]
                for other in filepaths:
                    if os.path.basename(other) == f"{dep_name}.py":
                        deps[fpath].add(other)
        except Exception:
            pass
    ordered = []
    visited = set()
    def visit(path):
        if path in visited:
            return
        visited.add(path)
        for dep in deps.get(path, []):
            visit(dep)
        ordered.append(path)
    for path in filepaths:
        visit(path)
    return ordered


def fix_empty_blocks(code: str) -> str:
    lines = code.splitlines()
    result = []
    for i, line in enumerate(lines):
        result.append(line)
        if line.rstrip().endswith(':'):
            next_code = None
            for j in range(i+1, len(lines)):
                if lines[j].strip():
                    next_code = lines[j]
                    break
            if next_code is None or len(next_code) - len(next_code.lstrip()) <= len(line) - len(line.lstrip()):
                indent = len(line) - len(line.lstrip()) + 4
                result.append(' ' * indent + 'pass')
    return '\n'.join(result)


def apply_delivery(delivery: dict) -> bool:
    try:
        for file_info in delivery.get("files", []):
            tool_write_file(file_info["path"], file_info["content"])
        return True
    except Exception as e:
        log("ERR", f"apply_delivery: {e}")
        return False


def run_delivery_tests(delivery: dict) -> dict:
    test_files = [f for f in delivery.get("files", []) if "test" in f["path"] and f["path"].endswith(".py")]
    source_files = [f for f in delivery.get("files", []) if "test" not in f["path"] and f["path"].endswith(".py")]

    if not test_files:
        return {"success": False, "stdout": "", "stderr": "No test file delivered — you must always include unit tests."}
    
    all_imports = []
    for f in test_files:
        lines = f["content"].splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                full_line = stripped
                while full_line.endswith("\\") and i + 1 < len(lines):
                    i += 1
                    full_line = full_line[:-1] + lines[i].strip()
                if "framework" in full_line or "src" in full_line or full_line.startswith("from ."):
                    i += 1
                    continue
                if any(x in full_line for x in STDLIB_IMPORTS):
                    if full_line not in all_imports:
                        all_imports.append(full_line)
            i += 1

    combined = "# AUTO-GENERATED TEST RUNNER\n\n"
    combined += "import pytest\n"
    combined += "\n".join(all_imports) + "\n\n"

    delivery_paths = {f["path"] for f in source_files}
    if os.path.exists("output/framework"):
            all_existing = []
            for root, _, files in os.walk("output/framework"):
                for fname in files:
                    if fname.endswith(".py"):
                        all_existing.append(os.path.join(root, fname))
            
            for fpath in sort_by_dependencies(all_existing):
                rel = fpath.replace("output/", "")
                if rel in delivery_paths:
                    continue
                try:
                    with open(fpath) as fp:
                        existing = fp.read()
                    lines = [l for l in existing.splitlines()
                            if not l.strip().startswith("from .")
                            and not l.strip().startswith("from framework")
                            and not (l.strip().startswith("import ") and not any(x in l for x in STDLIB_IMPORTS))]
                    combined += f"# === EXISTING: {rel} ===\n" + "\n".join(lines) + "\n\n"
                except Exception:
                    pass

    for f in source_files:
        lines = []
        i = 0
        content_lines = f["content"].splitlines()
        while i < len(content_lines):
            line = content_lines[i]
            stripped = line.strip()
            if stripped.startswith("from .") or stripped.startswith("from framework"):
                i += 1
                continue
            while stripped.endswith("\\") and i + 1 < len(content_lines):
                i += 1
                stripped = stripped[:-1].strip() + " " + content_lines[i].strip()
                line = stripped
            lines.append(line)
            i += 1
        combined += f"# === SOURCE: {f['path']} ===\n" + "\n".join(lines) + "\n\n"

    for f in test_files:
        lines = []
        for line in f["content"].splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                continue
            lines.append(line)
        combined += f"# === TEST: {f['path']} ===\n" + "\n".join(lines) + "\n\n"

    combined += "\npytest.main(['-x', '-q', '--tb=short', '--no-header', '-p', 'no:cacheprovider', __file__])\n"

    requirements = delivery.get("requirements", [])
    requirements = [r.strip() for r in requirements if r.strip()]

    for forced in ["pytest", "requests", "pydantic", "pyyaml"]:
        if forced not in requirements:
            requirements.append(forced)

    return tool_exec_code(combined, requirements)

def extract_key_error(stderr: str) -> str:
    lines = stderr.splitlines()
    key_lines = []
    for line in lines:
        if any(x in line for x in ["PydanticDeprecated", "DeprecatedSince", "deprecated", "warning"]):
            continue
        if any(x in line for x in ["Error", "Exception", "ModuleNotFound", "NameError", "SyntaxError", "IndentationError", "Traceback", "line "]):
            key_lines.append(line)
    return "\n".join(key_lines[-10:]) if key_lines else stderr[-500:]


def extract_json(text: str) -> Optional[dict]:
    text = "".join(c for c in text if ord(c) >= 32 or c in "\n\r\t")
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i, c in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if c == "\\" and in_string:
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        return None

    candidate = text[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(candidate.encode("utf-8", errors="replace").decode("utf-8"))
    except json.JSONDecodeError as e:
        log("ERR", f"JSON parse error final: {e}")
        return None


def extract_delivery(text: str) -> Optional[dict]:
    try:
        delivery_match = re.search(r"<delivery>(.*?)</delivery>", text, re.DOTALL)
        if not delivery_match:
            return None

        content = delivery_match.group(1)

        ticket_id = re.search(r"<ticket_id>(.*?)</ticket_id>", content)
        requirements = re.search(r"<requirements>(.*?)</requirements>", content)
        files = re.findall(r'<file path="([^"]+)">(.*?)</file>', content, re.DOTALL)

        cleaned_files = []
        for path, file_content in files:
            file_content = re.sub(r'```\w*', '', file_content)
            file_content = file_content.strip()
            cleaned_files.append({"path": path.strip(), "content": file_content.strip()})


        return {
            "type": "code_delivery",
            "ticket_id": ticket_id.group(1).strip() if ticket_id else "",
            "requirements": (
                [r.strip() for r in requirements.group(1).split(",")]
                if requirements
                else []
            ),
            "files": cleaned_files,
        }
    except Exception as e:
        log("ERR", f"extract_delivery error: {e}")
        return None