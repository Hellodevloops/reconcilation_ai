
import re
import sys
import os

# Add project root to path
sys.path.insert(0, os.getcwd())

from services.multi_invoice_processor import MultiInvoiceProcessor

def test_regex_extraction():
    processor = MultiInvoiceProcessor()
    
    # Test Case 1: Standard Invoice Number
    text1 = """
    INVOICE
    Number: INV-2023-001
    Date: 2023-10-27
    """
    inv_num1 = processor._extract_invoice_number(text1)
    print(f"Test 1 (Standard): Expected 'INV-2023-001', Got '{inv_num1}' - {'PASS' if inv_num1 == 'INV-2023-001' else 'FAIL'}")

    # Test Case 2: Multiline Invoice Number (User Case)
    text2 = """
    TAX INVOICE
    HSD Capital / Floozie Ltd
    Invoice Number
    INV-0111
    
    Date: 2023-10-27
    """
    inv_num2 = processor._extract_invoice_number(text2)
    print(f"Test 2 (Multiline): Expected 'INV-0111', Got '{inv_num2}' - {'PASS' if inv_num2 == 'INV-0111' else 'FAIL'}")

    # Test Case 3: Line Items
    text3 = """
    Description    Quantity    Unit Price    VAT    Amount
    Consulting Services    10    150.00    20%    1,500.00
    Web Development        1     500.00    20%      500.00
    """
    items = processor._extract_line_items(text3)
    print(f"Test 3 (Line Items): Found {len(items)} items")
    if len(items) >= 2:
        print(f"  Item 1: {items[0].description} | {items[0].total_amount}")
        print(f"  Item 2: {items[1].description} | {items[1].total_amount}")
    
    # Test Case 4: Total GBP
    text4 = """
    Subtotal: 2000.00
    VAT: 400.00
    Total GBP: 2,400.00
    """
    total_gbp = processor._extract_total_gbp(text4)
    print(f"Test 4 (Total GBP): Expected 2400.0, Got {total_gbp} - {'PASS' if total_gbp == 2400.0 else 'FAIL'}")

    # Test Case 5: Amount GBP variance
    text5 = """
    Amount GBP: 1,234.56
    """
    total_gbp_2 = processor._extract_total_gbp(text5)
    print(f"Test 5 (Amount GBP): Expected 1234.56, Got {total_gbp_2} - {'PASS' if total_gbp_2 == 1234.56 else 'FAIL'}")

if __name__ == "__main__":
    test_regex_extraction()
