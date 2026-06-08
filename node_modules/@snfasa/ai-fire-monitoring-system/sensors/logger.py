import os
from collections import deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "system_logs.txt")


def add_log(message):
    """Appends a message safely."""
    try:
        # Using a context manager ensures the file is closed immediately
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            # Always ensure a newline so logs don't merge into one line
            f.write(f"{message}\n")
    except Exception as e:
        print(f"❌ Logger Error: {e}")


def get_logs():
    """Reads the last 50 lines efficiently."""
    if not os.path.exists(LOG_FILE):
        return "System Initialized. Waiting for data...\n"

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # Deque is highly optimized for 'tail' operations
            last_lines = deque(f, maxlen=50)
            return "".join(last_lines)
    except Exception:
        return "Error reading log file."
