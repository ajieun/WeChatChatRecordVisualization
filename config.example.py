"""本地个人配置（不要提交到 git！）。

复制本文件为 config.py 并填入你自己的值：

    cp config.example.py config.py

或者直接用命令行参数覆盖，见 scripts/export_to_archive.py --help。
"""

# 微信 4.x 数据目录：账号目录的【上一级】
# 目录名通常是 xwechat_files，可能在 C: / D: / Documents 下
DB_DIR = r"D:\xwechat_files"

# 账号目录名：xwechat_files 下面以 <登录名>_<4位随机码> 命名的那个目录
ACCOUNT = "your_account_abcd"

# 密钥缓存目录（首次运行后会把解密密钥缓存在这里，绝不能外传/提交）
WORKDIR = r"_tools\wdb_work"
