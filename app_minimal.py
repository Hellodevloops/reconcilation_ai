#!/usr/bin/env python3
"""
Minimal working app.py for MySQL testing
"""

from flask import Flask, jsonify
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database_manager import db_manager
    print("Database manager imported successfully")
    
    # Test connection
    result = db_manager.execute_query("SELECT 1 as test")
    if result and result[0]['test'] == 1:
        print("Database connection successful")
        
        # Create Flask app
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return jsonify({
                "status": "MySQL integration working!",
                "database": "reconciltion",
                "message": "Your reconciliation system is ready with MySQL"
            })
        
        @app.route('/test-db')
        def test_db():
            try:
                tables = db_manager.execute_query("SHOW TABLES")
                return jsonify({
                    "status": "success",
                    "tables": [table for table in tables]
                })
            except Exception as e:
                return jsonify({
                    "status": "error", 
                    "message": str(e)
                }), 500
        
        if __name__ == '__main__':
            print("Starting Flask application on http://localhost:5001")
            app.run(host='0.0.0.0', port=5001, debug=True)
    else:
        print("Database connection failed")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
