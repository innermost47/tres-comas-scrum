from datetime import datetime

def log(tag: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    colors = {
        "CEO": "\033[94m", 
        "CODER": "\033[92m", 
        "TOOL": "\033[93m", 
        "RUN": "\033[95m",  
        "DB": "\033[96m", 
        "ERR": "\033[91m",
        "WATCH": "\033[97m", 
    }
    reset = "\033[0m"
    color = colors.get(tag, "")
    print(f"[{ts}] {color}[{tag}]{reset} {msg}")