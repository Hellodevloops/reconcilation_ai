"""
Database Query Optimization
Adds indexes and optimizes database queries
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def add_database_indexes(db_path: str):
    """
    Add database indexes for common queries to improve performance
    
    Args:
        db_path: Path to SQLite database file
    """
    indexes = [
        # Transactions table indexes
        "CREATE INDEX IF NOT EXISTS idx_transactions_source ON transactions(source)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_reconciliation_id ON transactions(reconciliation_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_amount ON transactions(amount)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_vendor ON transactions(vendor)",
        
        # Matches table indexes
        "CREATE INDEX IF NOT EXISTS idx_matches_reconciliation_id ON matches(reconciliation_id)",
        "CREATE INDEX IF NOT EXISTS idx_matches_invoice_tx_id ON matches(invoice_tx_id)",
        "CREATE INDEX IF NOT EXISTS idx_matches_bank_tx_id ON matches(bank_tx_id)",
        "CREATE INDEX IF NOT EXISTS idx_matches_confidence ON matches(confidence)",
        "CREATE INDEX IF NOT EXISTS idx_matches_created_at ON matches(created_at)",
        
        # Reconciliations table indexes
        "CREATE INDEX IF NOT EXISTS idx_reconciliations_created_at ON reconciliations(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_reconciliations_status ON reconciliations(status)",
        
        # Composite indexes for common query patterns
        "CREATE INDEX IF NOT EXISTS idx_transactions_recon_source ON transactions(reconciliation_id, source)",
        "CREATE INDEX IF NOT EXISTS idx_matches_recon_confidence ON matches(reconciliation_id, confidence)",
    ]
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
                logger.info(f"Created index: {index_sql}")
            except sqlite3.Error as e:
                logger.warning(f"Failed to create index: {e}")
        
        conn.commit()
        conn.close()
        
        logger.info("Database indexes created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating database indexes: {e}")
        return False


def analyze_slow_queries(db_path: str):
    """
    Analyze database for slow queries (SQLite doesn't have EXPLAIN ANALYZE,
    but we can check for missing indexes)
    
    Args:
        db_path: Path to SQLite database file
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        # Get all indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"Database has {len(tables)} tables and {len(indexes)} indexes")
        
        conn.close()
        return {"tables": len(tables), "indexes": len(indexes)}
    except Exception as e:
        logger.error(f"Error analyzing database: {e}")
        return None


def optimize_database(db_path: str):
    """
    Run database optimization (VACUUM, ANALYZE)
    
    Args:
        db_path: Path to SQLite database file
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # VACUUM to reclaim space and optimize
        cursor.execute("VACUUM")
        logger.info("Database vacuumed")
        
        # ANALYZE to update query planner statistics
        cursor.execute("ANALYZE")
        logger.info("Database analyzed")
        
        conn.close()
        logger.info("Database optimization completed")
        return True
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return False

