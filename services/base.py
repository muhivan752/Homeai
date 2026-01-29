# ===============================
# services/base.py - Base Service Class (PRODUCTION)
# ===============================
# Thread-safe database operations with proper connection lifecycle

import sqlite3
from typing import Any, Optional, Union
from contextlib import contextmanager


class BaseService:
    """
    Base class untuk semua service.
    
    Provides:
    - Thread-safe database connections
    - Automatic row_factory for dict results
    - Proper error handling & rollback
    - Context manager for transactions
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    @contextmanager
    def _get_conn(self):
        """
        Context manager untuk database connection.
        Ensures connection is always closed.
        """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def run_query(
        self, 
        query: str, 
        args: tuple = (), 
        one: bool = False, 
        commit: bool = False
    ) -> Optional[Union[dict, list, int]]:
        """
        Execute a database query with proper error handling.
        
        Args:
            query: SQL query string
            args: Query parameters (tuple)
            one: Return single result if True
            commit: Commit transaction if True (for INSERT/UPDATE/DELETE)
        
        Returns:
            - SELECT: list of dicts, or single dict if one=True, or None if not found
            - INSERT: lastrowid
            - UPDATE/DELETE: rowcount
            - On error: None
        
        Usage:
            # SELECT multiple
            users = self.run_query("SELECT * FROM users WHERE role=?", ("admin",))
            
            # SELECT one
            user = self.run_query("SELECT * FROM users WHERE id=?", (1,), one=True)
            
            # INSERT
            new_id = self.run_query(
                "INSERT INTO users (name, email) VALUES (?, ?)", 
                ("John", "john@example.com"), 
                commit=True
            )
            
            # UPDATE/DELETE
            affected = self.run_query(
                "UPDATE users SET name=? WHERE id=?",
                ("Jane", 1),
                commit=True
            )
        """
        try:
            with self._get_conn() as conn:
                cur = conn.execute(query, args)
                
                if commit:
                    conn.commit()
                    # For INSERT, return lastrowid
                    # For UPDATE/DELETE, return rowcount
                    return cur.lastrowid if cur.lastrowid else cur.rowcount
                else:
                    rows = cur.fetchall()
                    if one:
                        return dict(rows[0]) if rows else None
                    return [dict(r) for r in rows]
                    
        except sqlite3.Error as e:
            print(f"[DB ERROR] {e} | Query: {query[:100]}...")
            return None
        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")
            return None
    
    def run_query_many(
        self, 
        query: str, 
        args_list: list[tuple], 
        commit: bool = True
    ) -> Optional[int]:
        """
        Execute same query with multiple parameter sets.
        Useful for bulk inserts.
        
        Returns: Number of rows affected, or None on error
        """
        try:
            with self._get_conn() as conn:
                cur = conn.executemany(query, args_list)
                if commit:
                    conn.commit()
                return cur.rowcount
        except sqlite3.Error as e:
            print(f"[DB ERROR] {e} | Query: {query[:100]}...")
            return None
    
    def exists(self, table: str, column: str, value: Any) -> bool:
        """
        Check if a record exists.
        
        Usage:
            if self.exists("users", "email", "john@example.com"):
                return "Email already registered"
        """
        result = self.run_query(
            f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1",
            (value,),
            one=True
        )
        return result is not None
