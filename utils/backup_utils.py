import os
import shutil
from datetime import datetime

BACKUPS_DIR = "backups"
DB_PATH = "database/database.db"


def _ensure_backups_dir():
    """Create the backups directory if it doesn't exist."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def create_backup():
    """
    Copy the live database to a timestamped file in the backups directory.

    Returns:
        dict: {'status': 'success', 'filename': '...', 'size_kb': N}
              or {'status': 'error', 'message': '...'}
    """
    try:
        _ensure_backups_dir()

        if not os.path.exists(DB_PATH):
            return {'status': 'error', 'message': 'Database file not found'}

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(BACKUPS_DIR, backup_filename)

        shutil.copy2(DB_PATH, backup_path)

        return {
            'status': 'success',
            'filename': backup_filename,
            'size_kb': os.path.getsize(backup_path) // 1024
        }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def list_backups():
    """
    Return all backup files, newest first.

    Returns:
        list: Dicts with 'filename', 'created_at', 'size_kb'
    """
    try:
        _ensure_backups_dir()

        files = [
            f for f in os.listdir(BACKUPS_DIR)
            if f.startswith('backup_') and f.endswith('.db')
        ]

        backups = []
        for filename in files:
            path = os.path.join(BACKUPS_DIR, filename)
            stat = os.stat(path)
            backups.append({
                'filename': filename,
                'created_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'size_kb': stat.st_size // 1024
            })

        backups.sort(key=lambda x: x['filename'], reverse=True)
        return backups

    except Exception:
        return []


def restore_backup(backup_filename):
    """
    Overwrite the live database with a selected backup file.

    Args:
        backup_filename (str): Basename of the backup file — no path traversal allowed

    Returns:
        dict: {'status': 'success', 'message': '...'} or {'status': 'error', 'message': '...'}
    """
    try:
        # Sanitize — strip any path components, only allow our own backup filenames
        backup_filename = os.path.basename(backup_filename)

        if not (backup_filename.startswith('backup_') and backup_filename.endswith('.db')):
            return {'status': 'error', 'message': 'Invalid backup filename'}

        backup_path = os.path.join(BACKUPS_DIR, backup_filename)

        if not os.path.exists(backup_path):
            return {'status': 'error', 'message': 'Backup file not found'}

        shutil.copy2(backup_path, DB_PATH)
        return {'status': 'success', 'message': f'Restored from {backup_filename}'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def get_db_stats():
    """
    Return basic stats about the live database file and backup directory.

    Returns:
        dict: size_kb, last_modified, backup_count, latest_backup
    """
    try:
        if os.path.exists(DB_PATH):
            stat = os.stat(DB_PATH)
            size_kb = stat.st_size // 1024
            last_modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        else:
            size_kb = 0
            last_modified = 'N/A'

        _ensure_backups_dir()
        backup_files = [
            f for f in os.listdir(BACKUPS_DIR)
            if f.startswith('backup_') and f.endswith('.db')
        ]
        latest = max(backup_files) if backup_files else 'None'

        return {
            'size_kb': size_kb,
            'last_modified': last_modified,
            'backup_count': len(backup_files),
            'latest_backup': latest
        }

    except Exception:
        return {'size_kb': 0, 'last_modified': 'N/A', 'backup_count': 0, 'latest_backup': 'None'}
