"""
Admin routes - manage users, roles, KB configs, permissions
"""
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, session, flash
import bcrypt
import logging

bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


def require_admin(user_id):
    """Check if user has admin role"""
    from app.models import get_user_roles as _gur
    return 'admin' in _gur(user_id)


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id') or not require_admin(session['user_id']):
            return '需要管理员权限', 403
        return f(*args, **kwargs)
    return decorated


# ==================== User Management ====================

@bp.route('/admin/users')
@admin_required
def users():
    from app.models import get_all_users, get_all_roles
    users = get_all_users()
    roles = get_all_roles()
    return render_template('admin_users.html', users=users, roles=roles)


@bp.route('/admin/users', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    display_name = request.form.get('display_name', '').strip()
    role_ids = request.form.getlist('role_ids')

    if not username or not password:
        flash('用户名和密码不能为空', 'error')
        return redirect(url_for('admin.users'))

    from app.models import get_user_by_username, create_user as mk_user
    if get_user_by_username(username):
        flash('用户名已存在', 'error')
        return redirect(url_for('admin.users'))

    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user_id = mk_user(username, pwd_hash, display_name or username)

    from app.models import get_db_conn
    with get_db_conn() as conn:
        c = conn.cursor()
        for rid in role_ids:
            c.execute('INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)',
                      (user_id, int(rid)))

    flash(f'用户 {username} 创建成功', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/admin/users/<username>/roles', methods=['POST'])
@admin_required
def update_user_roles(username):
    role_names = request.form.getlist('role_ids')
    from app.models import get_db_conn, get_user_by_name

    user = get_user_by_name(username)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('admin.users'))

    # Update users.roles column directly (stores comma-separated role names)
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('UPDATE users SET roles = ? WHERE user_id = ?',
                  (','.join(role_names), user['user_id']))

    flash('角色分配已更新', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    from app.models import get_db_conn
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM user_roles WHERE user_id = ?', (user_id,))
        c.execute('DELETE FROM query_log WHERE user_id = ?', (user_id,))
        c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    flash('用户已删除', 'success')
    return redirect(url_for('admin.users'))


# ==================== Role Management ====================

@bp.route('/admin/roles')
@admin_required
def roles():
    from app.models import get_all_roles, get_all_role_kb_permissions, get_all_kbs, get_all_users
    roles = get_all_roles()
    perms = get_all_role_kb_permissions()
    kbs = get_all_kbs()
    # Build user count per role_id
    users = get_all_users()
    role_user_count = {}
    for u in users:
        roles_str = u['roles'] if 'roles' in u.keys() else None
        if roles_str:
            for r in roles_str.split(','):
                r = r.strip()
                if r:
                    from app.models import get_role_by_name
                    role = get_role_by_name(r)
                    if role:
                        role_user_count[role['role_id']] = role_user_count.get(role['role_id'], 0) + 1
    return render_template('admin_roles.html', roles=roles, kbs=kbs, perms=perms, role_user_count=role_user_count)


@bp.route('/admin/roles', methods=['POST'])
@admin_required
def create_role():
    role_name = request.form.get('role_name', '').strip()
    description = request.form.get('description', '').strip()
    if not role_name:
        flash('角色名不能为空', 'error')
        return redirect(url_for('admin.roles'))
    from app.models import get_db_conn
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO roles (role_name, description) VALUES (?, ?)',
                  (role_name, description))
    flash(f'角色 {role_name} 创建成功', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
@admin_required
def delete_role(role_id):
    from app.models import get_db_conn
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM user_roles WHERE role_id = ?', (role_id,))
        c.execute('DELETE FROM role_kb_permissions WHERE role_id = ?', (role_id,))
        c.execute('DELETE FROM roles WHERE role_id = ?', (role_id,))
    flash('角色已删除', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/admin/roles/<int:role_id>/permissions', methods=['GET'])
@admin_required
def get_role_permissions(role_id):
    from app.models import get_role_kb_permissions
    perms = get_role_kb_permissions(role_id)
    return jsonify([{'kb_id': p['kb_id'], 'can_read': p['can_read'], 'can_query': p['can_query']} for p in perms])


# ==================== KB Management ====================

@bp.route('/admin/kbs')
@admin_required
def kbs():
    from app.models import get_all_kbs, get_all_roles, get_all_role_kb_permissions
    from app.config import get_dify_defaults
    kbs = get_all_kbs()
    roles = get_all_roles()
    perms = get_all_role_kb_permissions()
    dify_defaults = get_dify_defaults()
    edit_kb_id = request.args.get('edit', type=int)
    return render_template('admin_kbs.html', kbs=kbs, roles=roles, perms=perms, dify_defaults=dify_defaults, edit_kb_id=edit_kb_id)


@bp.route('/admin/kbs/sync', methods=['POST'])
@admin_required
def sync_kbs():
    """Sync KBs from Dify API to local DB"""
    from app.services.dify_sync import sync_kbs_from_dify
    created, deleted, errors = sync_kbs_from_dify()
    if errors:
        flash(f'同步完成：新增 {created} 个，删除 {deleted} 个。错误：{"; ".join(errors[:3])}', 'error')
    else:
        flash(f'同步完成：新增 {created} 个知识库，删除 {deleted} 个无效知识库。', 'success')
    return redirect(url_for('admin.kbs'))


@bp.route('/admin/kbs', methods=['POST'])
@admin_required
def create_kb():
    kb_name = request.form.get('kb_name', '').strip()
    description = request.form.get('description', '').strip()
    dify_dataset_id = request.form.get('dify_dataset_id', '').strip()

    if not all([kb_name, dify_dataset_id]):
        flash('知识库名称和 Dataset ID 不能为空', 'error')
        return redirect(url_for('admin.kbs'))

    from app.models import create_kb
    from app.config import get_dify_defaults
    cfg = get_dify_defaults()
    kb_id = create_kb(kb_name, description, cfg['api_url'], cfg['api_key'], dify_dataset_id)
    flash(f'知识库 {kb_name} 创建成功', 'success')
    return redirect(url_for('admin.kbs'))


@bp.route('/admin/kbs/<int:kb_id>', methods=['GET', 'POST'])
@admin_required
def edit_kb(kb_id):
    from app.models import get_kb_by_id, update_kb
    kb = get_kb_by_id(kb_id)
    if not kb:
        return '知识库不存在', 404

    if request.method == 'POST':
        from app.config import get_dify_defaults
        cfg = get_dify_defaults()
        update_kb(
            kb_id,
            request.form.get('kb_name', '').strip(),
            request.form.get('description', '').strip(),
            cfg['api_url'],
            cfg['api_key'],
            request.form.get('dify_dataset_id', '').strip(),
        )
        flash('知识库已更新', 'success')
        return redirect(url_for('admin.kbs'))

    return redirect(url_for('admin.kbs'))

    # GET: show simple inline edit via query param
    from flask import redirect
    return redirect(f'/admin/kbs?edit={kb_id}')


@bp.route('/admin/kbs/<int:kb_id>/delete', methods=['POST'])
@admin_required
def delete_kb(kb_id):
    from app.models import delete_kb
    delete_kb(kb_id)
    flash('知识库已删除', 'success')
    return redirect(url_for('admin.kbs'))


@bp.route('/admin/kbs/<int:kb_id>/documents', methods=['GET'])
@admin_required
def get_kb_documents(kb_id):
    """获取知识库的文档列表"""
    from app.models import get_kb_by_id
    kb = get_kb_by_id(kb_id)
    dataset_id = kb['dify_dataset_id'] if kb else None
    if not kb or not dataset_id:
        return jsonify({'documents': [], 'total': 0})

    from app.services.dify import build_dify_service
    dify = build_dify_service(kb)
    result = dify.list_documents()
    if 'error' in result:
        import logging
        logging.getLogger(__name__).error(f"[Admin] list_documents error: {result['error']}")
    return jsonify(result)


# ==================== Permission Management ====================

@bp.route('/admin/permissions', methods=['POST'])
@admin_required
def update_permissions():
    action = request.form.get('action', 'set')

    if action == 'batch':
        # Batch update: submit all KB permissions for a role at once
        role_id = request.form.get('role_id', type=int)
        redirect_url = request.form.get('redirect', '/admin/roles')

        from app.models import get_all_kbs, set_kb_role_permission, remove_kb_role_permission
        kbs = get_all_kbs()

        for kb in kbs:
            kb_id = kb['kb_id']
            can_read = 1 if request.form.get(f'kb_read_{kb_id}') else 0
            can_query = 1 if request.form.get(f'kb_query_{kb_id}') else 0

            if can_read or can_query:
                set_kb_role_permission(role_id, kb_id, can_read, can_query)
            else:
                remove_kb_role_permission(role_id, kb_id)

        flash('权限配置已保存', 'success')
        from flask import redirect
        return redirect(redirect_url)

    # Individual update (old single-permission mode)
    role_id = request.form.get('role_id', type=int)
    kb_id = request.form.get('kb_id', type=int)
    can_read = 1 if request.form.get('can_read') else 0
    can_query = 1 if request.form.get('can_query') else 0

    from app.models import set_kb_role_permission, remove_kb_role_permission
    if action == 'remove':
        remove_kb_role_permission(role_id, kb_id)
        flash('权限已移除', 'success')
    else:
        set_kb_role_permission(role_id, kb_id, can_read, can_query)
        flash('权限已更新', 'success')

    from flask import redirect
    return redirect(url_for('admin.roles'))