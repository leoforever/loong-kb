"""
Database models and initialization
Includes: users, roles, kb_configs, user_roles, kb_roles
"""
import sqlite3
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'cache', 'db.sqlite')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db_conn():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize all tables"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db_conn() as conn:
        c = conn.cursor()

        # Roles table
        c.execute('''
            CREATE TABLE IF NOT EXISTS roles (
                role_id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # User <-> Role mapping
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
                UNIQUE(user_id, role_id)
            )
        ''')

        # Knowledge base configs (points to external Dify API)
        c.execute('''
            CREATE TABLE IF NOT EXISTS kb_configs (
                kb_id INTEGER PRIMARY KEY AUTOINCREMENT,
                kb_name TEXT NOT NULL,
                description TEXT,
                dify_api_url TEXT NOT NULL,
                dify_api_key TEXT NOT NULL,
                dify_dataset_id TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Role <-> KB permissions (which roles can access which KBs)
        # can_access: 可查看文件列表（不能上传/删除文档）
        # can_edit: 可上传/删除文档（包含 can_access，但不能编辑/删除知识库）
        # can_manage: 可修改知识库配置（名称/描述），不可修改 ID（包含 can_edit 和 can_access）
        # admin 角色默认拥有所有权限，且不可被修改
        c.execute('''
            CREATE TABLE IF NOT EXISTS role_kb_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                kb_id INTEGER NOT NULL,
                can_access INTEGER DEFAULT 0,
                can_edit INTEGER DEFAULT 0,
                can_manage INTEGER DEFAULT 0,
                FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
                FOREIGN KEY (kb_id) REFERENCES kb_configs(kb_id) ON DELETE CASCADE,
                UNIQUE(role_id, kb_id)
            )
        ''')

        # Query history
        c.execute('''
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kb_id INTEGER,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                hit_cache INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (kb_id) REFERENCES kb_configs(kb_id) ON DELETE SET NULL
            )
        ''')

        c.execute('CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_role_kb_role ON role_kb_permissions(role_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_query_log_user ON query_log(user_id)')

        # Insert default roles if not exist
        default_roles = [
            ('admin', '管理员，可管理所有知识库'),
            ('developer', '开发人员，可访问开发相关知识库'),
            ('viewer', '普通用户，只读访问知识库'),
        ]
        for name, desc in default_roles:
            c.execute('INSERT OR IGNORE INTO roles (role_name, description) VALUES (?, ?)', (name, desc))

    logger.info(f"Database initialized: {DB_PATH}")


# ==============================
# User operations
# ==============================

def create_user(username, password_hash, display_name=None):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
            (username, password_hash, display_name or username)
        )
        return c.lastrowid


def get_user_by_username(username):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        return c.fetchone()


def _row(row):
    """Convert sqlite3.Row to dict (sqlite3.Row doesn't support .get())"""
    return dict(row)


def get_user_by_id(user_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return c.fetchone()


def get_all_users():
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT u.*, GROUP_CONCAT(r.role_name) as roles
            FROM users u
            LEFT JOIN user_roles ur ON u.user_id = ur.user_id
            LEFT JOIN roles r ON ur.role_id = r.role_id
            GROUP BY u.user_id
        ''')
        return c.fetchall()


