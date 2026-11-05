"""统一归档库：表结构与通用工具。"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "archive.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    alias     TEXT,
    kind      TEXT DEFAULT 'friend',
    note      TEXT,
    msg_count INTEGER DEFAULT 0,
    last_ts   INTEGER
);

CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    ts      INTEGER NOT NULL,
    sender  TEXT,
    is_self INTEGER DEFAULT 0,
    mtype   TEXT DEFAULT 'text',
    content TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

CREATE INDEX IF NOT EXISTS idx_msg_chat_ts ON messages(chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(ts);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(content, content='messages', content_rowid='id', tokenize='trigram');

CREATE TRIGGER IF NOT EXISTS msg_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS msg_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS msg_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

TYPE_HINTS = [
    ("[图片]", "image"), ("[照片]", "image"), ("<img", "image"),
    ("[语音]", "voice"), ("[视频]", "video"), ("[文件]", "file"),
    ("[链接]", "link"), ("[动画表情]", "sticker"), ("[表情]", "sticker"),
    ("[位置]", "location"), ("[转账]", "transfer"), ("[红包]", "redpacket"),
    ("[小程序]", "miniapp"), ("[名片]", "card"),
]


def guess_type(text: str) -> str:
    if not text:
        return "other"
    t = text.strip()
    for token, kind in TYPE_HINTS:
        if t.startswith(token):
            return kind
    if t.startswith("<?xml") or t.startswith("<msg"):
        return "xml"
    return "text"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def upsert_chat(con: sqlite3.Connection, name: str, alias: str | None = None,
                kind: str = "friend", note: str | None = None) -> int:
    row = con.execute("SELECT id FROM chats WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = con.execute(
        "INSERT INTO chats(name, alias, kind, note) VALUES(?,?,?,?)",
        (name, alias, kind, note),
    )
    return cur.lastrowid


def refresh_chat_stats(con: sqlite3.Connection) -> None:
    con.execute("""
        UPDATE chats SET
            msg_count = (SELECT COUNT(*) FROM messages m WHERE m.chat_id = chats.id),
            last_ts   = (SELECT MAX(ts) FROM messages m WHERE m.chat_id = chats.id)
    """)


def set_meta(con: sqlite3.Connection, **kv) -> None:
    for k, v in kv.items():
        con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, json.dumps(v, ensure_ascii=False)))


def get_meta(con: sqlite3.Connection) -> dict:
    out = {}
    for row in con.execute("SELECT key, value FROM meta"):
        try:
            out[row["key"]] = json.loads(row["value"])
        except Exception:
            out[row["key"]] = row["value"]
    return out


TS_PATTERNS = [
    (re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$"), "ymdhms"),
    (re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$"), "ymd"),
]


def parse_time(value) -> int | None:
    """把各种时间写法统一成 Unix 秒。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e12:      # 毫秒
            v /= 1000
        if v > 1e8:
            return int(v)
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10,13}", s):
        v = int(s)
        return int(v / 1000) if len(s) == 13 else v
    m = TS_PATTERNS[0][0].match(s)
    if m:
        g = [int(x) if x else 0 for x in m.groups()]
        return int(time.mktime((g[0], g[1], g[2], g[3], g[4], g[5], 0, 0, -1)))
    m = TS_PATTERNS[1][0].match(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return int(time.mktime((y, mo, d, 0, 0, 0, 0, 0, -1)))
    # 兜底：让 dateutil 之外的常见格式也试一下
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M", "%Y年%m月%d日 %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(time.mktime(time.strptime(s, fmt)))
        except ValueError:
            continue
    return None
