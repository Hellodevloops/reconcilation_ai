#!/usr/bin/env python3
"""
Quick fix for app.py SQLite leftovers
"""

import re

def fix_app_py():
    """Remove all SQLite references and fix syntax errors"""
    
    file_path = "app.py"
    
    # Read the current file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove all PRAGMA statements
    content = re.sub(r'.*PRAGMA.*\n', '', content)
    
    # Remove all conn.execute statements that are orphaned
    content = re.sub(r'\s*conn\.execute\([^)]*\)\s*\n', '', content)
    
    # Remove all cur.execute statements that are orphaned
    content = re.sub(r'\s*cur\.execute\([^)]*\)\s*\n', '', content)
    
    # Remove all conn.commit/conn.close statements that are orphaned
    content = re.sub(r'\s*conn\.(commit|close)\(\)\s*\n', '', content)
    
    # Remove all cur.lastrowid statements that are orphaned
    content = re.sub(r'\s*cur\.lastrowid\s*\n', '', content)
    
    # Remove all conn.row_factory statements
    content = re.sub(r'\s*conn\.row_factory.*\n', '', content)
    
    # Remove all cur = conn.cursor() statements
    content = re.sub(r'\s*cur\s*=\s*conn\.cursor\(\)\s*\n', '', content)
    
    # Remove duplicate function definitions
    lines = content.split('\n')
    cleaned_lines = []
    seen_functions = set()
    
    for line in lines:
        if line.strip().startswith('def store_reconciliation_summary('):
            func_name = 'store_reconciliation_summary'
            if func_name in seen_functions:
                # Skip duplicate function definition
                continue
            seen_functions.add(func_name)
        cleaned_lines.append(line)
    
    content = '\n'.join(cleaned_lines)
    
    # Write the cleaned content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Fixed app.py - removed SQLite leftovers")

if __name__ == "__main__":
    fix_app_py()
