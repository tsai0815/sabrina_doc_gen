import datetime

def log_message(msg):
    """Print a timestamped log message."""
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{time}] {msg}")
