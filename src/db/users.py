"""User authentication database module.

Handles user registration, authentication, and management.
Uses a separate SQLite database from the card data.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Try to import bcrypt, fall back to hashlib if not available
try:
    import bcrypt

    BCRYPT_AVAILABLE = True
except ImportError:
    import hashlib

    BCRYPT_AVAILABLE = False


def _get_users_db_path() -> Path:
    """Get the path to the users database."""
    # Check environment variables for data directory
    data_dir = os.environ.get("BULK_DATA_DIR") or os.environ.get("PM_BULK_DATA_DIR")
    if data_dir:
        db_dir = Path(data_dir)
    else:
        # Default to project's data directory
        db_dir = Path(__file__).parent.parent.parent / "proxy-machine" / "data"

    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "users.db"


USERS_DB_PATH = _get_users_db_path()


def _get_connection() -> sqlite3.Connection:
    """Get a connection to the users database."""
    conn = sqlite3.connect(str(USERS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the users database schema."""
    conn = _get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                is_approved INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_approved ON users(is_approved);
        """
        )
        conn.commit()
    finally:
        conn.close()


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt or fallback to SHA256."""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    else:
        # Fallback: SHA256 with simple salt (less secure, but works without bcrypt)
        import secrets

        salt = secrets.token_hex(16)
        hash_value = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256:{salt}:{hash_value}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    if BCRYPT_AVAILABLE and not password_hash.startswith("sha256:"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    elif password_hash.startswith("sha256:"):
        # Fallback verification
        parts = password_hash.split(":")
        if len(parts) != 3:
            return False
        _, salt, stored_hash = parts
        computed_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        return computed_hash == stored_hash
    return False


def create_user(
    username: str, email: str, password: str, role: str = "user", auto_approve: bool = False
) -> tuple[bool, str]:
    """Create a new user account.

    Args:
        username: Unique username (will also be profile name)
        email: User's email address
        password: Plain text password (will be hashed)
        role: 'user' or 'admin'
        auto_approve: If True, user is immediately approved

    Returns:
        (success, message) tuple
    """
    # Validate username
    if not username or len(username) < 3 or len(username) > 20:
        return False, "Username must be 3-20 characters"

    if not username.replace("-", "").replace("_", "").isalnum():
        return False, "Username can only contain letters, numbers, hyphens, and underscores"

    # Validate email (basic check)
    if not email or "@" not in email or "." not in email:
        return False, "Invalid email address"

    # Validate password
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters"

    username = username.lower().strip()
    email = email.lower().strip()
    password_hash = _hash_password(password)

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_approved)
            VALUES (?, ?, ?, ?, ?)
        """,
            (username, email, password_hash, role, 1 if auto_approve else 0),
        )
        conn.commit()
        return True, "Account created successfully"
    except sqlite3.IntegrityError as e:
        if "username" in str(e).lower():
            return False, "Username already taken"
        elif "email" in str(e).lower():
            return False, "Email already registered"
        return False, f"Registration failed: {e}"
    finally:
        conn.close()


def verify_user(username: str, password: str) -> tuple[bool, Optional[dict], str]:
    """Verify user credentials.

    Args:
        username: Username or email
        password: Plain text password

    Returns:
        (success, user_dict, message) tuple
    """
    conn = _get_connection()
    try:
        # Allow login with username or email
        cur = conn.execute(
            """
            SELECT id, username, email, password_hash, role, is_approved, last_login
            FROM users
            WHERE username = ? OR email = ?
        """,
            (username.lower(), username.lower()),
        )
        row = cur.fetchone()

        if not row:
            return False, None, "Invalid username or password"

        if not _verify_password(password, row["password_hash"]):
            return False, None, "Invalid username or password"

        if not row["is_approved"]:
            return False, None, "Account pending approval"

        # Update last login
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()

        user = {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "is_admin": row["role"] == "admin",
        }
        return True, user, "Login successful"
    finally:
        conn.close()


def get_user(username: str) -> Optional[dict]:
    """Get user by username."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, username, email, role, is_approved, created_at, last_login
            FROM users WHERE username = ?
        """,
            (username.lower(),),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, username, email, role, is_approved, created_at, last_login
            FROM users WHERE id = ?
        """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def list_users() -> list[dict]:
    """List all users."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, username, email, role, is_approved, created_at, last_login
            FROM users ORDER BY created_at DESC
        """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def list_pending_users() -> list[dict]:
    """List users pending approval."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, username, email, role, created_at
            FROM users WHERE is_approved = 0 ORDER BY created_at ASC
        """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def approve_user(username: str) -> tuple[bool, str]:
    """Approve a pending user account."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "UPDATE users SET is_approved = 1 WHERE username = ? AND is_approved = 0",
            (username.lower(),),
        )
        conn.commit()
        if cur.rowcount > 0:
            return True, f"User '{username}' approved"
        return False, "User not found or already approved"
    finally:
        conn.close()


def delete_user(username: str) -> tuple[bool, str]:
    """Delete a user account."""
    conn = _get_connection()
    try:
        cur = conn.execute("DELETE FROM users WHERE username = ?", (username.lower(),))
        conn.commit()
        if cur.rowcount > 0:
            return True, f"User '{username}' deleted"
        return False, "User not found"
    finally:
        conn.close()


def set_user_role(username: str, role: str) -> tuple[bool, str]:
    """Set user role (admin/user)."""
    if role not in ("admin", "user"):
        return False, "Invalid role"

    conn = _get_connection()
    try:
        cur = conn.execute(
            "UPDATE users SET role = ? WHERE username = ?", (role, username.lower())
        )
        conn.commit()
        if cur.rowcount > 0:
            return True, f"User '{username}' role set to '{role}'"
        return False, "User not found"
    finally:
        conn.close()


def user_count() -> int:
    """Get total number of users."""
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]
    finally:
        conn.close()


def pending_count() -> int:
    """Get number of pending users."""
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM users WHERE is_approved = 0")
        return cur.fetchone()[0]
    finally:
        conn.close()


# Initialize database on module import
init_db()
