"""从已登录的微信进程提取全部数据库密钥（支持 4.0 / 4.1+）。

用法（项目根目录下）：
    .venv/Scripts/python.exe scripts/extract_keys.py --db-dir D:\\xwechat_files --account your_account_abcd

也可不带参数：自动读取根目录 config.py 中的 DB_DIR / ACCOUNT。
"""
import argparse
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_db_module(site: Path | None = None):
    """按文件路径加载 wechatauto/db.py。

    必须绕过包的 __init__.py —— 它会 import uiautomation / winsdk 等重依赖，
    在无 GUI 或精简环境下直接报错。db.py 本身只依赖 cryptography。
    """
    if site is None:
        site = ROOT / ".venv/Lib/site-packages/wechatauto"
    site = Path(site).resolve()
    if not (site / "db.py").exists():
        raise SystemExit(
            f"[X] 未找到 {site}\\db.py，请先安装：\n"
            "    .venv/Scripts/python.exe -m pip download --no-deps -d _tools/pkg wechatauto-replica\n"
            "    .venv/Scripts/python.exe -m pip install --no-deps _tools/pkg/wechatauto_replica-*.whl\n"
            "    .venv/Scripts/python.exe -m pip install cryptography zstandard pywin32 colorama"
        )
    pkg = types.ModuleType("wechatauto")
    pkg.__path__ = [str(site)]
    sys.modules["wechatauto"] = pkg
    spec = importlib.util.spec_from_file_location("wechatauto.db", site / "db.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wechatauto.db"] = mod
    spec.loader.exec_module(mod)
    return mod


def get_config():
    """可选：从根目录 config.py 读取默认 DB_DIR / ACCOUNT。"""
    cfg = {}
    p = ROOT / "config.py"
    if p.exists():
        spec = importlib.util.spec_from_file_location("user_config", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        cfg = {k: getattr(m, k) for k in ("DB_DIR", "ACCOUNT", "WORKDIR") if hasattr(m, k)}
    return cfg


def main():
    ap = argparse.ArgumentParser(description="提取微信 4.x 数据库密钥")
    ap.add_argument("--db-dir", default=None, help="微信数据目录（账号目录的上一级）")
    ap.add_argument("--account", default=None, help="账号目录名")
    ap.add_argument("--workdir", default=None, help="密钥缓存目录")
    args = ap.parse_args()

    cfg = get_config()
    db_dir = args.db_dir or cfg.get("DB_DIR")
    account = args.account or cfg.get("ACCOUNT")
    workdir = args.workdir or cfg.get("WORKDIR") or "_tools/wdb_work"
    if not db_dir or not account:
        raise SystemExit(
            "[X] 缺少 --db-dir / --account。请复制 config.example.py 为 config.py 填好，"
            "或在命令行显式传入。\n"
            "    目录结构: <db_dir>/<account>/db_storage/message/message_0.db"
        )

    print(f"[i] db_dir  = {db_dir}")
    print(f"[i] account = {account}")
    print("[i] 前提：微信 PC 版已在本机登录（密钥只存在于已登录进程内存中）")

    d = load_db_module()
    wx = d.WeChatDB(db_dir=db_dir, account=account, workdir=workdir)

    print(f"[✓] 提取成功，共 {len(wx._keys)} 个库的密钥：")
    for rel in sorted(wx._keys):
        print(f"    {rel}  {wx._keys[rel].hex()[:16]}...")
    if wx.master_key:
        print(f"[✓] 主密钥: {wx.master_key[:12]}...")

    print(f"[i] 密钥已缓存在 {workdir}/keys.json —— 该文件等于你全部聊天记录的钥匙，切勿外传")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
