"""
Training skeleton for ML-based reconciliation matcher.

High-level flow:
1. Read reconciled data from SQLite (reconcile.db).
2. Build a dataset of candidate pairs (invoice, bank) with features:
   - amount_diff
   - description_similarity
   - date_diff_days
3. Label pairs as:
   - 1 = match (comes from reconciliation_matches)
   - 0 = non-match (sampled random pairs that are not in matches)
4. Train a model (e.g. LogisticRegression, RandomForest) using scikit-learn.
5. Save the trained model to disk (model.pkl) using joblib.

Later, you can load model.pkl inside app.py and replace the _rule_based_match_score
with MODEL.predict_proba(features_vector)[0, 1].
"""

from __future__ import annotations

import os
import sqlite3
from typing import List, Tuple

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

from app import (
    DB_PATH,
    Transaction,
    _compute_match_features,
    _extract_key_terms,
    _normalize_text,
)  # type: ignore[attr-defined]
import re


def _get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def extract_vendor_name(description: str) -> str | None:
    """Extract vendor name from description."""
    if not description:
        return None
    
    # Patterns for vendor extraction
    vendor_patterns = [
        r"(?:from|to|payment\s+(?:to|from)|client|vendor|customer|bill\s+to)[\s:]+([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc)?)",
        r"^([A-Za-z0-9\s&.,\-]+)\s+(?:pvt|ltd|limited|inc|incorporated|llc)",
    ]
    
    for pattern in vendor_patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            vendor = re.sub(r'\s+(pvt|ltd|limited|inc|incorporated|llc)\.?$', '', vendor, flags=re.IGNORECASE).strip()
            if len(vendor) >= 3:  # Minimum length
                return vendor
    return None


def extract_invoice_number(description: str) -> str | None:
    """Extract invoice number from description."""
    if not description:
        return None
    
    inv_patterns = [
        r"(?:invoice\s*(?:no|number|#)?[\s:]*)([A-Za-z0-9\-]+)",
        r"(INV[-/]?[A-Za-z0-9\-]+)",
        r"([A-Z]{2,}[-/]?[0-9]+)",
    ]
    
    for pattern in inv_patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).strip().upper()
    return None


def load_transactions() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load invoice and bank transactions from the 'transactions' table.
    Also extracts vendor names and invoice numbers from descriptions.

    Returns:
        (invoice_df, bank_df)
    """
    conn = _get_connection()
    query = """
        SELECT id, kind, file_name, description, amount, date
        FROM transactions
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Extract vendor names and invoice numbers
    df['vendor_name'] = df['description'].apply(extract_vendor_name)
    df['invoice_number'] = df['description'].apply(extract_invoice_number)

    invoice_df = df[df["kind"] == "invoice"].copy()
    bank_df = df[df["kind"] == "bank"].copy()
    return invoice_df, bank_df


