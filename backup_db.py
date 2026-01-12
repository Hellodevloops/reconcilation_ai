"""
Simple helper script to create timestamped backups of the SQLite database.

Usage (from project root):
    python -m python_ocr_reconcile.backup_db
or:
    cd python_ocr_reconcile
    python backup_db.py
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime

from app import DB_PATH  # Reuse the same DB path config as the main app


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"Database file not found at: {DB_PATH}")
        return

    base_dir = os.path.dirname(DB_PATH)
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = os.path.basename(DB_PATH)
    backup_name = f"{db_name.rsplit('.', 1)[0]}_{timestamp}.sqlite3"
    backup_path = os.path.join(backup_dir, backup_name)

    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")


if __name__ == "__main__":
    main()


