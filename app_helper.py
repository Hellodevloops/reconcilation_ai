
    def _enrich_items_with_ids(self, items: List[Dict[str, Any]], item_type: str) -> List[Dict[str, Any]]:
        """
        Enrich a list of bank or invoice items with their corresponding database IDs.
        
        Args:
            items: List of dictionaries (unmatched items).
            item_type: "bank" or "invoice".
            
        Returns:
            List of dictionaries with 'id' or 'transaction_id'/'invoice_id' populated if found.
        """
        if not items:
            return []
            
        enriched_items = []
        for item in items:
            enriched_item = item.copy()
            
            # If ID is already present, keep it
            if item.get("id"):
                enriched_items.append(enriched_item)
                continue
                
            try:
                resolved_id = None
                
                if item_type == "bank":
                    # Lookup in bank_transactions
                    date_val = item.get("date")
                    desc_val = item.get("description")
                    amount_val = item.get("amount")
                    
                    if date_val and amount_val is not None:
                        # Try exact match first
                        query = """
                            SELECT id FROM bank_transactions 
                            WHERE transaction_date = %s 
                              AND ABS(amount) = %s 
                            ORDER BY id DESC LIMIT 1
                        """
                        params = [date_val, abs(float(amount_val))]
                        
                        # Add description check if available (loosely)
                        if desc_val:
                            # We don't do exact desc match here to be safe, but could improve strictness
                            pass
                            
                        row = db_manager.execute_query(query, tuple(params))
                        if row and row[0].get("id"):
                             resolved_id = row[0]["id"]
                             enriched_item["transaction_id"] = resolved_id
                             enriched_item["id"] = resolved_id # Common interface
                             
                elif item_type == "invoice":
                    # Lookup in invoices
                    amount_val = item.get("amount") or item.get("total_amount")
                    inv_no = item.get("invoice_number")
                    
                    if inv_no:
                         query = "SELECT id FROM invoices WHERE invoice_number = %s ORDER BY id DESC LIMIT 1"
                         row = db_manager.execute_query(query, (inv_no,))
                         if row and row[0].get("id"):
                             resolved_id = row[0]["id"]
                    
                    if not resolved_id and amount_val is not None:
                         # Fallback to amount match if invoice number missing/mismatched
                         query = "SELECT id FROM invoices WHERE ABS(total_amount) = %s ORDER BY id DESC LIMIT 1"
                         row = db_manager.execute_query(query, (abs(float(amount_val)),))
                         if row and row[0].get("id"):
                             resolved_id = row[0]["id"]
                             
                    if resolved_id:
                        enriched_item["invoice_id"] = resolved_id
                        enriched_item["id"] = resolved_id
            
            except Exception as e:
                # Log but don't crash
                print(f"Error enriching {item_type} item: {e}")
                
            enriched_items.append(enriched_item)
            
        return enriched_items
