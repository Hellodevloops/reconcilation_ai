from flask import Blueprint, request, jsonify
from database_manager import DatabaseManager
import logging

manual_entry_bp = Blueprint('manual_entry', __name__)
db_manager = DatabaseManager()

@manual_entry_bp.route("/api/reconciliations/<int:reconciliation_id>/manual-entry", methods=["POST"])
def api_create_manual_entry(reconciliation_id: int):
    """Create a manual entry (invoice or bank transaction) and attach it to a reconciliation as unmatched."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        entry_type = data.get("type")  # "invoice" or "bank"
        if entry_type not in ["invoice", "bank"]:
            return jsonify({"error": "Invalid entry type. Must be 'invoice' or 'bank'"}), 400

        # Required fields
        description = data.get("description", "").strip()
        amount = data.get("amount")
        date = data.get("date", "").strip()

        if not description:
            return jsonify({"error": "Description is required"}), 400
        if amount is None:
            return jsonify({"error": "Amount is required"}), 400
        if not date:
            return jsonify({"error": "Date is required"}), 400

        # Optional fields
        invoice_number = data.get("invoice_number", "").strip() if entry_type == "invoice" else None
        vendor_name = data.get("vendor_name", "").strip() if entry_type == "invoice" else None
        reference_id = data.get("reference_id", "").strip() if entry_type == "bank" else None
        currency = data.get("currency", "GBP").strip()

        # Verify reconciliation exists
        check_sql = "SELECT id FROM reconciliations WHERE id = ?"
        try:
            result = db_manager.execute_query(check_sql, (reconciliation_id,))
        except Exception:
            check_sql_mysql = "SELECT id FROM reconciliations WHERE id = %s"
            result = db_manager.execute_query(check_sql_mysql, (reconciliation_id,))
        
        if not result:
            return jsonify({"error": "Reconciliation not found"}), 404

        # Insert manual entry
        if entry_type == "invoice":
            insert_sql = """
                INSERT INTO manual_invoice_entries 
                (reconciliation_id, description, amount, date, invoice_number, vendor_name, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (reconciliation_id, description, amount, date, invoice_number, vendor_name, currency)
        else:  # bank
            insert_sql = """
                INSERT INTO manual_bank_entries 
                (reconciliation_id, description, amount, date, reference_id, currency)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (reconciliation_id, description, amount, date, reference_id, currency)

        try:
            entry_id = db_manager.execute_insert(insert_sql, params)
        except Exception:
            # Try MySQL syntax
            if entry_type == "invoice":
                insert_sql_mysql = """
                    INSERT INTO manual_invoice_entries 
                    (reconciliation_id, description, amount, date, invoice_number, vendor_name, currency)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            else:
                insert_sql_mysql = """
                    INSERT INTO manual_bank_entries 
                    (reconciliation_id, description, amount, date, reference_id, currency)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
            entry_id = db_manager.execute_insert(insert_sql_mysql, params)

        return jsonify({
            "success": True,
            "message": f"Manual {entry_type} entry created successfully",
            "entry_id": entry_id,
            "entry_type": entry_type
        })

    except Exception as e:
        logging.error(f"Error creating manual entry: {str(e)}")
        return jsonify({"error": str(e)}), 500
