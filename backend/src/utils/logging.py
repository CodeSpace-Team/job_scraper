from datetime import datetime

def log(msg: str):
    """Simple logging with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")