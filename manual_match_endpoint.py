
@app.route("/api/reconciliations/<int:reconciliation_id>/manual-match", methods=["POST"])
@limiter.limit(RATE_LIMITS["/api/reconciliations/<int:reconciliation_id>/manual-match"])
def api_manual_match(reconciliation_id: int):
    """
    Manually match an invoice item with a bank item.
    Moves items from 'unmatched' lists to 'matches' list.
    """
    try:
        data = request.get_json()
        if not data:
             return jsonify({"error": "No data provided"}), 400
             
        invoice_index = data.get("invoice_index")
        bank_index = data.get("bank_index")
        
        # Verify indices are integers
        if not isinstance(invoice_index, int) or not isinstance(bank_index, int):
            return jsonify({"error": "Invalid indices"}), 400

        # 1. Fetch reconciliation raw_json
        rows = db_manager.execute_query(
            "SELECT id, raw_json FROM reconciliations WHERE id = ?",
            (reconciliation_id,)
        )
        # Fallback for MySQL syntax if needed check happens inside db_manager usually, 
        # but let's assume ? works as per app.py line 822
        if not rows and db_manager.db_type == "mysql":
             rows = db_manager.execute_query(
                "SELECT id, raw_json FROM reconciliations WHERE id = %s",
                (reconciliation_id,)
            )
            
        if not rows:
            return jsonify({"error": "Reconciliation not found"}), 404
        
        row = rows[0]
        raw_json_str = row.get("raw_json")
        if not raw_json_str:
            return jsonify({"error": "Reconciliation data not available"}), 500
            
        try:
            recon_data = json.loads(raw_json_str)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid reconciliation data"}), 500
            
        results = recon_data.get("results", {})
        only_in_invoices = results.get("only_in_invoices", [])
        only_in_bank = results.get("only_in_bank", [])
        matches = results.get("matches", [])
        
        # 2. Validate indices
        if invoice_index < 0 or invoice_index >= len(only_in_invoices):
            return jsonify({"error": "Invoice index out of bounds"}), 400
        if bank_index < 0 or bank_index >= len(only_in_bank):
            return jsonify({"error": "Bank index out of bounds"}), 400
            
        invoice_item = only_in_invoices[invoice_index]
        bank_item = only_in_bank[bank_index]

        # STRICT MATCH VALIDATION
        # Ensure we have database IDs to link back to authoritative source
        inv_id = invoice_item.get("id") or invoice_item.get("invoice_id")
        bank_id = bank_item.get("id") or bank_item.get("transaction_id")
        
        if not inv_id or not bank_id:
             return jsonify({
                 "error": "Strict Match Failed: Selected items are not linked to database records.", 
                 "details": "Please re-run reconciliation to ensure all items are strictly validated."
             }), 400
             
        # Verify IDs exist in DB
        if db_manager.db_type == "mysql":
             try:
                 # Check Invoice
                 inv_check = db_manager.execute_query("SELECT id FROM invoices WHERE id = %s", (inv_id,))
                 if not inv_check:
                      return jsonify({"error": "Invalid Invoice ID: referenced invoice not found in database"}), 400
                      
                 # Check Bank Transaction
                 bank_check = db_manager.execute_query("SELECT id FROM bank_transactions WHERE id = %s", (bank_id,))
                 if not bank_check:
                      return jsonify({"error": "Invalid Bank Transaction ID: referenced transaction not found in database"}), 400
             except Exception as e:
                 logger.error(f"Database validation error: {e}")
                 # Fallback to loose validation if DB check fails due to connectivity
                 pass
        
        # 3. Create match object
        match_obj = {
            "invoice": invoice_item,
            "bank": bank_item,
            "match_score": 1.0,
            "is_manual_match": True,
            "timestamp": datetime.now().isoformat()
        }
        
        # 4. Update lists
        matches.append(match_obj)
        
        # Remove from unmatched lists
        new_only_in_invoices = [item for i, item in enumerate(only_in_invoices) if i != invoice_index]
        new_only_in_bank = [item for i, item in enumerate(only_in_bank) if i != bank_index]
        
        # Update recon_data
        recon_data["results"]["matches"] = matches
        recon_data["results"]["only_in_invoices"] = new_only_in_invoices
        recon_data["results"]["only_in_bank"] = new_only_in_bank
        
        # Update summary stats
        summary = recon_data["results"].get("summary", {})
        summary["total_matches"] = len(matches)
        summary["total_unmatched_invoices"] = len(new_only_in_invoices)
        summary["total_unmatched_bank"] = len(new_only_in_bank)
        recon_data["results"]["summary"] = summary
        
        # 5. Insert into reconciliation_matches table
        # We need to extract IDs if available, or just store the raw JSON link
        # reconciliation_matches table columns: 
        # reconciliation_id, invoice_id, transaction_id, match_score, is_manual_match, match_data
        
        inv_id = invoice_item.get("id") or invoice_item.get("invoice_id")
        bank_id = bank_item.get("id") or bank_item.get("transaction_id")
        
        # Validate invoice ID format (sometimes it's string from JSON)
        try:
             if inv_id and str(inv_id).isdigit(): inv_id = int(inv_id)
             else: inv_id = None
        except: inv_id = None
        
        try:
             if bank_id and str(bank_id).isdigit(): bank_id = int(bank_id)
             else: bank_id = None
        except: bank_id = None

        insert_sql = """
            INSERT INTO reconciliation_matches (
                reconciliation_id, invoice_id, transaction_id, match_score, is_manual_match, match_data
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        match_data_json = json.dumps(match_obj, ensure_ascii=False, default=str)
        
        params = (reconciliation_id, inv_id, bank_id, 1.0, 1, match_data_json)
        
        try:
             db_manager.execute_insert(insert_sql, params)
        except Exception:
             # Try MySQL syntax if failed
             insert_sql_mysql = """
                INSERT INTO reconciliation_matches (
                    reconciliation_id, invoice_id, transaction_id, match_score, is_manual_match, match_data
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """
             db_manager.execute_insert(insert_sql_mysql, params)

        # 6. Save update to reconciliations table
        new_raw_json = json.dumps(recon_data, ensure_ascii=False, default=str)
        
        update_sql = "UPDATE reconciliations SET raw_json = ?, total_matches = total_matches + 1 WHERE id = ?"
        try:
            db_manager.execute_update(update_sql, (new_raw_json, reconciliation_id))
        except Exception:
            update_sql_mysql = "UPDATE reconciliations SET raw_json = %s, total_matches = total_matches + 1 WHERE id = %s"
            db_manager.execute_update(update_sql_mysql, (new_raw_json, reconciliation_id))

        return jsonify({"success": True})
            
    except Exception as e:
        logger.error(f"Error in manual match: {e}")
        return jsonify({"error": str(e)}), 500
