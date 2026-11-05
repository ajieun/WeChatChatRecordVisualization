"""解密微信 4.x 消息库并写入本地归档库 data/archive.db。

用法（项目根目录下）：
    .venv/Scripts/python.exe scripts/export_to_archive.py
    .venv/Scripts/python.exe scripts/export_to_archive.py --db-dir D:\\xwechat_files --account your_account_abcd

前提：微信 PC 版已登录；根目录有 config.py（或命令行传参）；已安装
wechatauto-replica（见 README）。
"""
import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db as appdb  # noqa: E402
from extract_keys import get_config, load_db_module  # noqa: E402

TYPE_MAP = {
    "文本": "text", "图片": "image", "语音": "voice", "视频": "video",
    "位置": "location", "动画表情": "sticker", "文件/链接/卡片": "file",
    "音视频通话": "call", "系统消息": "system", "红包": "redpacket",
}
# 群消息开头内嵌的发送者前缀，如 "wxid_abc123:\n"
WXID_PREFIX = re.compile(r"^(wxid_[a-z0-9]+|[a-zA-Z0-9_-]{6,20}@chatroom):\s*\n?")


def main():
    ap = argparse.ArgumentParser(description="解密微信消息并写入本地归档库")
    ap.add_argument("--db-dir", default=None, help="微信数据目录（账号目录的上一级）")
    ap.add_argument("--account", default=None, help="账号目录名")
    ap.add_argument("--workdir", default=None, help="密钥缓存目录")
    args = ap.parse_args()

    cfg = get_config()
    db_dir = args.db_dir or cfg.get("DB_DIR")
    account = args.account or cfg.get("ACCOUNT")
    workdir = args.workdir or cfg.get("WORKDIR") or "_tools/wdb_work"
    if not db_dir or not account:
        raise SystemExit("[X] 缺少 db_dir / account（config.py 或 --db-dir/--account 提供）")

    d = load_db_module()
    wx = d.WeChatDB(db_dir=db_dir, account=account, workdir=workdir)
    own_wxid = wx.wxid or ""
    self_info = wx.get_self_info()
    self_nick = self_info.get("nick_name", "")
    print(f"[i] 自己: {own_wxid} ({self_nick})", flush=True)

    md5_to_user = wx._build_md5_index()
    nicks = wx._nickname_index()
    print(f"[i] 会话索引 {len(md5_to_user)}，联系人 {len(nicks)}", flush=True)

    db_path = appdb.DB_PATH
    for f in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if f.exists():
            f.unlink()
    con = appdb.connect()
    chat_ids = {}

    def chat_id(username, md5):
        if username in chat_ids:
            return chat_ids[username]
        name = nicks.get(username, username)
        if not name or name == username:
            name = md5_to_user.get(md5, username)
            name = nicks.get(name, name)
        kind = "group" if "@chatroom" in username else (
            "official" if ("@kefu" in username or "@openim" in username) else "friend")
        cid = appdb.upsert_chat(con, name, alias=username, kind=kind, note=username)
        chat_ids[username] = cid
        return cid

    total = 0
    t0 = time.time()
    batch = []
    seen = set()

    for rel in wx._message_dbs():
        conn = wx._open(rel)
        name2id = wx._name2id_map(conn)
        tabs = [t[0] for t in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")]
        print(f"[i] {rel}: {len(tabs)} 张消息表", flush=True)
        for table in tabs:
            md5 = table[4:]
            username = md5_to_user.get(md5, md5)
            try:
                rows = conn.execute(
                    "SELECT local_id, local_type, server_id, real_sender_id, create_time,"
                    " message_content, packed_info_data, sort_seq FROM %s" % table
                ).fetchall()
            except sqlite3.DatabaseError:
                continue
            rows.sort(key=lambda r: (r["sort_seq"], r["local_id"]))
            for r in rows:
                m = wx._export_row(r, d.MSG_TYPE_NAMES)
                sender_wxid = name2id.get(int(r["real_sender_id"] or 0), "")
                is_self = 1 if (own_wxid and sender_wxid == own_wxid) else 0
                sender = nicks.get(sender_wxid, sender_wxid) if sender_wxid else ""
                if is_self:
                    sender = self_nick or "我"
                content = m["content"] or ""
                if isinstance(content, bytes):
                    content = content.decode("utf-8", "replace")
                content = WXID_PREFIX.sub("", content)
                tname = m["type"] if isinstance(m["type"], str) else "文本"
                mtype = TYPE_MAP.get(tname, "other")
                if mtype != "text":
                    if content.strip().startswith(("<", "\x3c")) or not content:
                        content = f"[{tname}]"
                sid = m.get("server_id") or 0
                key = (username, sid) if sid else (username, r["sort_seq"], r["local_id"])
                if key in seen:
                    continue
                seen.add(key)
                batch.append((chat_id(username, md5), int(m["create_time"] or 0),
                              sender, is_self, mtype, content))
                if len(batch) >= 5000:
                    con.executemany(
                        "INSERT INTO messages(chat_id, ts, sender, is_self, mtype, content)"
                        " VALUES(?,?,?,?,?,?)", batch)
                    con.commit()
                    total += len(batch)
                    batch.clear()
                    print(f"    {total} 条 [{time.time()-t0:.0f}s]", flush=True)
        conn.close()

    if batch:
        con.executemany(
            "INSERT INTO messages(chat_id, ts, sender, is_self, mtype, content)"
            " VALUES(?,?,?,?,?,?)", batch)
        con.commit()
        total += len(batch)
        batch.clear()

    print("[i] 刷新会话统计...", flush=True)
    appdb.refresh_chat_stats(con)
    appdb.set_meta(con, source="wechat", account=own_wxid,
                   exported_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                   total_messages=total, demo=False)
    con.commit()
    con.execute("PRAGMA optimize")
    con.close()
    print(f"[✓] 完成：{len(chat_ids)} 个会话，{total} 条消息，耗时 {time.time()-t0:.0f}s",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
