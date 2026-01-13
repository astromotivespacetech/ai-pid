import os
import sqlite3
from typing import Optional
from passlib.hash import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "app.db")

# Admin email addresses - update this list with admin email(s)
ADMIN_EMAILS = [
    "lawrencemsheets@gmail.com"
]


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def is_admin(email: Optional[str]) -> bool:
    """Check if an email is in the admin list."""
    if not email:
        return False
    return email.lower() in [e.lower() for e in ADMIN_EMAILS]


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
    
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            graph_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            instruction TEXT,
            nodes_json TEXT,
            edges_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(graph_id) REFERENCES graphs(id) ON DELETE CASCADE
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
    """Create a new graph and save initial state as version 1"""
    now = datetime.utcnow().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO graphs (user_id, filename, instruction, nodes_json, edges_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, filename, instruction, json_dumps(nodes), json_dumps(edges), now),
    )
    gid = cur.lastrowid
    
    # Create version 1 with the initial state
    cur.execute(
        "INSERT INTO graph_versions (graph_id, version_number, instruction, nodes_json, edges_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (gid, 1, instruction, json_dumps(nodes), json_dumps(edges), now)
    )
    
    conn.commit()
    conn.close()
    return gid


def update_graph(graph_id: int, user_id: int, filename: str, instruction: str, nodes: list, edges: list) -> int:
    """Update an existing graph, verifying ownership and creating a version snapshot of the NEW state"""
    conn = _conn()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT user_id FROM graphs WHERE id = ?", (graph_id,))
    row = cur.fetchone()
    if not row or row[0] != user_id:
        conn.close()
        raise ValueError(f"Graph {graph_id} not found or access denied")
    
    # Get the next version number
    cur.execute("SELECT MAX(version_number) FROM graph_versions WHERE graph_id = ?", (graph_id,))
    max_version = cur.fetchone()[0]
    next_version = (max_version or 0) + 1
    
    # Update the graph with new data FIRST
    cur.execute(
        "UPDATE graphs SET filename = ?, instruction = ?, nodes_json = ?, edges_json = ? WHERE id = ?",
        (filename, instruction, json_dumps(nodes), json_dumps(edges), graph_id),
    )
    
    # THEN save the new state as a version snapshot
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO graph_versions (graph_id, version_number, instruction, nodes_json, edges_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, next_version, instruction, json_dumps(nodes), json_dumps(edges), now)
    )
    
    conn.commit()
    conn.close()
    return graph_id


def get_graphs_for_user(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT g.id, g.filename, g.instruction, g.nodes_json, g.edges_json, g.created_at,
           (SELECT COUNT(*) FROM graph_versions WHERE graph_id = g.id) as version_count
           FROM graphs g WHERE g.user_id = ? ORDER BY g.id DESC""",
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
                "version_count": r[6],
            }
        )
    return result


def get_graph_versions(graph_id: int, user_id: int):
    """Get all versions for a graph, verifying user ownership"""
    conn = _conn()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT user_id FROM graphs WHERE id = ?", (graph_id,))
    row = cur.fetchone()
    if not row or row[0] != user_id:
        conn.close()
        return []
    
    # Get all versions
    cur.execute(
        "SELECT id, version_number, instruction, nodes_json, edges_json, created_at FROM graph_versions WHERE graph_id = ? ORDER BY version_number DESC",
        (graph_id,),
    )
    rows = cur.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "version_number": r[1],
            "instruction": r[2],
            "nodes": json_loads(r[3]),
            "edges": json_loads(r[4]),
            "created_at": r[5],
        })
    return result


def restore_graph_version(graph_id: int, version_number: int, user_id: int) -> bool:
    """Restore a graph to a specific version (discards current unsaved changes)"""
    conn = _conn()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT user_id FROM graphs WHERE id = ?", (graph_id,))
    row = cur.fetchone()
    if not row or row[0] != user_id:
        conn.close()
        return False
    
    # Get the version data
    cur.execute(
        "SELECT instruction, nodes_json, edges_json FROM graph_versions WHERE graph_id = ? AND version_number = ?",
        (graph_id, version_number)
    )
    version_row = cur.fetchone()
    if not version_row:
        print(f"[restore_graph_version] Version {version_number} not found for graph {graph_id}")
        conn.close()
        return False
    
    print(f"[restore_graph_version] Restoring graph {graph_id} to version {version_number}")
    print(f"[restore_graph_version] Nodes: {version_row[1][:100]}...")
    
    # Restore the complete version snapshot including instruction/description
    # Each version has its own description that was captured when it was created
    cur.execute(
        "UPDATE graphs SET instruction = ?, nodes_json = ?, edges_json = ? WHERE id = ?",
        (version_row[0], version_row[1], version_row[2], graph_id)
    )
    
    affected_rows = cur.rowcount
    print(f"[restore_graph_version] Updated {affected_rows} row(s)")
    
    conn.commit()
    conn.close()
    return True


def update_graph_description(graph_id: int, user_id: int, description: str) -> bool:
    """Update only the description/instruction field of a graph"""
    conn = _conn()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT user_id FROM graphs WHERE id = ?", (graph_id,))
    row = cur.fetchone()
    if not row or row[0] != user_id:
        conn.close()
        return False
    
    # Update description
    cur.execute(
        "UPDATE graphs SET instruction = ? WHERE id = ?",
        (description, graph_id)
    )
    
    conn.commit()
    conn.close()
    return True


def update_version_description(graph_id: int, version_number: int, user_id: int, description: str) -> bool:
    """Update the description of a specific version snapshot"""
    conn = _conn()
    cur = conn.cursor()
    
    # Verify ownership via graphs table
    cur.execute("SELECT user_id FROM graphs WHERE id = ?", (graph_id,))
    row = cur.fetchone()
    if not row or row[0] != user_id:
        conn.close()
        return False
    
    # Update the version's description
    cur.execute(
        "UPDATE graph_versions SET instruction = ? WHERE graph_id = ? AND version_number = ?",
        (description, graph_id, version_number)
    )
    
    if cur.rowcount == 0:
        conn.close()
        return False
    
    conn.commit()
    conn.close()
    return True


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
