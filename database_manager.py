"""
Database Manager - MySQL/SQLite Abstraction Layer
Handles database connections and operations for both MySQL and SQLite
"""

import os
import sqlite3
import pymysql
import logging
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager
from config import DB_TYPE, MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, MYSQL_PORT, DB_PATH

logger = logging.getLogger(__name__)


class _CompatCursor:
    def __init__(self, cursor, db_type: str):
        self._cursor = cursor
        self._db_type = db_type

    def _normalize_query(self, query: str) -> str:
        if self._db_type == "mysql":
            # Only replace ? placeholders that are actual parameter placeholders, not % in JSON strings
            # This is a simple approach - replace ? with %s only for SQL parameter placeholders
            return query.replace("?", "%s")
        return query

    def execute(self, query: str, params: Optional[Tuple] = None):
        query = self._normalize_query(query)
        if params is not None:
            self._cursor.execute(query, params)
        else:
            self._cursor.execute(query)
        return self

    def executemany(self, query: str, param_seq):
        query = self._normalize_query(query)
        self._cursor.executemany(query, param_seq)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        return self._cursor.close()


class _CompatConnection:
    def __init__(self, conn, db_type: str):
        self._conn = conn
        self._db_type = db_type

    def cursor(self):
        return _CompatCursor(self._conn.cursor(), self._db_type)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

class DatabaseManager:
    """Database abstraction layer for MySQL and SQLite"""
    
    def __init__(self):
        self.db_type = DB_TYPE
        if self.db_type != "mysql":
            raise RuntimeError("SQLite is not supported in this setup. Set DB_TYPE=mysql in .env")
        self.connection_params = self._get_connection_params()
    
    def _get_connection_params(self) -> Dict[str, Any]:
        """Get connection parameters based on database type"""
        if self.db_type == "mysql":
            return {
                'host': MYSQL_HOST,
                'user': MYSQL_USER,
                'password': MYSQL_PASSWORD,
                'database': MYSQL_DATABASE,
                'port': MYSQL_PORT,
                'charset': 'utf8mb4',
                'autocommit': True
            }
        else:
            return {
                'database': DB_PATH
            }
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            if self.db_type == "mysql":
                conn = pymysql.connect(
                    **self.connection_params,
                    cursorclass=pymysql.cursors.DictCursor,
                )
                conn = _CompatConnection(conn, self.db_type)
            else:
                conn = sqlite3.connect(self.connection_params['database'])
                conn.row_factory = sqlite3.Row  # Enable dict-like access
            
            yield conn
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.db_type == "mysql":
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                rows = cursor.fetchall()
                if rows and isinstance(rows[0], dict):
                    results = list(rows)
                else:
                    # Get column names
                    columns = [desc[0] for desc in cursor.description]
                    results = [dict(zip(columns, row)) for row in rows]
            else:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                results = [dict(row) for row in cursor.fetchall()]
            
            return results
    
    def execute_update(self, query: str, params: Optional[Tuple] = None) -> int:
        """Execute INSERT, UPDATE, DELETE queries and return affected rows"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            conn.commit()
            return cursor.rowcount
    
    def execute_insert(self, query: str, params: Optional[Tuple] = None) -> int:
        """Execute INSERT query and return last inserted ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            conn.commit()
            
            if self.db_type == "mysql":
                return cursor.lastrowid
            else:
                return cursor.lastrowid
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists"""
        if self.db_type == "mysql":
            query = """
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            """
            result = self.execute_query(query, (MYSQL_DATABASE, table_name))
        else:
            query = """
                SELECT COUNT(*) as count 
                FROM sqlite_master 
                WHERE type='table' AND name=?
            """
            result = self.execute_query(query, (table_name,))
        
        return result[0]['count'] > 0
    
    def create_database_if_not_exists(self):
        """Create database if it doesn't exist (MySQL only)"""
        if self.db_type == "mysql":
            try:
                # Connect without specifying database
                temp_params = self.connection_params.copy()
                temp_params.pop('database', None)
                
                with pymysql.connect(**temp_params) as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    conn.commit()
                    logger.info(f"Database '{MYSQL_DATABASE}' created or already exists")
            except Exception as e:
                logger.error(f"Error creating database: {e}")
                raise

# Global database manager instance
db_manager = DatabaseManager()

# Convenience functions for backward compatibility
def get_db_connection():
    """Get database connection (for backward compatibility)"""
    return db_manager.get_connection()

def execute_query(query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """Execute query with database manager"""
    return db_manager.execute_query(query, params)

def execute_update(query: str, params: Optional[Tuple] = None) -> int:
    """Execute update with database manager"""
    return db_manager.execute_update(query, params)

def execute_insert(query: str, params: Optional[Tuple] = None) -> int:
    """Execute insert with database manager"""
    return db_manager.execute_insert(query, params)
