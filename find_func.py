
import re

filename = r"c:\xampp\htdocs\reconcile\aiprojects\python_ocr_reconcile\app.py"

try:
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if "def csv_to_transactions" in line:
            print(f"Line {i+1}: {line.strip()}")
except Exception as e:
    print(f"Error: {e}")