def get_user_roles(user_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT r.* FROM roles r
            JOIN user_roles ur ON r.role_id = ur.role_id
            WHERE ur.user_id = ?
        ''', (user_id,))
        return [row['role_name'] for row in c.fetchall()]


# ==============================
# Role operations
# ==============================

def get_all_roles():
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM roles ORDER BY role_id')
        return c.fetchall()


def get_role_by_name(name):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM roles WHERE role_name = ?', (name,))
        return c.fetchone()


def assign_role_to_user(user_id, role_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)', (user_id, role_id))


def remove_user_role(user_id, role_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM user_roles WHERE user_id = ? AND role_id = ?', (user_id, role_id))


# ==============================
# KB config operations
# ==============================

def create_kb(name, description, dify_api_url, dify_api_key, dify_dataset_id, template_type=None):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO kb_configs (kb_name, description, dify_api_url, dify_api_key, dify_dataset_id, template_type)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, description, dify_api_url, dify_api_key, dify_dataset_id, template_type))
        return c.lastrowid


def get_all_kbs():
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM kb_configs ORDER BY kb_id')
        return [_row(r) for r in c.fetchall()]


def get_kb_by_id(kb_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM kb_configs WHERE kb_id = ?', (kb_id,))
        return c.fetchone()


def update_kb(kb_id, name, description, dify_api_url, dify_api_key, dify_dataset_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE kb_configs
            SET kb_name=?, description=?, dify_api_url=?, dify_api_key=?, dify_dataset_id=?
            WHERE kb_id=?
        ''', (name, description, dify_api_url, dify_api_key, dify_dataset_id, kb_id))


def delete_kb(kb_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM role_kb_permissions WHERE kb_id = ?', (kb_id,))
        c.execute('DELETE FROM kb_configs WHERE kb_id = ?', (kb_id,))


# ==============================
# KB permission operations
# ==============================

def set_kb_role_permission(role_id, kb_id, can_access=0, can_edit=0, can_manage=0):
    """设置角色对知识库的权限。上级权限自动包含下级权限：manage → edit → access"""
    # Enforce inheritance: manage → edit → access
    if can_manage:
        can_edit = 1
        can_access = 1
    elif can_edit:
        can_access = 1
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO role_kb_permissions (role_id, kb_id, can_access, can_edit, can_manage)
            VALUES (?, ?, ?, ?, ?)
        ''', (role_id, kb_id, can_access, can_edit, can_manage))


def remove_kb_role_permission(role_id, kb_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM role_kb_permissions WHERE role_id = ? AND kb_id = ?', (role_id, kb_id))


def get_kb_permissions_for_roles(role_ids):
    """Return dict of kb_id -> {can_access, can_edit, can_manage} for given role_ids"""
    if not role_ids:
        return {}
    with get_db_conn() as conn:
        c = conn.cursor()
        placeholders = ','.join(['?'] * len(role_ids))
        c.execute(f'''
            SELECT kb_id, MAX(can_access) as can_access, MAX(can_edit) as can_edit, MAX(can_manage) as can_manage
            FROM role_kb_permissions
            WHERE role_id IN ({placeholders})
            GROUP BY kb_id
        ''', role_ids)
        return {row['kb_id']: {'can_access': row['can_access'], 'can_edit': row['can_edit'], 'can_manage': row['can_manage']}
                for row in c.fetchall()}


def get_role_kb_permissions(role_id):
    """Get all KB permissions for a specific role"""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT rkp.*, kc.kb_name, kc.dify_dataset_id
            FROM role_kb_permissions rkp
            JOIN kb_configs kc ON rkp.kb_id = kc.kb_id
            WHERE rkp.role_id = ?
        ''', (role_id,))
        return c.fetchall()


def get_all_role_kb_permissions():
    """Get all role-KB permission mappings for admin view"""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT rkp.*, kc.kb_name, r.role_name
            FROM role_kb_permissions rkp
            JOIN kb_configs kc ON rkp.kb_id = kc.kb_id
            JOIN roles r ON rkp.role_id = r.role_id
        ''')
        return c.fetchall()


# ==============================
# Query log
# ==============================

def save_query_log(user_id, kb_id, question, answer, hit_cache=0):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO query_log (user_id, kb_id, question, answer, hit_cache)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, kb_id, question, answer, hit_cache))


def get_user_history(user_id, limit=50):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT ql.*, kc.kb_name
            FROM query_log ql
            LEFT JOIN kb_configs kc ON ql.kb_id = kc.kb_id
            WHERE ql.user_id = ?
            ORDER BY ql.created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        return c.fetchall()


def delete_user_history(user_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM query_log WHERE user_id = ?', (user_id,))