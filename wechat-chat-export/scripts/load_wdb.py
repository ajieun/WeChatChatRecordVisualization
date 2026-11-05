"""加载 wechatauto.db（绕过包 __init__ 的重依赖），并取到全库密钥。

用法：
    .venv/Scripts/python.exe load_wdb.py <db_dir> <account> [workdir]

示例：
    .venv/Scripts/python.exe load_wdb.py D:\\xwechat_files your_account_abcd _tools/wdb_work
"""
import importlib.util
import sys
import types
from pathlib import Path


def load_db(site: Path | None = None):
    """按文件路径加载 wechatauto/db.py，不执行 wechatauto/__init__.py。"""
    if site is None:
        site = Path(".venv/Lib/site-packages/wechatauto").resolve()
    site = Path(site).resolve()

    pkg = types.ModuleType("wechatauto")
    pkg.__path__ = [str(site)]
    sys.modules["wechatauto"] = pkg

    spec = importlib.util.spec_from_file_location("wechatauto.db", site / "db.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wechatauto.db"] = mod
    spec.loader.exec_module(mod)
    return mod


def open_db(db_dir: str, account: str, workdir: str = "_tools/wdb_work"):
    d = load_db()
    return d, d.WeChatDB(db_dir=db_dir, account=account, workdir=workdir)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    db_dir, account = sys.argv[1], sys.argv[2]
    workdir = sys.argv[3] if len(sys.argv) > 3 else "_tools/wdb_work"

    d, wx = open_db(db_dir, account, workdir)
    print(f"[i] 账号: {wx.account}")
    print(f"[i] 密钥数: {len(wx._keys)}")
    for rel in sorted(wx._keys):
        print(f"    {rel}  {wx._keys[rel].hex()[:24]}...")
    if wx.master_key:
        print(f"[i] 主密钥: {wx.master_key[:24]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
