"""本地聊天记录查看器后端（仅用标准库）。"""
from __future__ import annotations

import json
import mimetypes
import sqlite3
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db as store

STATIC = Path(__file__).resolve().parent / "static"
PORT = 8777


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


class Handler(BaseHTTPRequestHandler):
    server_version = "WeChatArchive/1.0"

    def log_message(self, fmt, *args):
        pass

    # ---------- 工具 ----------
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def conn(self):
        con = sqlite3.connect(store.DB_PATH)
        con.row_factory = sqlite3.Row
        return con

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path.startswith("/api/"):
                return self.api(u.path[5:], qs)
            return self.static(u.path)
        except Exception as e:
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        f = (STATIC / rel).resolve()
        if not str(f).startswith(str(STATIC)) or not f.is_file():
            f = STATIC / "index.html"
        data = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if f.suffix in (".html", ".js", ".css"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def api(self, name: str, qs: dict):
        con = self.conn()
        try:
            if name == "meta":
                meta = store.get_meta(con)
                meta["chats"] = con.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
                meta["messages"] = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                rng = con.execute("SELECT MIN(ts), MAX(ts) FROM messages").fetchone()
                meta["range"] = [rng[0], rng[1]]
                return self.send_json(meta)

            if name == "chats":
                q = qs.get("q", "").strip()
                if q:
                    cur = con.execute("""
                        SELECT c.*, (SELECT content FROM messages m WHERE m.chat_id=c.id
                                     ORDER BY ts DESC LIMIT 1) AS preview
                        FROM chats c WHERE c.name LIKE ?
                        ORDER BY c.last_ts DESC""", (f"%{q}%",))
                else:
                    cur = con.execute("""
                        SELECT c.*, (SELECT content FROM messages m WHERE m.chat_id=c.id
                                     ORDER BY ts DESC LIMIT 1) AS preview
                        FROM chats c ORDER BY c.last_ts DESC""")
                return self.send_json({"chats": rows(cur)})

            if name == "messages":
                chat_id = int(qs.get("chat_id", 0))
                limit = min(int(qs.get("limit", 60)), 500)
                q = qs.get("q", "").strip()
                after = qs.get("after_ts")
                before = qs.get("before_ts")
                around = qs.get("around_ts")
                cond, params = ["chat_id = ?"], [chat_id]
                if q:
                    cond.append("content LIKE ?")
                    params.append(f"%{q}%")
                if around:
                    cond.append("ABS(ts - ?) <= 3 * 86400")
                    params.append(int(around))
                if before:
                    cond.append("ts < ?")
                    params.append(int(before))
                if after:
                    cond.append("ts > ?")
                    params.append(int(after))
                where = " AND ".join(cond)
                cur = con.execute(
                    f"SELECT * FROM messages WHERE {where} ORDER BY ts DESC LIMIT ?",
                    (*params, limit))
                items = rows(cur)
                items.reverse()
                return self.send_json({"messages": items})

            if name == "search":
                q = qs.get("q", "").strip()
                if not q:
                    return self.send_json({"hits": [], "total": 0})
                limit = min(int(qs.get("limit", 50)), 200)
                offset = int(qs.get("offset", 0))
                cond, params = ["m.content LIKE ?"], [f"%{q}%"]
                if qs.get("chat_id"):
                    cond.append("m.chat_id = ?")
                    params.append(int(qs["chat_id"]))
                if qs.get("start"):
                    cond.append("m.ts >= ?")
                    params.append(int(qs["start"]))
                if qs.get("end"):
                    cond.append("m.ts <= ?")
                    params.append(int(qs["end"]))
                where = " AND ".join(cond)
                total = con.execute(f"SELECT COUNT(*) FROM messages m WHERE {where}",
                                    params).fetchone()[0]
                cur = con.execute(f"""
                    SELECT m.id, m.chat_id, m.ts, m.sender, m.is_self, m.mtype, m.content,
                           c.name AS chat_name
                    FROM messages m JOIN chats c ON c.id = m.chat_id
                    WHERE {where} ORDER BY m.ts DESC LIMIT ? OFFSET ?""",
                    (*params, limit, offset))
                return self.send_json({"hits": rows(cur), "total": total})

            if name == "stats":
                chat_id = qs.get("chat_id")
                if chat_id:
                    cur = con.execute("""
                        SELECT COALESCE(NULLIF(sender,''),'未标注') AS sender, is_self, COUNT(*) n
                        FROM messages WHERE chat_id=? GROUP BY sender, is_self
                        ORDER BY n DESC LIMIT 30""", (int(chat_id),))
                    yearly = rows(con.execute("""
                        SELECT strftime('%Y', ts, 'unixepoch', 'localtime') y, COUNT(*) n
                        FROM messages WHERE chat_id=? GROUP BY y ORDER BY y""", (int(chat_id),)))
                else:
                    cur = con.execute("""
                        SELECT c.name AS sender, 0 AS is_self, c.msg_count AS n
                        FROM chats c ORDER BY n DESC LIMIT 30""")
                    yearly = rows(con.execute("""
                        SELECT strftime('%Y', ts, 'unixepoch', 'localtime') y, COUNT(*) n
                        FROM messages GROUP BY y ORDER BY y"""))
                return self.send_json({"senders": rows(cur), "yearly": yearly})

            return self.send_json({"error": "unknown api"}, 404)
        finally:
            con.close()


def main():
    if not store.DB_PATH.exists():
        print("[!] 还没有数据，请先运行：python app/importer.py <导出文件或目录>")
    httpd = None
    for port in range(PORT, PORT + 8):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        print("[!] 端口被占用，启动失败")
        return
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"[✓] 聊天记录查看器已启动：{url}")
    print("    关闭此窗口即可停止服务")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    httpd.serve_forever()


if __name__ == "__main__":
    main()
