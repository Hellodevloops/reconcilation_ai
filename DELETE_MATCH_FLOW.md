# Delete Match Functionality - Complete Flow & Logic

## Overview
This document explains the **Delete Match** functionality, including the complete flow, backend logic, and user experience.

---

## 1. USER INTERFACE

### Button Location
- **Section:** "Matched Transactions (X)"
- **Location:** Action column in each matched transaction row
- **Button Text:** "Delete" (changed from "Unmatch" for clarity)
- **Button Icon:** 🗑️ (trash icon - `fa-trash`)
- **Button Color:** Red (indicates destructive action)

### Visual Design
```html
<button 
  type="button" 
  class="json-toggle" 
  style="padding: 4px 10px; font-size: 0.75rem; 
         background: rgba(239, 68, 68, 0.2); 
         border-color: rgba(239, 68, 68, 0.4); 
         color: #f87171;"
  onclick="unmatchTransaction(reconciliationId, matchId, event)"
  title="Delete this match permanently"
>
  <i class="fas fa-trash"></i> Delete
</button>
```

---

## 2. COMPLETE FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INTERACTION FLOW                         │
└─────────────────────────────────────────────────────────────────┘

Step 1: User Views Matched Transactions
    │
    ├─► Sees list of matched transactions
    ├─► Each row shows: Invoice ↔ Bank Transaction
    └─► Each row has "Delete" button in Action column
        │
        │
Step 2: User Clicks "Delete" Button
    │
    ├─► Event: onclick="unmatchTransaction(reconciliationId, matchId, event)"
    ├─► event.stopPropagation() - Prevents row click event
    └─► Function: unmatchTransaction() is called
        │
        │
Step 3: Confirmation Dialog
    │
    ├─► Shows confirmation message:
    │   "Are you sure you want to DELETE this match?
    │    
    │    This will permanently remove the match between 
    │    the invoice and bank transaction. 
    │    This action cannot be undone.
    │    
    │    After deletion, you can re-run reconciliation 
    │    to see these transactions in the unmatched sections."
    │
    ├─► User Options:
    │   ├─► "Cancel" → Function returns, no action taken
    │   └─► "OK" → Proceeds to deletion
        │
        │
Step 4: Frontend Processing
    │
    ├─► Shows loading status: "Deleting match..."
    ├─► Makes API call:
    │   DELETE /api/reconciliations/{reconciliationId}/matches/{matchId}
    │
    └─► Waits for response
        │
        │
Step 5: Backend Processing
    │
    ├─► Endpoint: api_delete_match(reconciliation_id, match_id)
    │
    ├─► Step 5.1: Database Connection
    │   └─► Opens SQLite connection to reconciliation database
    │
    ├─► Step 5.2: Validation
    │   ├─► Checks if match exists
    │   ├─► Checks if match belongs to the reconciliation
    │   └─► If not found → Returns 404 error
    │
    ├─► Step 5.3: Get Match Info
    │   └─► Retrieves match details (including is_manual_match flag)
    │
    ├─► Step 5.4: Delete Match
    │   ├─► Executes SQL: DELETE FROM reconciliation_matches 
    │   │                WHERE id = ? AND reconciliation_id = ?
    │   ├─► Commits transaction
    │   └─► Closes database connection
    │
    ├─► Step 5.5: Cache Invalidation
    │   ├─► Removes cached match data for this reconciliation
    │   └─► Cache key: "matches_{reconciliation_id}"
    │
    └─► Step 5.6: Response
        ├─► Returns JSON with success status
        ├─► Includes match_id and reconciliation_id
        └─► Includes match type (Manual/Automatic)
        │
        │
Step 6: Frontend Response Handling
    │
    ├─► If Success (200 OK):
    │   ├─► Shows success message: 
    │   │   "✓ Match deleted successfully! The transaction has been 
    │   │    removed from matched list. Re-run reconciliation to see 
    │   │    updated results."
    │   ├─► Removes row from UI immediately
    │   │   └─► Uses: document.querySelector(`tr[data-match-id="${matchId}"]`)
    │   ├─► Updates match count in header (if displayed)
    │   └─► Changes status to "success" (green)
    │
    └─► If Error (4xx/5xx):
        ├─► Shows error message
        ├─► Displays error details to user
        └─► Changes status to "error" (red)
        │
        │
Step 7: Post-Deletion State
    │
    ├─► Match is permanently removed from database
    ├─► Row is removed from UI
    ├─► Match count is updated
    └─► User can re-run reconciliation to see transactions 
        in unmatched sections
