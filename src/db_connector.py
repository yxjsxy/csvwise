#!/usr/bin/env python3
"""
Database Connector for csvwise
支持 SQLite 和 PostgreSQL 数据源
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# PostgreSQL support (optional)
try:
    import psycopg2
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


class DatabaseConnector:
    """统一的数据库连接器，支持 SQLite 和 PostgreSQL"""
    
    def __init__(self, connection_string: str):
        """
        初始化数据库连接
        
        Args:
            connection_string: 数据库连接字符串
                - SQLite: "sqlite:///path/to/db.sqlite" 或直接 "/path/to/db.sqlite"
                - PostgreSQL: "postgresql://user:pass@host:port/dbname"
        """
        self.connection_string = connection_string
        self.db_type = self._detect_db_type(connection_string)
        self.conn = None
        
    def _detect_db_type(self, conn_str: str) -> str:
        """检测数据库类型"""
        if conn_str.startswith("postgresql://") or conn_str.startswith("postgres://"):
            return "postgresql"
        elif conn_str.startswith("sqlite:///"):
            return "sqlite"
        elif conn_str.endswith((".db", ".sqlite", ".sqlite3")):
            return "sqlite"
        else:
            # 默认尝试 SQLite
            return "sqlite"
    
    def connect(self):
        """建立数据库连接"""
        if self.db_type == "sqlite":
            path = self.connection_string
            if path.startswith("sqlite:///"):
                path = path[10:]
            if not os.path.exists(path):
                raise FileNotFoundError(f"SQLite 数据库不存在: {path}")
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            
        elif self.db_type == "postgresql":
            if not HAS_POSTGRES:
                raise ImportError("需要安装 psycopg2: pip install psycopg2-binary")
            self.conn = psycopg2.connect(self.connection_string)
            
        return self
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def list_tables(self) -> List[str]:
        """列出所有表"""
        cursor = self.conn.cursor()
        
        if self.db_type == "sqlite":
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        elif self.db_type == "postgresql":
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, str]]:
        """获取表结构"""
        cursor = self.conn.cursor()
        
        if self.db_type == "sqlite":
            cursor.execute(f"PRAGMA table_info('{table_name}')")
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "name": row[1],
                    "type": row[2],
                    "nullable": not row[3],
                    "default": row[4],
                    "pk": bool(row[5])
                })
                
        elif self.db_type == "postgresql":
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": row[3],
                    "pk": False  # 需要额外查询
                })
        
        cursor.close()
        return columns
    
    def get_table_row_count(self, table_name: str) -> int:
        """获取表行数"""
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    
    def query_table(
        self, 
        table_name: str, 
        limit: int = 1000,
        offset: int = 0,
        columns: Optional[List[str]] = None
    ) -> Tuple[List[str], List[Tuple]]:
        """
        查询表数据
        
        Returns:
            (headers, rows) - 列名列表和数据行
        """
        cursor = self.conn.cursor()
        
        col_str = ", ".join(columns) if columns else "*"
        
        if self.db_type == "sqlite":
            cursor.execute(f"SELECT {col_str} FROM {table_name} LIMIT ? OFFSET ?", (limit, offset))
        elif self.db_type == "postgresql":
            cursor.execute(f"SELECT {col_str} FROM {table_name} LIMIT %s OFFSET %s", (limit, offset))
        
        # 获取列名
        if self.db_type == "sqlite":
            headers = [desc[0] for desc in cursor.description]
        else:
            headers = [desc[0] for desc in cursor.description]
        
        rows = cursor.fetchall()
        cursor.close()
        
        # 转换为元组列表
        rows = [tuple(row) for row in rows]
        
        return headers, rows
    
    def execute_query(self, sql: str, params: tuple = ()) -> Tuple[List[str], List[Tuple]]:
        """
        执行自定义 SQL 查询
        
        Returns:
            (headers, rows)
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        
        if cursor.description:
            headers = [desc[0] for desc in cursor.description]
            rows = [tuple(row) for row in cursor.fetchall()]
        else:
            headers = []
            rows = []
        
        cursor.close()
        return headers, rows
    
    def table_to_csv_string(self, table_name: str, limit: int = 1000) -> str:
        """将表数据转换为 CSV 字符串（用于兼容 csvwise）"""
        import io
        import csv
        
        headers, rows = self.query_table(table_name, limit=limit)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        
        return output.getvalue()


def get_db_info(connection_string: str) -> Dict[str, Any]:
    """获取数据库概览信息"""
    with DatabaseConnector(connection_string) as db:
        tables = db.list_tables()
        info = {
            "type": db.db_type,
            "tables": {},
            "total_tables": len(tables)
        }
        
        for table in tables:
            schema = db.get_table_schema(table)
            row_count = db.get_table_row_count(table)
            info["tables"][table] = {
                "columns": schema,
                "row_count": row_count
            }
        
        return info


if __name__ == "__main__":
    # 测试
    import sys
    if len(sys.argv) > 1:
        conn_str = sys.argv[1]
        info = get_db_info(conn_str)
        print(f"数据库类型: {info['type']}")
        print(f"表数量: {info['total_tables']}")
        for table, details in info["tables"].items():
            print(f"\n📊 {table} ({details['row_count']} 行)")
            for col in details["columns"]:
                print(f"  - {col['name']}: {col['type']}")
