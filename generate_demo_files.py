from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import pandas as pd
from datetime import date, timedelta
import os

styles = getSampleStyleSheet()

# Get current directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# File paths - save in current directory
inv_pdf = os.path.join(current_dir, "demo_invoice.pdf")
inv_csv = os.path.join(current_dir, "demo_invoice.csv")
bank_pdf = os.path.join(current_dir, "demo_bank_statement.pdf")
bank_csv = os.path.join(current_dir, "demo_bank_statement.csv")

# Dummy matched data (small - only 4 rows)
invoice_data = [
    ["INV-101", "05/02/2024", "BOOKER WHOLESALE", 250.00],
    ["INV-102", "10/02/2024", "BOOKER WHOLESALE", 180.00],
    ["INV-103", "18/02/2024", "BOOKER WHOLESALE", 320.00],
    ["INV-104", "25/02/2024", "BOOKER WHOLESALE", 210.00],
]

invoice_df = pd.DataFrame(invoice_data, columns=["Invoice No", "Invoice Date", "Supplier", "Amount (£)"])
invoice_df.to_csv(inv_csv, index=False)
print(f"✓ Created: {inv_csv}")

bank_data = [
    ["06 Feb 2024", "BOOKER WHOLESALE INV-101", 250.00],
    ["11 Feb 2024", "BOOKER WHOLESALE INV-102", 180.00],
    ["19 Feb 2024", "BOOKER WHOLESALE INV-103", 320.00],
    ["26 Feb 2024", "BOOKER WHOLESALE INV-104", 210.00],
]

bank_df = pd.DataFrame(bank_data, columns=["Date", "Narration", "Amount (£)"])
bank_df.to_csv(bank_csv, index=False)
print(f"✓ Created: {bank_csv}")

# Invoice PDF
doc1 = SimpleDocTemplate(inv_pdf, pagesize=A4)
elements1 = [
    Paragraph("<b>Demo Invoice List</b>", styles["Title"]),
    Paragraph("Customer: POLEBROOK ARMS NORTHANTS LTD", styles["Normal"]),
    Paragraph("<br/>", styles["Normal"]),
]
table1 = Table([invoice_df.columns.tolist()] + invoice_df.values.tolist())
table1.setStyle(TableStyle([
    ("GRID", (0,0), (-1,-1), 0.5, colors.black),
    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
]))
elements1.append(table1)
doc1.build(elements1)
print(f"✓ Created: {inv_pdf}")

# Bank PDF
doc2 = SimpleDocTemplate(bank_pdf, pagesize=A4)
elements2 = [
    Paragraph("<b>Demo Bank Statement</b>", styles["Title"]),
    Paragraph("Account Holder: POLEBROOK ARMS NORTHANTS LTD", styles["Normal"]),
    Paragraph("<br/>", styles["Normal"]),
]
table2 = Table([bank_df.columns.tolist()] + bank_df.values.tolist())
table2.setStyle(TableStyle([
    ("GRID", (0,0), (-1,-1), 0.5, colors.black),
    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
]))
elements2.append(table2)
doc2.build(elements2)
print(f"✓ Created: {bank_pdf}")

print("\n✅ All 4 files created successfully!")
print(f"Location: {current_dir}")
print("\nFiles:")
print(f"  - {os.path.basename(inv_pdf)}")
print(f"  - {os.path.basename(inv_csv)}")
print(f"  - {os.path.basename(bank_pdf)}")
print(f"  - {os.path.basename(bank_csv)}")



