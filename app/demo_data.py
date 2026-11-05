"""生成演示数据，方便先预览界面（导入真实数据时会自动清空）。"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as store

random.seed(20261104)
NOW = int(time.time())
DAY = 86400

DIALOGS = {
    "大学室友群": (
        "group",
        ["阿杰", "老王", "小胖", "阿杰"],
        [
            "今晚谁有空？老地方撸串",
            "我可以，几点",
            "七点半吧，我先去占位",
            "好，我大概七点四十到",
            "记得把上次的发票带上，报销要用",
            "收到",
            "话说你们周末去爬山吗？天气预报说是晴天",
            "去！我正好买了新登山鞋",
            "那定周六早上八点地铁站集合",
            "图片.jpg",
            "这家的串真不错，下次还来",
            "同意，就是有点辣",
            "谁能帮我看看这段代码为什么报错",
            "把报错信息发群里看看",
            "已经发了，在第 42 行",
            "少了个分号吧 😂",
        ],
    ),
    "妈妈": (
        "friend",
        ["妈妈", "我"],
        [
            "吃饭了吗",
            "刚吃完，你呢",
            "我也吃了，今天做了红烧肉",
            "周末回来吃饭吗，给你留着",
            "应该可以，周六下午到",
            "路上注意安全，天冷了多穿点",
            "知道了妈",
            "给你寄了点家乡的橘子，明天应该到",
            "谢谢妈，收到了告诉你",
        ],
    ),
    "产品-研发对接群": (
        "group",
        ["张产品", "李研发", "王测试", "我"],
        [
            "这版需求文档更新了，大家看一下",
            "登录页的验证码逻辑要改，现在体验太差",
            "改成滑块还是保持短信？",
            "先用短信，滑块下个版本再说",
            "接口文档我今晚同步到 wiki",
            "测试环境什么时候能部署",
            "明天上午十点前",
            "发现一个 bug，订单金额显示少了一分钱",
            "是浮点数精度问题，用分存储就好了",
            "已修复，麻烦回归一下",
            "回归通过 ✅",
            "周五发版，大家注意封版时间",
        ],
    ),
    "健身搭子-小陈": (
        "friend",
        ["小陈", "我"],
        [
            "今天练背还是练腿",
            "腿吧，昨天背有点酸",
            "那先深蹲，我带你热身",
            "行，六点半健身房见",
            "记得带护膝",
            "今天卧推破百了！",
            "牛啊，恭喜",
            "下次一起挑战 105",
        ],
    ),
    "文件传输助手": (
        "other",
        ["我"],
        [
            "会议纪要 2026-10-28",
            "https://example.com/design-review",
            "报销单.xlsx",
            "记得周三前提交季度总结",
        ],
    ),
}


def main():
    con = store.connect()
    con.executescript("DELETE FROM messages; DELETE FROM chats; DELETE FROM meta;")
    con.commit()

    total = 0
    for name, (kind, speakers, lines) in DIALOGS.items():
        cid = store.upsert_chat(con, name, kind=kind)
        n = 260 if kind == "group" else 140
        ts = NOW - DAY * 420
        batch = []
        for i in range(n):
            ts += random.randint(600, 60 * 60 * 8)
            if ts > NOW - 120:
                ts = NOW - random.randint(60, 3000)
            line = random.choice(lines)
            sender = random.choice(speakers)
            is_self = 1 if sender == "我" else 0
            mtype = store.guess_type(line)
            if mtype == "text" and random.random() < 0.03:
                line = "[图片] " + random.choice(["IMG_2031.jpg", "截图.png", "微信图片_2026.jpg"])
                mtype = "image"
            batch.append((cid, ts, sender, is_self, mtype, line))
        con.executemany(
            "INSERT INTO messages(chat_id, ts, sender, is_self, mtype, content) VALUES(?,?,?,?,?,?)",
            batch)
        total += len(batch)

    store.refresh_chat_stats(con)
    store.set_meta(con, demo=True, imported_at=time.strftime("%Y-%m-%d %H:%M:%S"), source=["demo"])
    con.commit()
    print(f"[✓] 演示数据已写入：{len(DIALOGS)} 个会话 / {total} 条消息")
    print(f"[i] {store.DB_PATH}")


if __name__ == "__main__":
    main()
