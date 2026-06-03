#!/usr/bin/env python3
"""
初始化脚本：创建 admin 用户、Dify 知识库配置、分配权限
"""
import bcrypt
import sys
sys.path.insert(0, '/root/.openclaw/workspace/loong-kb')

from app.models import init_db, create_user, create_kb, assign_role_to_user, set_kb_role_permission
from app.models import get_role_by_name, get_kb_by_id, get_db_conn

def setup():
    init_db()
    print("✓ 数据库初始化完成")

    # Create admin user
    pwd_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        user_id = create_user('admin', pwd_hash, '管理员')
        print(f"✓ 创建管理员用户: admin / admin123")
    except Exception as e:
        print(f"  admin 用户已存在，跳过: {e}")
        from app.models import get_user_by_username
        user_id = get_user_by_username('admin')['user_id']

    # Assign admin role
    admin_role = get_role_by_name('admin')
    assign_role_to_user(user_id, admin_role['role_id'])
    print(f"✓ 分配 admin 角色")

    # Create viewer role if not exists
    viewer_role = get_role_by_name('viewer')
    if not viewer_role:
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO roles (role_name, description) VALUES ('viewer', '普通用户，只读访问')")
        viewer_role = get_role_by_name('viewer')
        print(f"✓ 创建 viewer 角色")

    # Add Dify KB config
    try:
        kb_id = create_kb(
            name='龙芯产品手册',
            description='龙芯 2K3000 处理器用户手册 V0.9 试用版',
            dify_api_url='http://10.40.65.201',
            dify_api_key='dataset-azoKiFzT0wBo90inEwSmE4Ho',
            dify_dataset_id='e41789cd-45d0-4d3d-b7d1-3d269efc0471'
        )
        print(f"✓ 创建知识库: 龙芯产品手册 (id={kb_id})")
    except Exception as e:
        print(f"  知识库已存在，跳过: {e}")
        from app.models import get_all_kbs
        kbs = get_all_kbs()
        kb_id = kbs[0]['kb_id'] if kbs else None

    if kb_id:
        # admin role can read + query
        set_kb_role_permission(admin_role['role_id'], kb_id, can_read=1, can_query=1)
        # viewer role can only read (not query, or query based on preference)
        set_kb_role_permission(viewer_role['role_id'], kb_id, can_read=1, can_query=1)
        print(f"✓ 权限配置完成: admin(viewer) -> 龙芯产品手册")

    print("\n✅ 初始化完成!")
    print("=" * 40)
    print("  管理员账号: admin / admin123")
    print("  访问地址: http://10.40.65.201:5001")
    print("  知识库: 龙芯产品手册 (对接 Dify API)")

if __name__ == '__main__':
    setup()