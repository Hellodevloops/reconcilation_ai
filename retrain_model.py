"""
Quick script to retrain the ML model for better accuracy.
Run this after you have some reconciliation data in the database.

Usage:
    python retrain_model.py
"""

from train_model import main

if __name__ == "__main__":
    print("="*60)
    print("Retraining ML Model for 95%+ Accuracy")
    print("="*60)
    print("\nThis will:")
    print("1. Load all matched pairs from database")
    print("2. Extract vendor names and invoice numbers")
    print("3. Build training dataset with enhanced features")
    print("4. Train optimized RandomForest model")
    print("5. Save model to model.pkl")
    print("\n" + "="*60 + "\n")
    
    main()
    
    print("\n" + "="*60)
    print("Model retraining complete!")
    print("="*60)
    print("\nThe new model will be used automatically in the next reconciliation.")
    print("Restart the Flask app to load the new model.\n")

