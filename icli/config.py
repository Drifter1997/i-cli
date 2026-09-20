import os
import atexit
import shutil
from pathlib import Path

# Base configuration directory in user's home (completely independent from any browser)
CONFIG_DIR = Path(os.path.expanduser("~/.config/i-cli"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Isolated session and cookie storage
SESSION_FILE = CONFIG_DIR / "session.json"

# Download directory for explicit :d command
DOWNLOAD_DIR = Path(os.path.expanduser("~/Downloads"))
if not DOWNLOAD_DIR.exists():
    DOWNLOAD_DIR = Path(os.path.expanduser("~/repo/i-cli/downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# RAM-only media directory (uses Linux tmpfs in /dev/shm for 0 disk writes)
if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
    RAM_DIR = Path(f"/dev/shm/i-cli-{os.getuid()}")
else:
    RAM_DIR = Path(f"/tmp/i-cli-{os.getuid()}")

RAM_DIR.mkdir(parents=True, exist_ok=True)

# Cleanup RAM media directory on application exit
def cleanup_ram_dir():
    try:
        if RAM_DIR.exists():
            shutil.rmtree(RAM_DIR, ignore_errors=True)
    except Exception:
        pass

atexit.register(cleanup_ram_dir)

# External tool commands
IMV_PATH = shutil.which("imv") or "imv"
MPV_PATH = shutil.which("mpv") or "mpv"
CHAFA_PATH = shutil.which("chafa") or "chafa"

# Thumbnail defaults
THUMB_MAX_WIDTH = 28
THUMB_MAX_HEIGHT = 12
