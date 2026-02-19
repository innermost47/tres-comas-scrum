import os
import re
import subprocess
import tempfile
import requests
from logger import log


def tool_web_search(query: str) -> str:
    log("TOOL", f"🔍 web_search: {query}")
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                results.append(r["Text"])
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"web_search error: {e}"


def tool_fetch_url(url: str) -> str:
    log("TOOL", f"🌐 fetch_url: {url}")
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]
    except Exception as e:
        return f"fetch_url error: {e}"


def tool_exec_code(code: str, requirements: list[str] = None) -> dict:
    log("RUN", f"⚙️  Sandbox execution (bwrap)")
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_dir = os.path.join(tmpdir, "venv")
        code_file = os.path.join(tmpdir, "test_runner.py")
        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir)

        subprocess.run(["python3", "-m", "venv", venv_dir], capture_output=True)
        pip = os.path.join(venv_dir, "bin", "pip")

        if requirements:
            for req in requirements:
                log("RUN", f"📦 pip install {req}")
                subprocess.run([pip, "install", req], capture_output=True, timeout=60)

        with open(code_file, "w") as f:
            f.write(code)

        python_bin = os.path.join(venv_dir, "bin", "python3")

        cmd = [
            "bwrap",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--ro-bind",
            "/etc/resolv.conf",
            "/etc/resolv.conf", 
            "--bind",
            tmpdir,
            tmpdir,  
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--unshare-pid",
            "--die-with-parent",
            python_bin,
            code_file,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=tmpdir
            )
            success = result.returncode in (0, )
            log("RUN", f"{'✅' if success else '❌'} returncode={result.returncode}")
            if not success:
                log("ERR", f"stderr: {result.stderr}")
            return {
                "success": success,
                "stdout": result.stdout[:3000],
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Timeout (30s exceeded)"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}


def tool_read_file(path: str) -> str:
    path = path.lstrip("/")
    if path.startswith("output/"):
        path = path[len("output/"):]
    safe_path = os.path.join("output", path)
    log("TOOL", f"📖 read_file: {safe_path}")
    try:
        with open(safe_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def tool_write_file(path: str, content: str) -> str:
    safe_path = os.path.join("output", path.lstrip("/"))
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    log("TOOL", f"✍️  write_file: {safe_path}")
    try:
        with open(safe_path, "w") as f:
            f.write(content)
        return f"File written: {safe_path}"
    except Exception as e:
        return f"Error: {e}"


def tool_list_files() -> str:
    log("TOOL", "📁 list_files")
    result = []
    for root, dirs, files in os.walk("output"):
        for fname in files:
            result.append(os.path.join(root, fname))
    return "\n".join(result) if result else "No files."


TOOLS_DISPATCH = {
    "web_search": lambda args: tool_web_search(args["query"]),
    "fetch_url": lambda args: tool_fetch_url(args["url"]),
    "exec_code": lambda args: tool_exec_code(
        args["code"], args.get("requirements", [])
    ),
    "read_file": lambda args: tool_read_file(args["path"]),
    "write_file": lambda args: tool_write_file(args["path"], args["content"]),
    "list_files": lambda args: tool_list_files(),
}


def dispatch_tool(name: str, args: dict):
    fn = TOOLS_DISPATCH.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    return fn(args)