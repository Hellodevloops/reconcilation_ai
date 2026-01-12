## Python OCR Reconciliation (No OpenAI)

This folder contains a **standalone Python backend** that provides:

- **OCR** for invoice and bank statement images (using `pytesseract` and `Pillow`)
- **Reconciliation** between invoice and bank transactions
- **JSON API** with a **single-page HTML frontend** (`static/index.html`)

The main application file is `app.py`.

### 1. Install Python dependencies

Make sure you have **Python 3.10+** installed.

From this folder (`python_ocr_reconcile`), run:

```bash
pip install -r requirements.txt
```

You also need **Tesseract OCR** installed on your system:

- On Windows, install from: `https://github.com/tesseract-ocr/tesseract`
- Then ensure `tesseract.exe` is in your `PATH`, or configure `pytesseract.pytesseract.tesseract_cmd` in `app.py`.

### 2. Run the Python server

From `python_ocr_reconcile`:

```bash
python app.py
```

The server will start on `http://localhost:5001/`.

### 3. Use the single-page app

Open this in your browser:

- `http://localhost:5001/`

Then:

1. Upload an **invoice** image file.
2. Upload a **bank statement** image file.
3. Click **“Run OCR & Reconcile”**.

The OCR + reconciliation will run, and:

- The **JSON response** will appear on the left.
- A small **summary** (matches, only in invoices, only in bank) will appear on the right.

### 4. API details (for developers)

Endpoint:

- **POST** `/api/reconcile`

Request:

- `multipart/form-data` with:
  - `invoice`: file (image)
  - `bank`: file (image)

Response (JSON), example shape:

```json
{
  "invoice_lines": ["... raw OCR lines ..."],
  "bank_lines": ["... raw OCR lines ..."],
  "reconciliation": {
    "matches": [
      {
        "invoice": { "source": "invoice", "description": "...", "amount": 123.45, "date": "2025-01-01" },
        "bank": { "source": "bank", "description": "...", "amount": 123.45, "date": "2025-01-01" }
      }
    ],
    "only_in_invoices": [
      { "source": "invoice", "description": "...", "amount": 500.0, "date": null }
    ],
    "only_in_bank": [
      { "source": "bank", "description": "...", "amount": 800.0, "date": null }
    ]
  }
}
```

You can call this API from any other frontend if you don't want to use `static/index.html`.

## Training the ML Model for 95%+ Accuracy

The system now uses enhanced features including:
- Vendor name matching
- Invoice number matching
- Amount matching (exact, close, ratio)
- Description similarity
- Date matching

### Quick Retrain (Recommended)

After running some reconciliations to build up training data:

```bash
python retrain_model.py
```

This will:
1. Load all matched pairs from the database
2. Extract vendor names and invoice numbers automatically
3. Build training dataset with 8 enhanced features
4. Train optimized RandomForest model (500 trees, tuned hyperparameters)
5. Save model to `model.pkl`
6. Show accuracy metrics and feature importance

### Manual Training

For more control:

```bash
python train_model.py
```

### Training Data Requirements

For best results (95%+ accuracy):
- **Minimum**: 50+ matched pairs in database
- **Recommended**: 100+ matched pairs
- **Optimal**: 200+ matched pairs

The more diverse your training data, the better the model will perform.

### Model Features

The trained model uses these 8 features:
1. `amount_diff` - Absolute difference in amounts
2. `description_similarity` - Text similarity (0-1)
3. `date_diff_days` - Days difference between dates
4. `amount_match_exact` - Binary: exact amount match
5. `amount_match_close` - Binary: within 1% difference
6. `amount_ratio` - Ratio of smaller to larger amount
7. `vendor_similarity` - Vendor name similarity (0-1)
8. `invoice_number_match` - Binary: invoice number match

### After Training

1. Check the accuracy metrics in the output
2. Review feature importance to see what matters most
3. Restart Flask app: `python app.py`
4. Run new reconciliations - accuracy should be 90-95%+

### Improving Accuracy Further

If accuracy is still below 95%:
1. Run more reconciliations to get more training data
2. Ensure your invoices have clear vendor names and invoice numbers
3. Check that bank statements include payment descriptions with vendor names
4. Retrain the model: `python retrain_model.py`

