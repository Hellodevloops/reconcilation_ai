
import os
import sys
from PIL import Image
import pytesseract

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.multi_invoice_processor import MultiInvoiceProcessor

def verify_extraction(image_path):
    print(f"Verifying extraction for: {image_path}")
    
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    # Initialize processor
    processor = MultiInvoiceProcessor()
    
    # Process image
    print("Performing OCR and extraction...")
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        print("\n--- Extracted Text Preview ---")
        print(text[:500] + "...")
        print("------------------------------\n")
        
        invoice = processor._extract_invoice_from_text(text, 1, os.path.basename(image_path))
        
        if invoice:
            print("--- Extraction Results ---")
            print(f"Vendor: {invoice.vendor_name}")
            print(f"Invoice Number: {invoice.invoice_number}")
            print(f"Amount: {invoice.total_amount} {invoice.currency}")
            print(f"Date: {invoice.invoice_date}")
            print(f"Bank Name: {invoice.bank_name}")
            print(f"Account Name: {invoice.account_name}")
            print(f"Account Number: {invoice.account_number}")
            print(f"Sort Code: {invoice.sort_code}")
            print(f"IBAN: {invoice.iban}")
            print(f"BIC: {invoice.bic}")
            print(f"Confidence: {invoice.confidence_score}")
            print("--------------------------")
        else:
            print("Failed to identify as an invoice.")
            
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_image = r"C:/Users/Drashti Tandel/.gemini/antigravity/brain/6c0dccea-d403-4304-85fb-ac3fec068a6b/uploaded_image_1768289203885.png"
    verify_extraction(test_image)