def load_positive_pairs() -> pd.DataFrame:
    """
    Load all matched invoice/bank pairs from reconciliation_matches.
    These will be labeled as y=1 (true match).
    """
    conn = _get_connection()
    query = """
        SELECT
            reconciliation_id,
            invoice_description,
            invoice_amount,
            invoice_date,
            bank_description,
            bank_amount,
            bank_date
        FROM reconciliation_matches
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def build_training_dataset(
    positive_pairs: pd.DataFrame,
    num_negative_samples_per_pos: int = 8,  # Increased from 5 for better negative sampling
) -> pd.DataFrame:
    """
    Build a training DataFrame with features + label.

    - For each positive pair (match), compute features and label=1.
    - For each positive, sample some random bank rows (with different amount)
      as "negative" examples and label=0.

    NOTE: This is a simple heuristic way to build a dataset.
    In production, you may want better negative sampling.
    """
    # Load all bank transactions once for negative sampling
    invoice_df, bank_df = load_transactions()

    rows = []

    for _, row in positive_pairs.iterrows():
        # --- Positive example ---
        # Extract vendor and invoice number from descriptions
        inv_vendor = extract_vendor_name(str(row["invoice_description"]))
        inv_inv_num = extract_invoice_number(str(row["invoice_description"]))
        bank_vendor = extract_vendor_name(str(row["bank_description"]))
        bank_inv_num = extract_invoice_number(str(row["bank_description"]))
        
        inv = Transaction(
            source="invoice",
            description=row["invoice_description"],
            amount=float(row["invoice_amount"]),
            date=str(row["invoice_date"]) if row["invoice_date"] else None,
            vendor_name=inv_vendor,
            invoice_number=inv_inv_num,
        )
        bank = Transaction(
            source="bank",
            description=row["bank_description"],
            amount=float(row["bank_amount"]),
            date=str(row["bank_date"]) if row["bank_date"] else None,
            vendor_name=bank_vendor,
            invoice_number=bank_inv_num,
        )

        feats = _compute_match_features(inv, bank)
        feats["label"] = 1
        rows.append(feats)

        # --- Negative examples ---
        # Sample bank rows with different amount as "non-matches"
        # Also try to get negative examples with similar amounts but different vendors/invoices
        available_neg = bank_df[
            (bank_df["amount"] != row["bank_amount"]) | 
            (bank_df["amount"] == row["bank_amount"])  # Include same amount but different vendor/invoice
        ]
        if available_neg.empty:
            continue

        # Prefer negative samples with different amounts first, then same amount but different vendor
        neg_candidates = available_neg.sample(
            n=min(num_negative_samples_per_pos, len(available_neg)),
            replace=False,
            random_state=42,
        )

        for _, neg in neg_candidates.iterrows():
            inv_neg = inv
            bank_neg = Transaction(
                source="bank",
                description=str(neg["description"]),
                amount=float(neg["amount"]),
                date=str(neg["date"]) if neg["date"] else None,
                vendor_name=neg.get("vendor_name") if "vendor_name" in neg else extract_vendor_name(str(neg["description"])),
                invoice_number=neg.get("invoice_number") if "invoice_number" in neg else extract_invoice_number(str(neg["description"])),
            )
            feats_neg = _compute_match_features(inv_neg, bank_neg)
            feats_neg["label"] = 0
            rows.append(feats_neg)

    return pd.DataFrame(rows)


def train_and_save_model(
    df: pd.DataFrame,
    model_path: str = "model.pkl",
) -> None:
    """
    Train an optimized RandomForest classifier with all enhanced features.
    Targets 95%+ accuracy.
    """
    # All available features including new ones
    feature_cols = [
        "amount_diff",
        "description_similarity", 
        "date_diff_days",
        "amount_match_exact",
        "amount_match_close",
        "amount_ratio",
        "vendor_similarity",
        "invoice_number_match",
        "reference_id_match",
    ]
    
    # Replace None with 0 or neutral values
    df = df.copy()
    df["date_diff_days"] = df["date_diff_days"].fillna(0)
    df["amount_match_exact"] = df["amount_match_exact"].fillna(0)
    df["amount_match_close"] = df["amount_match_close"].fillna(0)
    df["amount_ratio"] = df["amount_ratio"].fillna(0)
    df["vendor_similarity"] = df["vendor_similarity"].fillna(0)
    df["invoice_number_match"] = df["invoice_number_match"].fillna(0)
    if "reference_id_match" in df.columns:
        df["reference_id_match"] = df["reference_id_match"].fillna(0)

    # Check which features are available (some might be missing in old data)
    available_features = [col for col in feature_cols if col in df.columns]
    print(f"Using features: {available_features}")
    
    X = df[available_features].values
    y = df["label"].values

    print(f"Training dataset: {len(X)} samples, {len(available_features)} features")
    print(f"Positive samples: {sum(y)}, Negative samples: {sum(1 - y)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Optimized RandomForest for better accuracy - Enhanced for multiple invoices
    model = RandomForestClassifier(
        n_estimators=800,  # Increased from 500 - more trees for better accuracy
        max_depth=25,  # Increased from 20 - allow deeper trees for complex patterns
        min_samples_split=3,  # Reduced from 5 - more splits for better learning
        min_samples_leaf=1,  # Reduced from 2 - more granular splits
        max_features='sqrt',  # Use sqrt of features for each split
        random_state=42,
        class_weight="balanced_subsample",  # Handle imbalanced data
        n_jobs=-1,  # Use all CPU cores
        bootstrap=True,
        oob_score=True,  # Out-of-bag scoring
        max_samples=0.8,  # Use 80% of samples per tree for better generalization
    )
    
    print("Training model...")
    model.fit(X_train, y_train)

    # Evaluate on test set
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print("\n" + "="*60)
    print("Classification report (hold‑out test set):")
    print("="*60)
    print(classification_report(y_test, y_pred, digits=4))

    try:
        auc = roc_auc_score(y_test, y_proba)
        print(f"\nROC‑AUC: {auc:.4f}")
    except Exception:
        pass
    
    # Feature importance
    print("\n" + "="*60)
    print("Feature Importance:")
    print("="*60)
    feature_importance = list(zip(available_features, model.feature_importances_))
    feature_importance.sort(key=lambda x: x[1], reverse=True)
    for feature, importance in feature_importance:
        print(f"  {feature:25s}: {importance:.4f}")
    
    if hasattr(model, 'oob_score_'):
        print(f"\nOut-of-bag score: {model.oob_score_:.4f}")

    joblib.dump(model, model_path)
    print(f"\nModel saved to {os.path.abspath(model_path)}")
    print("="*60)


def main() -> None:
    """
    End-to-end pipeline:
    - Load positive pairs from reconciliation_matches.
    - Build labeled dataset (positive + negative).
    - Optionally save dataset to CSV (for inspection).
    - Train model and save to model.pkl.
    """
    print("Loading positive (matched) pairs from DB...")
    pos = load_positive_pairs()
    if pos.empty:
        print("No data in reconciliation_matches table. Run some reconciliations first.")
        return

    print(f"Loaded {len(pos)} matched pairs.")
    print("Building training dataset (with negative samples)...")
    df = build_training_dataset(pos)
    print(f"Final training rows: {len(df)}")

    # Optional: inspect / debug
    df.to_csv("reconciliation_training_data.csv", index=False)
    print("Training data saved to reconciliation_training_data.csv")

    print("Training model...")
    train_and_save_model(df)


if __name__ == "__main__":
    main()


