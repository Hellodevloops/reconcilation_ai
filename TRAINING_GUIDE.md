# Complete Training Guide - 95%+ Accuracy

## Overview

This guide shows you how to train the model based on real invoice and bank statement formats.

## Examples Analyzed

### 1. Invoice Format (Booker Wholesale)
- **Date**: DD/MM/YYYY format (e.g., 04/05/2024)
- **Invoice No**: Numeric (e.g., 0327315)
- **Vendor**: Company name (e.g., "Booker Wholesale")
- **Invoice Total**: Final amount with £ symbol
- **Structure**: Table with columns: Date, Invoice No, Total Items, VAT amounts, Invoice Total

### 2. Bank Statement Format (Tide)
- **Date**: DD MMM YYYY format (e.g., "29 Feb 2024")
- **Details**: Vendor name / ref: (e.g., "CARLSBERG MARSTONS BREWING COMPANY / ref: KA POLEBROOK")
- **Amount**: Paid in/out with £ symbol
- **Transaction Type**: Domestic Transfer, Card Transaction, etc.

## Step-by-Step Training Process

### Step 1: Create Training Data

Run the training data generator based on your examples:

```bash
python create_training_data.py
```

This creates:
- 50 matched invoice-bank pairs
- 10 unmatched invoices
- 10 unmatched bank transactions
- Realistic data matching your formats

### Step 2: Run Reconciliations (Optional but Recommended)

Upload your actual invoice and bank statement files:

```bash
python app.py
```

Visit: http://localhost:5001/

Upload files and run reconciliations. This adds real data to your database.

### Step 3: Train the Model

```bash
python retrain_model.py
```

This will:
- Extract all matched pairs from database
- Extract vendor names and invoice numbers automatically
- Build training dataset with 8 features
- Train optimized RandomForest model
- Show accuracy metrics

### Step 4: Verify Model

Check the output:
- Accuracy should be 90%+
- Feature importance will show which features matter most
- ROC-AUC score should be high

### Step 5: Test with New Data

Restart the app and test with new reconciliations:

```bash
# Stop current app (Ctrl+C)
python app.py
```

Run new reconciliations - accuracy should be much better!

## Enhanced Features Implemented

### 1. Invoice Parsing Improvements

✅ **Date Formats Supported**:
- DD/MM/YYYY (04/05/2024) - Prioritized for UK/invoices
- DD MMM YYYY (29 Feb 2024) - For bank statements
- Multiple other formats

✅ **Invoice Number Extraction**:
- From "Invoice No:" column
- From description text
- Patterns: INV-123, 0327315, etc.

✅ **Invoice Total Detection**:
- Prefers "Invoice Total" column
- Falls back to "Total" column
- Handles £, $, ₹ currency symbols

✅ **Vendor Name Extraction**:
- From headers
- From "Client:", "Vendor:" labels
- From company names with Ltd/Pvt/etc.

### 2. Bank Statement Parsing Improvements

✅ **Vendor Name Extraction**:
- "CARLSBERG MARSTONS BREWING COMPANY / ref: KA POLEBROOK"
- "Payment received from ABC Pvt Ltd"
- Multiple pattern matching

✅ **Invoice Number from Bank Description**:
- Extracts from "ref: INV-123" patterns
- Handles various formats

✅ **Date Parsing**:
- Tide format: "29 Feb 2024"
- Multiple formats supported

### 3. Enhanced Matching Algorithm

✅ **8 Features Used**:
1. `amount_diff` - Amount difference
2. `description_similarity` - Text similarity
3. `date_diff_days` - Date difference
4. `amount_match_exact` - Exact amount match (binary)
5. `amount_match_close` - Close amount match (binary)
6. `amount_ratio` - Amount ratio
7. `vendor_similarity` - Vendor name similarity (NEW)
8. `invoice_number_match` - Invoice number match (NEW)

✅ **Scoring Weights**:
- Invoice Number Match: 25% (highest priority)
- Vendor Name Match: 20%
- Amount Match: 25%
- Description: 15%
- Date: 15%

## Expected Results

After proper training:

- **Invoice Accuracy**: 90-100%
- **Bank Accuracy**: 85-95%+
- **Better matching** with vendor names
- **Invoice numbers** properly matched
- **Amount matching** improved

## Troubleshooting

### Low Accuracy?

1. **Check Training Data**:
   - Run `create_training_data.py` to add more data
   - Run more reconciliations to build real data

2. **Verify Data Quality**:
   - Ensure invoices have clear vendor names
   - Ensure invoice numbers are present
   - Check that bank descriptions include vendor names

3. **Retrain**:
   ```bash
   python retrain_model.py
   ```

### Model Not Using New Features?

1. Check if model.pkl exists
2. Delete old model.pkl: `rm model.pkl`
3. Retrain: `python retrain_model.py`

### Dates Not Matching?

- Check date formats in your files
- Ensure dates are parseable (DD/MM/YYYY or DD MMM YYYY)
- Check date extraction in transaction descriptions

## Quick Start Checklist

- [ ] Run `python create_training_data.py` - Creates sample training data
- [ ] Run some reconciliations with your files - Adds real data
- [ ] Run `python retrain_model.py` - Trains the model
- [ ] Check accuracy metrics in output
- [ ] Restart app: `python app.py`
- [ ] Test with new reconciliations
- [ ] Verify accuracy is 90%+

## Files Modified

1. **app.py** - Enhanced parsing for invoices and bank statements
2. **train_model.py** - Improved training with 8 features
3. **create_training_data.py** - NEW: Creates training data from examples
4. **retrain_model.py** - Quick retrain script

## Support

If accuracy is still low:
1. Share sample invoice and bank statement data
2. Check feature importance output
3. Ensure training data is diverse
4. Retrain with more data

