"""
Step 12: OCR Results Caching System

Features:
- Cache OCR results to avoid re-processing same files
- Hash-based file identification
- Configurable cache size and expiration
- Automatic cache cleanup
"""

import os
import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta


CACHE_DIR = os.path.join(os.path.dirname(__file__), ".ocr_cache")
CACHE_EXPIRY_DAYS = int(os.environ.get("OCR_CACHE_EXPIRY_DAYS", "30"))
MAX_CACHE_SIZE_MB = int(os.environ.get("MAX_OCR_CACHE_SIZE_MB", "500"))


def ensure_cache_dir():
    """Ensure cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_file_hash(file_bytes: bytes) -> str:
    """Generate SHA256 hash of file content."""
    return hashlib.sha256(file_bytes).hexdigest()


def get_cache_path(file_hash: str) -> str:
    """Get cache file path for a given hash."""
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{file_hash}.cache")


def get_metadata_path(file_hash: str) -> str:
    """Get metadata file path for a given hash."""
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{file_hash}.meta.json")


def cache_ocr_result(file_bytes: bytes, ocr_lines: List[str], metadata: Optional[Dict] = None):
    """
    Cache OCR results for a file.
    
    Args:
        file_bytes: Original file bytes
        ocr_lines: OCR extracted lines
        metadata: Optional metadata (file name, type, etc.)
    """
    ensure_cache_dir()
    
    file_hash = get_file_hash(file_bytes)
    cache_path = get_cache_path(file_hash)
    metadata_path = get_metadata_path(file_hash)
    
    # Save OCR lines
    with open(cache_path, 'wb') as f:
        pickle.dump(ocr_lines, f)
    
    # Save metadata
    cache_metadata = {
        "file_hash": file_hash,
        "cached_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=CACHE_EXPIRY_DAYS)).isoformat(),
        "ocr_lines_count": len(ocr_lines),
        "file_size_bytes": len(file_bytes)
    }
    
    if metadata:
        cache_metadata.update(metadata)
    
    with open(metadata_path, 'w') as f:
        json.dump(cache_metadata, f, indent=2)
    
    print(f"✓ Cached OCR results for file (hash: {file_hash[:8]}...)")
    return file_hash


def get_cached_ocr_result(file_bytes: bytes) -> Optional[List[str]]:
    """
    Retrieve cached OCR results if available and not expired.
    
    Args:
        file_bytes: File bytes to look up
        
    Returns:
        Cached OCR lines if found and valid, None otherwise
    """
    ensure_cache_dir()
    
    file_hash = get_file_hash(file_bytes)
    cache_path = get_cache_path(file_hash)
    metadata_path = get_metadata_path(file_hash)
    
    # Check if cache exists
    if not os.path.exists(cache_path) or not os.path.exists(metadata_path):
        return None
    
    # Check expiration
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        expires_at = datetime.fromisoformat(metadata["expires_at"])
        if datetime.now() > expires_at:
            # Cache expired, remove it
            os.remove(cache_path)
            os.remove(metadata_path)
            return None
        
        # Load cached OCR lines
        with open(cache_path, 'rb') as f:
            ocr_lines = pickle.load(f)
        
        print(f"✓ Using cached OCR results (hash: {file_hash[:8]}...)")
        return ocr_lines
    
    except Exception as e:
        # If there's any error, remove corrupted cache
        print(f"Warning: Error reading cache: {e}")
        try:
            if os.path.exists(cache_path):
                os.remove(cache_path)
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
        except:
            pass
        return None


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache."""
    ensure_cache_dir()
    
    cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith('.cache')]
    total_size = 0
    expired_count = 0
    valid_count = 0
    
    for cache_file in cache_files:
        cache_path = os.path.join(CACHE_DIR, cache_file)
        total_size += os.path.getsize(cache_path)
        
        file_hash = cache_file.replace('.cache', '')
        metadata_path = get_metadata_path(file_hash)
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                expires_at = datetime.fromisoformat(metadata["expires_at"])
                if datetime.now() > expires_at:
                    expired_count += 1
                else:
                    valid_count += 1
            except:
                expired_count += 1
        else:
            expired_count += 1
    
    return {
        "total_files": len(cache_files),
        "valid_files": valid_count,
        "expired_files": expired_count,
        "total_size_mb": total_size / (1024 * 1024),
        "cache_dir": CACHE_DIR
    }


def cleanup_cache():
    """Remove expired cache entries and enforce size limits."""
    ensure_cache_dir()
    
    cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith('.cache')]
    removed_count = 0
    total_size = 0
    
    # First pass: remove expired entries
    for cache_file in cache_files:
        file_hash = cache_file.replace('.cache', '')
        cache_path = os.path.join(CACHE_DIR, cache_file)
        metadata_path = get_metadata_path(file_hash)
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                expires_at = datetime.fromisoformat(metadata["expires_at"])
                if datetime.now() > expires_at:
                    os.remove(cache_path)
                    os.remove(metadata_path)
                    removed_count += 1
                    continue
            except:
                # Corrupted metadata, remove cache
                os.remove(cache_path)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                removed_count += 1
                continue
        
        total_size += os.path.getsize(cache_path)
    
    # Second pass: enforce size limit (remove oldest if needed)
    if total_size > MAX_CACHE_SIZE_MB * 1024 * 1024:
        # Get all valid cache entries with timestamps
        cache_entries = []
        for cache_file in os.listdir(CACHE_DIR):
            if cache_file.endswith('.cache'):
                file_hash = cache_file.replace('.cache', '')
                cache_path = os.path.join(CACHE_DIR, cache_file)
                metadata_path = get_metadata_path(file_hash)
                
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                        expires_at = datetime.fromisoformat(metadata["expires_at"])
                        if datetime.now() <= expires_at:
                            cache_entries.append({
                                "hash": file_hash,
                                "cached_at": datetime.fromisoformat(metadata["cached_at"]),
                                "size": os.path.getsize(cache_path)
                            })
                    except:
                        pass
        
        # Sort by creation time (oldest first)
        cache_entries.sort(key=lambda x: x["cached_at"])
        
        # Remove oldest until under size limit
        current_size = total_size
        for entry in cache_entries:
            if current_size <= MAX_CACHE_SIZE_MB * 1024 * 1024:
                break
            
            cache_path = get_cache_path(entry["hash"])
            metadata_path = get_metadata_path(entry["hash"])
            
            if os.path.exists(cache_path):
                current_size -= entry["size"]
                os.remove(cache_path)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                removed_count += 1
    
    if removed_count > 0:
        print(f"✓ Cleaned up {removed_count} cache entry(ies)")
    
    return removed_count


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python ocr_cache.py stats    - Show cache statistics")
        print("  python ocr_cache.py cleanup  - Clean up expired and oversized cache")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "stats":
        stats = get_cache_stats()
        print("\nOCR Cache Statistics:")
        print(f"  Total cached files: {stats['total_files']}")
        print(f"  Valid files: {stats['valid_files']}")
        print(f"  Expired files: {stats['expired_files']}")
        print(f"  Total size: {stats['total_size_mb']:.2f} MB")
        print(f"  Cache directory: {stats['cache_dir']}")
    
    elif command == "cleanup":
        removed = cleanup_cache()
        print(f"Cleanup complete. Removed {removed} cache entry(ies).")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


