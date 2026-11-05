---
name: wechat-chat-export
description: 从 Windows 本地微信（3.x / 4.0 / 4.1）解密导出全部聊天记录并生成可搜索的本地查看器。适用于"导出微信聊天记录""微信聊天记录解密""做个本地聊天记录查询页面""db_storage 打不开/密钥扫不到""更新聊天记录"等请求。含 4.1 密钥提取（XOR 混淆在 WCDB Config.Cipher）、消息归属还原、数据清洗与查看器启动全流程。
---

# 微信聊天记录导出与本地查看器

把本机 Windows 微信的聊天记录解密、导出、清洗，并落成一个可全文检索的本地网页查看器。

## 适用范围与技术路线

| 微信版本 | 数据目录 | 密钥形态 | 本 skill 是否覆盖 |
|---|---|---|---|
| 3.x | `Documents\WeChat Files\<wxid>\Msg*.db` | 内存中 32 位 hex（需 MD5(IMEI+uin) 派生） | 参考，主流程按 4.x 写 |
| 4.0 | `xwechat_files\<account>\db_storage` | 内存明文 `x'<64hex>'` / `x'<64hex><32hex盐>'` | 可用，改扫描方式即可 |
| 4.1+ | 同上 | **不再有明文**，XOR 混淆在 `com.Tencent.WCDB.Config.Cipher` 配置对象里 | ✅ 主路径 |

关键结论（踩过的坑，别再重走）：

1. **不要自己写内存扫描器去捞 4.1 的密钥。** 4.1 登录后会把明文密钥擦掉，全量扫私有内存（1.5 GB × 多轮、原始字节 / 32 位 hex / 64 位 hex / 96 位 hex / base64 全试过）零命中。
2. 直接用 PyPI 上已适配 4.1 的实现 **`wechatauto-replica`** 的 `db` 模块，25 个库的密钥一次全出。
3. 该包的 `__init__` 会 import uiautomation / winsdk 等重依赖，**必须绕过 `__init__` 单独加载 `db.py`**（下给代码）。
4. 开源导出工具 `chatlog`（sjzar）、`wechat-dump-rs`（0xlane）已被 DMCA 下架或清空，别浪费时间找 release。
5. **微信必须处于已登录状态**，密钥只存在于已登录进程内存中；登录界面状态下数据库都没打开。

## 前置条件

- Windows，微信 PC 版已安装且**已登录**（任务栏能看到微信窗口）
- Python 3.10+，项目根目录有可用的 `.venv`
- 以只读方式访问 `xwechat_files`，**不修改、不移动微信原始数据**

## 步骤 0：定位版本与数据目录

```powershell
# 版本与安装路径
Get-Process | Where-Object {$_.ProcessName -match 'Weixin|WeChat'} | Select-Object Id,Path
(Get-Item "D:\WeChat\Weixin\Weixin.exe").VersionInfo.FileVersion

# 数据目录（新版 D:\xwechat_files，老版 Documents\WeChat Files）
Get-ChildItem D:\xwechat_files | Select-Object Name,LastWriteTime
Get-ChildItem D:\xwechat_files\<account>\db_storage -Recurse -File |
  Sort-Object Length -Descending | Select-Object -First 10 FullName,Length
```

要记下两个值，后面所有脚本都要用：

- `db_dir`：账号目录的**上一级**，例如 `D:\xwechat_files`
- `account`：账号目录名，例如 `your_account_abcd`

目录典型结构：

```
D:\xwechat_files\<account>\
├── db_storage\
│   ├── message\message_0..3.db + message_fts.db + message_resource.db   ← 消息主体（可达 GB 级）
│   ├── contact\contact.db        ← 联系人
│   ├── session\session.db        ← 会话
│   └── sns / favorite / emoticon / head_image ... 共 20+ 个库
├── msg\attach\...                ← 图片/语音/视频等 .dat 附件（本流程不解密）
└── config\                       ← 登录配置
```

加密形态：SQLCipher 4（AES-256-CBC，页 4096，PBKDF2-HMAC-SHA512 256000 轮），**每个库独立密钥**。

## 步骤 1：环境准备

