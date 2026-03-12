import os

# Create a 'logs.txt' file in the same folder as this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "system_logs.txt")


def add_log(message):
    """Appends a message to the shared log file."""
    try:
        # Open in 'append' mode to add new lines
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message)
    except Exception as e:
        print(f"❌ Logger Error: {e}")


def get_logs():
    """Reads the last 50 lines from the shared log file."""
    if not os.path.exists(LOG_FILE):
        return "System Initialized. Waiting for data...\n"

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Return only the last 50 lines to keep it fast
            return "".join(lines[-50:])
    except Exception:
        return "Error reading log file."