```

---

## 3. BACKEND LOGIC DETAILS

### API Endpoint
```
DELETE /api/reconciliations/{reconciliation_id}/matches/{match_id}
```

### Function: `api_delete_match()`

#### Step-by-Step Logic:

**1. Input Validation**
```python
# Parameters received from URL
reconciliation_id: int  # ID of the reconciliation
match_id: int          # ID of the match to delete
```

**2. Database Connection**
```python
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
cur = conn.cursor()
```

**3. Match Existence Check**
```python
cur.execute(
    """
    SELECT id, is_manual_match FROM reconciliation_matches 
    WHERE id = ? AND reconciliation_id = ?
    """,
    (match_id, reconciliation_id)
)
match_row = cur.fetchone()

# If match doesn't exist or doesn't belong to reconciliation
if not match_row:
    return jsonify({"error": "Match not found"}), 404
```

**4. Match Deletion**
```python
# Delete the match record
cur.execute(
    "DELETE FROM reconciliation_matches WHERE id = ? AND reconciliation_id = ?",
    (match_id, reconciliation_id)
)

# Commit the transaction
conn.commit()
conn.close()
```

**5. Cache Invalidation**
```python
cache_key = f"matches_{reconciliation_id}"
with _cache_lock:
    if cache_key in _cache:
        del _cache[cache_key]
```

**6. Response Generation**
```python
match_type = "Manual" if match_row["is_manual_match"] else "Automatic"
return jsonify({
    "success": True,
    "message": f"{match_type} match deleted successfully",
    "match_id": match_id,
    "reconciliation_id": reconciliation_id
})
```

### Error Handling

**404 - Match Not Found**
```python
if not match_row:
    return jsonify({
        "error": f"Match ID {match_id} not found for reconciliation {reconciliation_id}"
    }), 404
```

**500 - Internal Server Error**
```python
except Exception as e:
    return jsonify({
        "error": "Internal server error while deleting match.",
        "details": str(e),
        "traceback": error_traceback if app.debug else None
    }), 500
