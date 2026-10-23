#!/usr/local/bin/python3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, "/var/lib/.ts-sync")

from settings import BACKUP_ROOT, LOG_PATH

def main():
    root = Path(BACKUP_ROOT)
    snapshots = sorted(path for path in root.glob("*") if path.is_dir())
    log_path = Path(LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"{datetime.now(timezone.utc).isoformat()} snapshots={len(snapshots)}\n"
        )

if __name__ == "__main__":
    main()
