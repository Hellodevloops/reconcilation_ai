#!/usr/bin/env python3
"""
Script to update all remaining SQLite connections in app.py to use MySQL
"""

import re

def update_app_py():
    """Update app.py to use MySQL instead of SQLite"""
    
    file_path = "app.py"
    
    # Read the current file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Patterns to replace
    replacements = [
        # Replace sqlite3.connect with database manager calls
        (r'conn = sqlite3\.connect\(DB_PATH.*?\)', 'results = db_manager.execute_query(query, params)'),
        
        # Replace conn.row_factory = sqlite3.Row (not needed with our db_manager)
        (r'conn\.row_factory = sqlite3\.Row\n\s*cur = conn\.cursor\(\)', ''),
        
        # Replace cur.execute with db_manager calls for SELECT
        (r'cur\.execute\((.*?)\)\n\s*rows = \[dict\(r\) for r in cur\.fetchall\(\)\]\n\s*conn\.close\(\)', 
         r'results = db_manager.execute_query(\1)'),
        
        # Replace cur.execute for single row
        (r'cur\.execute\((.*?)\)\n\s*row = cur\.fetchone\(\)\n\s*conn\.close\(\)', 
         r'results = db_manager.execute_query(\1)\n        row = results[0] if results else None'),
        
        # Replace cur.execute for updates
        (r'cur\.execute\((.*?)\)\n\s*conn\.commit\(\)\n\s*conn\.close\(\)', 
         r'db_manager.execute_update(\1)'),
        
        # Replace cur.lastrowid
        (r'cur\.lastrowid', 'insert_id'),
        
        # Replace conn.commit() and conn.close()
        (r'conn\.commit\(\)\s*\n\s*conn\.close\(\)', ''),
        
        # Replace conn.rollback() and conn.close()
        (r'conn\.rollback\(\)\s*\n\s*conn\.close\(\)', ''),
    ]
    
    # Apply replacements
    updated_content = content
    for pattern, replacement in replacements:
        updated_content = re.sub(pattern, replacement, updated_content, flags=re.MULTILINE | re.DOTALL)
    
    # Write the updated content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print("Updated app.py with MySQL integration")

if __name__ == "__main__":
    update_app_py()