```bash
cd <项目根目录>
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -q --upgrade pip
# 只装 db 模块真正需要的依赖，避免包的重依赖
./.venv/Scripts/python.exe -m pip download -q --no-deps -d _tools/pkg wechatauto-replica
./.venv/Scripts/python.exe -m pip install -q --no-deps _tools/pkg/*.whl
./.venv/Scripts/python.exe -m pip install -q cryptography zstandard pywin32 colorama
```

`--no-deps` 是关键：否则它会拖入 `uiautomation`、`winsdk`、`opencv` 等一堆与读取数据库无关的包，且在无 GUI 环境下容易报错。

## 步骤 2：提取密钥（绕过包初始化）

`_tools/extract_keys.py` 的核心——三行都不能少：

```python
import sys, types, importlib.util
from pathlib import Path

SITE = Path(".venv/Lib/site-packages/wechatauto").resolve()

def load_db():
    # 1) 伪造父包，只给 __path__，不执行真正的 __init__.py
    pkg = types.ModuleType("wechatauto")
    pkg.__path__ = [str(SITE)]
    sys.modules["wechatauto"] = pkg
    # 2) 按文件路径直接加载 db.py
    spec = importlib.util.spec_from_file_location("wechatauto.db", SITE / "db.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wechatauto.db"] = mod
    spec.loader.exec_module(mod)
    return mod

d = load_db()
db = d.WeChatDB(
    db_dir=r"D:\xwechat_files",          # 账号目录的上一级
    account="your_account_abcd",       # 账号目录名
    workdir=r"_tools\wdb_work",          # 密钥缓存目录
)
print(len(db._keys), db.master_key)
```

`WeChatDB.__init__` 内部完成：定位进程 → 解析 WCDB `Config.Cipher` → 反 XOR 掩码 → HMAC 校验 → 与库文件头盐值匹配。密钥随后缓存到 `workdir/keys.json`，同一份数据再次运行会很快。

预期输出（25 个库左右）：

```
[i] db 模块加载成功
[i] 账号: your_account_abcd
[i] 密钥数: 25
    contact/contact.db 3f9c...
[i] 主密钥: ...
```

## 步骤 3：导出到归档库

`_tools/export_to_archive.py` 做三件事，缺一条数据就会错：

1. **会话名解析**：`_build_md5_index()`（`Msg_<md5>` 表名 → 会话 username）+ `_nickname_index()`（username → 昵称）。群聊 username 以 `@chatroom` 结尾，据此判 `kind=group`。
2. **发送者还原**：每条消息的 `real_sender_id` 通过 `_name2id_map(conn)` 还原成真实 wxid，再映射昵称。**不要用昵称判断"是不是我发的"**——重名会错。
3. **自己发的判定**：`is_self = (sender_wxid == wx.self.wxid)`。实测 10.7 万条自己发的消息 100% 正确。

其它必须注意的点：

- 遍历 `wx._message_dbs()` → `wx._open(rel)` → `wx._shard_label` / `_name2id_map`，逐个 `Msg_*` 表用 `wx._export_row(row, d.MSG_TYPE_NAMES)` 转成统一结构；`sqlite3.DatabaseError` 要 `continue`（个别表结构异常）。
- 读 `-wal` 才能拿到最新消息：库对象本身走 SQLCipher 打开，WAL 会自动合并，不要只读 `.db` 主文件。
- 去重键：`(username, server_id)`，`server_id` 为空时退化为 `(username, sort_seq, local_id)`。
- 消息类型映射：`文本/图片/语音/视频/位置/动画表情/文件\/链接\/卡片/音视频通话/系统消息/红包` → 内部 mtype。
- 批量 5000 条一次 `executemany`，结束时 `refresh_chat_stats()` + 写 meta（`demo=False`），再 `PRAGMA optimize`。
- 量级参考：471 会话 / 145.6 万条消息 / 约 15 分钟 / 归档库 1.3 GB。

## 步骤 4：数据清洗

跑完导出后执行两步清洗（详见 `_tools` 下清洗片段，也可作为一次性 SQL/Python 脚本）：

1. 群消息开头的 `wxid_xxx:` / `xxx@chatroom:` 前缀（微信把发送者内嵌在 content 首行）—— 约 25 万条。
   正则：`^[A-Za-z0-9_\-]{3,30}:\n`
