"""把各种微信聊天记录导出文件导入统一归档库。

用法：
    python app/importer.py 导出文件或目录 [更多路径...] [--chat 名称] [--replace]

支持的格式：
    .csv / .tsv        自动识别列名（中英文皆可），每个文件可视为一个聊天
    .json / .jsonl     支持 {"messages":[...]} 、{"chats":[{"name":..,"messages":[..]}]} 、
                       纯消息数组，以及 chatlog / 留痕 等常见字段名
    目录              递归扫描其中的 csv/json，文件名作为聊天名（可用 --chat 覆盖）
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db as store

# 归一化字段 -> 可能出现的列名
SYNONYMS = {
    "time": ["time", "strtime", "createtime", "create_time", "msgtime", "sorttime",
             "timestamp", "ts", "date", "datetime", "时间", "发送时间", "消息时间", "日期"],
    "sender": ["sender", "from", "fromuser", "talker", "strsender", "nickname", "sendername",
               "speaker", "user", "username", "发送者", "发送人", "昵称", "发言人", "对方"],
    "content": ["content", "strcontent", "message", "msg", "text", "body", "msgcontent",
                "内容", "消息", "消息内容", "文本", "聊天内容"],
    "chat": ["chat", "chatname", "session", "room", "conversation", "strtalker", "talkername",
             "群聊", "会话", "聊天", "聊天对象", "联系人", "群名称", "好友"],
    "is_self": ["isself", "is_self", "issender", "direction", "issend", "自己发的", "是否自己"],
    "mtype": ["type", "msgtype", "msg_type", "subtype", "类型", "消息类型"],
}

SELF_WORDS = {"我", "自己", "self", "me", "true", "1", "out", "send", "sent", "right"}


def norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(s)).lower()


def build_map(headers: list[str]) -> dict[str, str]:
    """把实际列名映射到归一化字段。"""
    mapping = {}
    lower = {norm(h): h for h in headers}
    for field, names in SYNONYMS.items():
        for name in names:
            key = norm(name)
            if key in lower:
                mapping[field] = lower[key]
                break
    return mapping


def is_self_value(v) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in SELF_WORDS


def to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def rows_from_csv(path: Path) -> tuple[list[dict], dict[str, str]]:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-16", "gb18030", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法解码文件，请转成 UTF-8")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if sample.count("\t") > sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = [h for h in (reader.fieldnames or []) if h]
    return list(reader), build_map(headers)


def rows_from_json(path: Path) -> tuple[list[dict], dict[str, str], str | None]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    chat_hint = None

    def wrap(items):
        return items or []

    if isinstance(data, dict):
        if "messages" in data:
            items = wrap(data["messages"])
            chat_hint = data.get("name") or data.get("chat") or data.get("talker")
        elif "chats" in data or "sessions" in data:
            out = []
            for c in data.get("chats") or data.get("sessions"):
                name = c.get("name") or c.get("chat") or c.get("talker")
                for m in c.get("messages", []):
                    m = dict(m)
                    m.setdefault("__chat__", name)
                    out.append(m)
            items = out
        elif "data" in data and isinstance(data["data"], list):
            items = data["data"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("不支持的 JSON 结构")

    headers = []
    for it in items[:50]:
        if isinstance(it, dict):
            headers.extend(it.keys())
    return items, build_map(list(dict.fromkeys(headers))), chat_hint


def normalize(items: list[dict], mapping: dict[str, str], default_chat: str,
              chat_hint: str | None = None) -> list[dict]:
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        chat = to_text(it.get("__chat__")) or (
            to_text(it.get(mapping["chat"])) if "chat" in mapping else "") or chat_hint or default_chat
        ts = store.parse_time(it.get(mapping["time"])) if "time" in mapping else None
        if ts is None:
            continue
        content = to_text(it.get(mapping["content"])) if "content" in mapping else ""
        sender = to_text(it.get(mapping["sender"])) if "sender" in mapping else ""
        self_flag = is_self_value(it.get(mapping["is_self"])) if "is_self" in mapping else False
        if not self_flag and sender.strip() in {"我", "自己"}:
            self_flag = True
        mtype = to_text(it.get(mapping["mtype"])) if "mtype" in mapping else ""
        if not mtype or mtype.isdigit():
            mtype = store.guess_type(content)
        out.append({
            "chat": chat.strip() or default_chat,
            "ts": ts,
            "sender": sender.strip() or ("我" if self_flag else ""),
            "is_self": 1 if self_flag else 0,
            "mtype": mtype,
            "content": content,
        })
    return out


def collect(path: Path) -> list[Path]:
    if path.is_dir():
        files = []
        for ext in ("*.csv", "*.tsv", "*.json", "*.jsonl"):
            files.extend(path.rglob(ext))
        return sorted(files)
    return [path]


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    replace = "--replace" in argv
    chat_override = None
    for i, a in enumerate(argv):
        if a == "--chat" and i + 1 < len(argv):
            chat_override = argv[i + 1]
            args = [x for x in args if x != chat_override]

    if not args:
        print(__doc__)
        return 1

    con = store.connect()
    if replace:
        con.executescript("DELETE FROM messages; DELETE FROM chats; DELETE FROM meta;")
        con.commit()
        print("[i] 已清空原有数据")

    total = 0
    for arg in args:
        for f in collect(Path(arg)):
            try:
                if f.suffix.lower() in (".json", ".jsonl"):
                    items, mapping, hint = rows_from_json(f)
                else:
                    items, mapping = rows_from_csv(f)
                    hint = None
                if not mapping.get("content") or not mapping.get("time"):
                    print(f"[!] {f.name}: 找不到时间/内容列，跳过（可用 --chat 指定聊天名）")
                    continue
                recs = normalize(items, mapping, f.stem, hint)
                if chat_override:
                    for r in recs:
                        r["chat"] = chat_override
                by_chat: dict[str, list[dict]] = {}
                for r in recs:
                    by_chat.setdefault(r["chat"], []).append(r)

                for chat_name, msgs in by_chat.items():
                    kind = "group" if ("@" in chat_name or "群" in chat_name) else "friend"
                    cid = store.upsert_chat(con, chat_name, kind=kind)
                    existing = {(row[0], row[1]) for row in con.execute(
                        "SELECT ts, substr(content,1,64) FROM messages WHERE chat_id=?", (cid,))}
                    batch = []
                    for m in msgs:
                        sig = (m["ts"], m["content"][:64])
                        if sig in existing:
                            continue
                        batch.append((cid, m["ts"], m["sender"], m["is_self"], m["mtype"], m["content"]))
                    con.executemany(
                        "INSERT INTO messages(chat_id, ts, sender, is_self, mtype, content) "
                        "VALUES(?,?,?,?,?,?)", batch)
                    total += len(batch)
                    print(f"[✓] {chat_name}: 新增 {len(batch)} 条（文件 {f.name}）")
            except Exception as e:
                print(f"[!] {f.name}: {type(e).__name__} {e}")

    store.refresh_chat_stats(con)
    store.set_meta(con, imported_at=store.time.strftime("%Y-%m-%d %H:%M:%S"), source=args)
    con.commit()
    n_chat = con.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    n_msg = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"\n[i] 导入完成：{n_chat} 个聊天 / {n_msg} 条消息（本次新增 {total}）")
    print(f"[i] 数据库：{store.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
