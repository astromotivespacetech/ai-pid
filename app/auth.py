import os
import sqlite3
from typing import Optional
from passlib.hash import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "app.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _conn()
    cur = conn.cursor()
    
    # Check if users table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cur.fetchone()
    
    if not table_exists:
        # Create new table with nullable username and password_hash
        cur.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                provider TEXT,
                provider_id TEXT,
                email TEXT,
                display_name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
    else:
        # Table exists - need to check constraints and potentially recreate
        # SQLite doesn't support ALTER COLUMN, so we need to recreate if needed
        cur.execute("PRAGMA table_info(users)")
        columns = cur.fetchall()
        # Check if username or password_hash have NOT NULL constraint (notnull == 1)
        has_constraint = any(col[1] in ('username', 'password_hash') and col[3] == 1 for col in columns)
        
        if has_constraint:
            print("[DB] Recreating users table to remove NOT NULL constraints...")
            # Backup existing data
            cur.execute("SELECT id, username, password_hash, provider, provider_id, email, display_name, created_at FROM users")
            existing_users = cur.fetchall()
            
            # Drop and recreate
            cur.execute("DROP TABLE users")
            cur.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    provider TEXT,
                    provider_id TEXT,
                    email TEXT,
                    display_name TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            
            # Restore data
            for user in existing_users:
                cur.execute(
                    "INSERT INTO users (id, username, password_hash, provider, provider_id, email, display_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    user
                )
    
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graphs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            instruction TEXT,
            nodes_json TEXT,
            edges_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    # Ensure new columns exist in users table for older DBs
    def _ensure_column(table: str, column: str, definition: str):
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    _ensure_column("users", "provider", "TEXT")
    _ensure_column("users", "provider_id", "TEXT")
    _ensure_column("users", "email", "TEXT")
    _ensure_column("users", "display_name", "TEXT")
    conn.commit()
    conn.close()


def create_user(username: str, password: str) -> Optional[int]:
    pw_hash = bcrypt.hash(password)
    now = datetime.utcnow().isoformat()
    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, pw_hash, now),
        )
        conn.commit()
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        uid = None
    conn.close()
    return uid


def get_or_create_oauth_user(provider: str, provider_id: str, email: str = None, display_name: str = None) -> Optional[int]:
    """Return existing user id for the provider/provider_id or create one."""
    now = datetime.utcnow().isoformat()
    conn = _conn()
    cur = conn.cursor()
    # Try to find existing
    cur.execute(
        "SELECT id FROM users WHERE provider = ? AND provider_id = ?",
        (provider, provider_id),
    )
    row = cur.fetchone()
    if row:
        uid = row[0]
        print(f"[Auth] Found existing user: uid={uid}")
        conn.close()
        return uid
    # Insert new - generate a username for OAuth users
    # Use email prefix or fallback to provider_providerId
    username = email.split("@")[0] if email else f"{provider}_{provider_id}"
    # Make username unique if it already exists
    base_username = username
    counter = 1
    while True:
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cur.fetchone():
            break
        username = f"{base_username}_{counter}"
        counter += 1
    
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, provider, provider_id, email, display_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, None, provider, provider_id, email, display_name, now),
        )
        conn.commit()
        uid = cur.lastrowid
        print(f"[Auth] Created new user: uid={uid}, username={username}")
    except sqlite3.IntegrityError as e:
        print(f"[Auth ERROR] IntegrityError creating user: {e}")
        uid = None
    except Exception as e:
        print(f"[Auth ERROR] Unexpected error creating user: {e}")
        uid = None
    conn.close()
    return uid


def authenticate_user(username: str, password: str) -> Optional[int]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    uid, pw_hash = row
    if bcrypt.verify(password, pw_hash):
        return uid
    return None


def get_user(user_id: int) -> Optional[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, display_name, created_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "display_name": row[3], "created_at": row[4]}


def save_graph(user_id: int, filename: str, instruction: str, nodes: list, edges: list) -> int:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO graphs (user_id, filename, instruction, nodes_json, edges_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, filename, instruction, json_dumps(nodes), json_dumps(edges), now),
    )
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return gid


def get_graphs_for_user(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, filename, instruction, nodes_json, edges_json, created_at FROM graphs WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r[0],
                "filename": r[1],
                "instruction": r[2],
                "nodes": json_loads(r[3]),
                "edges": json_loads(r[4]),
                "created_at": r[5],
            }
        )
    return result


def delete_graph(graph_id: int):
    """Delete a graph by ID."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM graphs WHERE id = ?", (graph_id,))
    conn.commit()
    conn.close()


# lightweight json helpers to avoid importing json in many places
import json


def json_dumps(v):
    try:
        return json.dumps(v)
    except Exception:
        return json.dumps(str(v))


def json_loads(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None
