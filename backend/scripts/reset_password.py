"""重置任意账号的密码（忘记 admin 密码时使用）。

用法（在 backend 目录下）：
    python scripts/reset_password.py admin 新密码
服务器上：
    cd /opt/unipredict/backend && ../venv/bin/python scripts/reset_password.py admin 新密码
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.security import hash_password  # noqa: E402

if len(sys.argv) != 3 or len(sys.argv[2]) < 6:
    print("用法：python scripts/reset_password.py 用户名 新密码（至少 6 位）")
    sys.exit(1)
db.init_db()
user, pwd = sys.argv[1], sys.argv[2]
row = db.query_one("SELECT id FROM users WHERE username = ?", [user])
if not row:
    print(f"用户 {user} 不存在")
    sys.exit(1)
db.update("users", row["id"], {"password_hash": hash_password(pwd), "is_active": 1})
print(f"已重置 {user} 的密码，可以直接登录（无需重启服务）")
