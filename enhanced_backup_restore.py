"""
Step 10: Enhanced Backup and Restore System

Features:
- Automated scheduled backups
- Backup compression
- Restore functionality
- Backup listing and management
- Automatic cleanup of old backups
"""

import os
import sqlite3
import shutil
import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


DB_PATH = os.environ.get(
    "RECONCILE_DB_PATH",
    os.path.join(os.path.dirname(__file__), "reconcile.db"),
)

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
MAX_BACKUP_AGE_DAYS = int(os.environ.get("MAX_BACKUP_AGE_DAYS", "30"))
MAX_BACKUPS = int(os.environ.get("MAX_BACKUPS", "50"))


def ensure_backup_dir():
    """Ensure backup directory exists."""
    os.makedirs(BACKUP_DIR, exist_ok=True)


def create_backup(compress: bool = True) -> str:
    """
    Create a backup of the database.
    
    Args:
        compress: Whether to compress the backup with gzip
        
    Returns:
        Path to the backup file
    """
    ensure_backup_dir()
    
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    
    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"reconcile_backup_{timestamp}.db"
    if compress:
        backup_name += ".gz"
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    # Copy database
    if compress:
        with open(DB_PATH, 'rb') as f_in:
            with gzip.open(backup_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copy2(DB_PATH, backup_path)
    
    # Create metadata file
    metadata = {
        "backup_file": backup_name,
        "created_at": datetime.now().isoformat(),
        "original_db_path": DB_PATH,
        "compressed": compress,
        "db_size_bytes": os.path.getsize(DB_PATH)
    }
    
    metadata_path = backup_path.replace(".db.gz", ".meta.json").replace(".db", ".meta.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✓ Backup created: {backup_name}")
    return backup_path


def list_backups() -> List[Dict]:
    """List all available backups with metadata."""
    ensure_backup_dir()
    
    backups = []
    for file in os.listdir(BACKUP_DIR):
        if file.startswith("reconcile_backup_") and (file.endswith(".db") or file.endswith(".db.gz")):
            backup_path = os.path.join(BACKUP_DIR, file)
            metadata_path = backup_path.replace(".db.gz", ".meta.json").replace(".db", ".meta.json")
            
            backup_info = {
                "file": file,
                "path": backup_path,
                "size_bytes": os.path.getsize(backup_path),
                "created_at": datetime.fromtimestamp(os.path.getctime(backup_path)).isoformat(),
                "compressed": file.endswith(".gz")
            }
            
            # Load metadata if available
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        backup_info.update(metadata)
                except:
                    pass
            
            backups.append(backup_info)
    
    # Sort by creation time (newest first)
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def restore_backup(backup_file: str, create_backup_first: bool = True) -> bool:
    """
    Restore database from a backup.
    
    Args:
        backup_file: Name of backup file (or full path)
        create_backup_first: Whether to create a backup of current DB before restoring
        
    Returns:
        True if successful
    """
    ensure_backup_dir()
    
    # If just filename, construct full path
    if not os.path.isabs(backup_file):
        backup_path = os.path.join(BACKUP_DIR, backup_file)
    else:
        backup_path = backup_file
    
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    
    # Create backup of current database if it exists
    if create_backup_first and os.path.exists(DB_PATH):
        print("Creating backup of current database before restore...")
        create_backup()
    
    # Restore database
    print(f"Restoring from backup: {backup_file}")
    
    if backup_path.endswith(".gz"):
        # Decompress and restore
        with gzip.open(backup_path, 'rb') as f_in:
            with open(DB_PATH, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        # Direct copy
        shutil.copy2(backup_path, DB_PATH)
    
    print(f"✓ Database restored from {backup_file}")
    return True


def cleanup_old_backups():
    """Remove backups older than MAX_BACKUP_AGE_DAYS and keep only MAX_BACKUPS most recent."""
    ensure_backup_dir()
    
    backups = list_backups()
    
    # Remove old backups
    cutoff_date = datetime.now() - timedelta(days=MAX_BACKUP_AGE_DAYS)
    removed_count = 0
    
    for backup in backups:
        backup_date = datetime.fromisoformat(backup["created_at"])
        if backup_date < cutoff_date:
            try:
                os.remove(backup["path"])
                # Remove metadata file if exists
                metadata_path = backup["path"].replace(".db.gz", ".meta.json").replace(".db", ".meta.json")
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                removed_count += 1
            except Exception as e:
                print(f"Warning: Could not remove old backup {backup['file']}: {e}")
    
    # Keep only MAX_BACKUPS most recent
    backups = list_backups()
    if len(backups) > MAX_BACKUPS:
        backups_to_remove = backups[MAX_BACKUPS:]
        for backup in backups_to_remove:
            try:
                os.remove(backup["path"])
                metadata_path = backup["path"].replace(".db.gz", ".meta.json").replace(".db", ".meta.json")
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                removed_count += 1
            except Exception as e:
                print(f"Warning: Could not remove backup {backup['file']}: {e}")
    
    if removed_count > 0:
        print(f"✓ Cleaned up {removed_count} old backup(s)")
    
    return removed_count


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python enhanced_backup_restore.py backup          - Create a backup")
        print("  python enhanced_backup_restore.py list             - List all backups")
        print("  python enhanced_backup_restore.py restore <file> - Restore from backup")
        print("  python enhanced_backup_restore.py cleanup         - Clean up old backups")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "backup":
        backup_path = create_backup()
        print(f"Backup created: {backup_path}")
    
    elif command == "list":
        backups = list_backups()
        print(f"\nFound {len(backups)} backup(s):\n")
        for backup in backups:
            size_mb = backup["size_bytes"] / (1024 * 1024)
            print(f"  {backup['file']}")
            print(f"    Created: {backup['created_at']}")
            print(f"    Size: {size_mb:.2f} MB")
            print(f"    Compressed: {backup['compressed']}")
            print()
    
    elif command == "restore":
        if len(sys.argv) < 3:
            print("Error: Please specify backup file to restore")
            sys.exit(1)
        restore_backup(sys.argv[2])
    
    elif command == "cleanup":
        removed = cleanup_old_backups()
        print(f"Cleanup complete. Removed {removed} backup(s).")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)