2. 原始 XML 消息转占位，避免界面上一屏 `<msg><img aeskey=...>`。
   按开头标签映射：`<img`→`[图片]`、`<voicemsg`→`[语音]`、`<videomsg`→`[视频]`、`<appmsg`→`[文件/链接]`、`<location`→`[位置]`、`<voipmsg`→`[通话]`；其余 XML 尝试抽 `<title>`，抽不到给 `[消息]`。

## 步骤 5：启动查看器

```bash
python app/server.py          # 或双击 启动.bat，默认 http://127.0.0.1:8777/
```

功能与接口：

| 功能 | 接口 / 操作 |
|---|---|
| 会话列表 | `GET /api/chats`（带最后一条消息预览） |
| **会话搜索（群组/个人）** | 左栏搜索框，前端对已加载会话实时过滤，支持「全部 / 群聊 / 单聊」切换；`?chat=关键字&kind=group` 可直达 |
| 全库搜索 | `GET /api/search?q=&chat_id=&start=&end=` |
| 会话内消息 | `GET /api/messages?chat_id=&limit=&before_ts=&around_ts=&q=` |
| 统计 | `GET /api/stats?chat_id=`（年度分布 + 发言人排行） |

会话搜索的类型映射要注意：归档库 `chats.kind` 实际取值是 `group` / `friend` / `official`（共 471 个：191 群 + 255 好友 + 25 公众号），**没有 `single` 这个值**。前端「单聊」= `kind != 'group'`，若直接按 `kind == 'single'` 过滤会得到空列表。

快捷键：`/` 聚焦全库搜索，`Ctrl+K` 或 `F` 聚焦会话搜索，`Esc` 清空/关闭浮层。

## 步骤 6：增量更新

双击 `更新数据.bat`（内部调用 `_tools/export_to_archive.py`），全量重建 `data/archive.db`。要求微信已登录；重跑前会删掉旧归档库与 `-wal/-shm`。

## 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 密钥数 0 / 扫不到密钥 | 微信停在登录界面，或进程刚重启未打开库 | 手动登录，等 30 秒（看 `contact.db-wal` 的 mtime 是否在更新）再跑 |
| `wechatauto` import 报 uiautomation/winsdk 错 | 走了包的 `__init__` | 用步骤 2 的 `load_db()`，不要 `import wechatauto.db` |
| PyPI 装不上 | 网络 | 用 `pip download` 先落 wheel，再 `--no-deps` 本地安装 |
| 后台扫描/导出进程莫名消失 | 工具会话结束时清理了子进程 | 用受管的后台任务方式运行，别用 `nohup`/裸 `&` |
| 消息里出现 `<msg>` XML | 未做步骤 4 清洗 | 重跑 XML 占位清洗 |
| 自己发的消息左右反了 | 用昵称判断 is_self | 改回 wxid 比对（步骤 3） |
| 服务器端口占用 | 8777 被占 | `server.py` 已在 8777–8784 自动顺延 |

## 安全与合规

- 全程**只读**微信数据目录，不修改、不移动、不覆盖原始 `.db`
- 密钥只缓存在本地 `_tools/wdb_work/`，**不要上传、不要外发、不要提交到 git**
- 导出结果仅存本地（`data/archive.db`），查看器只监听 `127.0.0.1`，不对外暴露
- 附件 `.dat`（图片/语音/视频）本流程不解密，界面上以 `[图片]` 等占位保留

## 项目文件对照

```
<项目根>/
├── 启动.bat / 更新数据.bat / 导入数据.bat
├── app/
│   ├── server.py       HTTP 服务（纯标准库）
│   ├── db.py           归档库 schema（chats / messages / meta）
│   ├── importer.py     通用导入器（CSV/JSON，第三方工具导出时用）
│   ├── demo_data.py    演示数据
│   └── static/         index.html / app.js / style.css
├── _tools/
│   ├── extract_keys.py        步骤 2
│   ├── export_to_archive.py   步骤 3（一键全量）
│   └── wdb_work/keys.json     密钥缓存（勿外传）
└── data/archive.db            归档库
```
