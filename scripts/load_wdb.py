"""加载 wechatauto.db 并打开微信数据库（脚本骨架）。

用法：
    .venv/Scripts/python.exe scripts/load_wdb.py --db-dir D:\\xwechat_files --account your_account_abcd

在你的脚本里复用：

    from scripts.extract_keys import load_db_module
    d = load_db_module()
    wx = d.WeChatDB(db_dir=..., account=..., workdir=...)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_keys import get_config, load_db_module  # noqa: E402


def open_db(db_dir: str | None = None, account: str | None = None,
            workdir: str | None = None):
    cfg = get_config()
    db_dir = db_dir or cfg.get("DB_DIR")
    account = account or cfg.get("ACCOUNT")
    workdir = workdir or cfg.get("WORKDIR") or "_tools/wdb_work"
    if not db_dir or not account:
        raise SystemExit("[X] 缺少 db_dir / account（config.py 或命令行参数提供）")
    d = load_db_module()
    return d, d.WeChatDB(db_dir=db_dir, account=account, workdir=workdir)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-dir")
    ap.add_argument("--account")
    ap.add_argument("--workdir")
    args = ap.parse_args()

    d, wx = open_db(args.db_dir, args.account, args.workdir)
    print(f"[i] 账号: {wx.account}")
    print(f"[i] 密钥数: {len(wx._keys)}")
    for rel in sorted(wx._keys):
        print(f"    {rel}  {wx._keys[rel].hex()[:16]}...")
    if wx.master_key:
        print(f"[i] 主密钥: {wx.master_key[:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