```

---

## 4. FRONTEND LOGIC DETAILS

### Function: `unmatchTransaction()`

#### Complete Code Flow:

```javascript
async function unmatchTransaction(reconciliationId, matchId, event) {
    // 1. Prevent event bubbling
    event.stopPropagation();
    
    // 2. Show confirmation dialog
    if (!confirm('Are you sure you want to DELETE this match?...')) {
        return; // User cancelled
    }
    
    // 3. Show loading state
    statusEl.textContent = "Deleting match...";
    statusEl.className = "status processing show";
    
    // 4. Make API call
    const response = await fetch(
        `/api/reconciliations/${reconciliationId}/matches/${matchId}`,
        { method: 'DELETE' }
    );
    
    // 5. Parse response
    const result = await response.json();
    
    // 6. Handle response
    if (!response.ok) {
        // Error handling
        statusEl.textContent = `Error: ${result.error}`;
        statusEl.className = "status error show";
        alert(`Error deleting match: ${result.error}`);
        return;
    }
    
    // 7. Success handling
    statusEl.textContent = "✓ Match deleted successfully!...";
    statusEl.className = "status success show";
    
    // 8. Remove row from UI
    const row = document.querySelector(`tr[data-match-id="${matchId}"]`);
    if (row) {
        row.remove();
    }
    
    // 9. Update match count
    const remainingMatches = document.querySelectorAll('.matches-table tbody tr').length;
    // Update header if needed
}
```

---

## 5. DATABASE IMPACT

### Table: `reconciliation_matches`

**Before Deletion:**
```
| id | reconciliation_id | invoice_description | bank_description | match_score | is_manual_match |
|----|-------------------|---------------------|------------------|-------------|-----------------|
| 5  | 123              | Invoice #001        | Bank TX #001     | 0.95        | 0               |
```

**After Deletion:**
```
| id | reconciliation_id | invoice_description | bank_description | match_score | is_manual_match |
|----|-------------------|---------------------|------------------|-------------|-----------------|
| (row removed)                                                                                    |
```

### What Happens to Transactions?

**Important:** The transactions themselves are NOT deleted. Only the match relationship is removed.

- **Invoice transaction:** Still exists in original invoice data
- **Bank transaction:** Still exists in original bank data
- **Match relationship:** Deleted from `reconciliation_matches` table

**After Re-running Reconciliation:**
- The invoice will appear in "Unmatched Invoices" section
- The bank transaction will appear in "Unmatched Bank Transactions" section
- They can be matched again if needed

---

## 6. CACHE MANAGEMENT

### Cache Key Format
```
"matches_{reconciliation_id}"
```

### Cache Invalidation Flow
```
1. Match is deleted from database
2. Cache key is identified: "matches_123"
3. Cache entry is removed (if exists)
4. Next reconciliation fetch will rebuild cache
```

### Why Cache Invalidation?
- Ensures UI shows fresh data
- Prevents stale match data from being displayed
- Maintains data consistency

---

## 7. USER EXPERIENCE FLOW

### Scenario: User Deletes a Match

**Step 1: Discovery**
- User is reviewing matched transactions
- Notices an incorrect match
- Sees "Delete" button in Action column

**Step 2: Action**
- Clicks "Delete" button
- Confirmation dialog appears

**Step 3: Confirmation**
- Reads warning message
- Understands action is permanent
- Clicks "OK" to confirm

**Step 4: Processing**
- Sees "Deleting match..." status
- Waits for operation to complete

**Step 5: Result**
- Sees success message
- Row disappears from table
- Match count updates
- Status shows green success indicator

**Step 6: Next Steps**
- User can re-run reconciliation
- Transactions will appear in unmatched sections
- User can rematch if needed

---

## 8. ERROR SCENARIOS & HANDLING

### Error 1: Match Not Found
**Cause:** Match ID doesn't exist or doesn't belong to reconciliation
**Response:** 404 error with message
**User Sees:** "Error: Match ID X not found for reconciliation Y"

### Error 2: Network Error
**Cause:** Connection failure or timeout
**Response:** Exception caught, error message shown
**User Sees:** "Error deleting match. Please try again."

### Error 3: Database Error
**Cause:** Database connection issue or constraint violation
**Response:** 500 error with details
**User Sees:** "Internal server error while deleting match."

### Error 4: Permission Error
**Cause:** Rate limiting or authentication issue
**Response:** 403/429 error
**User Sees:** Appropriate error message

---

## 9. SECURITY CONSIDERATIONS

### 1. Validation
- ✅ Match ID is validated against reconciliation ID
- ✅ Prevents deletion of matches from other reconciliations
- ✅ SQL injection protection via parameterized queries

### 2. Rate Limiting
- ✅ Endpoint is rate-limited: 30 requests per minute
- ✅ Prevents abuse and DoS attacks

### 3. Transaction Safety
- ✅ Database operations are transactional
- ✅ Commit only on success
- ✅ Rollback on error

### 4. Cache Consistency
- ✅ Cache is invalidated after deletion
- ✅ Prevents stale data issues

---

## 10. TESTING SCENARIOS

### Test Case 1: Successful Deletion
```
Input: Valid reconciliation_id and match_id
Expected: Match deleted, 200 response, row removed from UI
```

### Test Case 2: Invalid Match ID
```
Input: Non-existent match_id
Expected: 404 error, error message shown
```

### Test Case 3: Match from Different Reconciliation
```
Input: Valid match_id but wrong reconciliation_id
Expected: 404 error (match not found for this reconciliation)
```

### Test Case 4: User Cancels Confirmation
```
Input: User clicks "Cancel" in confirmation dialog
Expected: No API call, no changes, function returns early
```

### Test Case 5: Network Failure
```
Input: Network error during API call
Expected: Error caught, user-friendly message shown
```

---

## 11. SUMMARY

### Key Points:

1. **Button Name:** Changed from "Unmatch" to "Delete" for clarity
2. **Icon:** Changed to trash icon (fa-trash) for better UX
3. **Confirmation:** Enhanced confirmation message explains consequences
4. **Backend:** Fully functional DELETE endpoint with proper validation
5. **Cache:** Automatic cache invalidation after deletion
6. **UI Update:** Immediate row removal and count update
7. **Error Handling:** Comprehensive error handling at all levels

### Flow Summary:
```
User Click → Confirmation → API Call → Backend Validation → 
Database Deletion → Cache Invalidation → UI Update → Success Message
```

### Important Notes:
- Deletion is **permanent** (cannot be undone)
- Transactions are **not deleted**, only the match relationship
- Re-run reconciliation to see transactions in unmatched sections
- Both automatic and manual matches can be deleted
- Match count updates automatically in UI

---

**End of Documentation**


