# Nahida_Picbot

一个 Telegram 发图机器人, 接收 Pixiv 链接, 发送图片到频道, 并发送原图到关联的评论区。


## 食用方式

1. `clone` 本项目并进入项目目录

```bash
clone https://github.com/NahidaBuer/Nahida_Picbot.git && cd Nahida_Picbot
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

linux 下请使用 `pip3` 或者 `apt install python-is-python3`

3. 复制 `.env.example`, 并改名为 `.env`, 填入所有配置

```bash
cp .env.example .env

vi .env # 或者你顺手的编辑器
```

4. 复制 gallery-dl.conf, 查找 twitter, 填入用户名密码

Linux:

```bash
cp gallery-dl.conf.example ~/.gallery-dl.conf

vi .env # 或者你顺手的编辑器
```

Windows:

```powershell
cp gallery-dl.conf.example ~/gallery-dl.conf
 
code %USERPROFILE%\gallery-dl.conf # 或者你顺手的编辑器
```

5. 运行

```
python bot.py
```

## 参考

Telegram 官方 Bot API 文档: https://core.telegram.org/bots/api

Python-Telegram-Bot 文档: https://docs.python-telegram-bot.org/en/v20.5/index.html

PixivPy 项目: https://github.com/upbit/pixivpy

gallery-dl 项目: https://github.com/mikf/gallery-dl