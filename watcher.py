import os
import sys
import time
import subprocess
from datetime import datetime
from config import MAIN_SCRIPT, RESTART_FLAG, CHECK_INTERVAL


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] \033[97m[WATCH]\033[0m {msg}")

def start_main():
    req_file = "output/requirements.txt"
    if os.path.exists(req_file):
        log("📦 pip install -r output/requirements.txt")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file], check=False
        )
    return subprocess.Popen([sys.executable, MAIN_SCRIPT], ...)

def main():
    log("👁️  Watcher started")
    if os.path.exists(RESTART_FLAG):
        os.remove(RESTART_FLAG)
    process = start_main()
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            if process.poll() is not None:
                returncode = process.returncode
                if returncode == 0:
                    log("✅ main.py completed cleanly (code 0)")
                else:
                    log(
                        f"💀 main.py crashed (code {returncode}), restarting in 3s..."
                    )
                    time.sleep(3)
                    process = start_main()
                continue
            if os.path.exists(RESTART_FLAG):
                log("🔄 restart.flag detected! Restarting...")
                os.remove(RESTART_FLAG)
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                log("🔁 Relaunching main.py with new codebase")
                time.sleep(1)
                process = start_main()
    except KeyboardInterrupt:
        log("⛔ Stop requested (Ctrl+C)")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        log("👋 Watcher stopped")

if __name__ == "__main__":
    main()