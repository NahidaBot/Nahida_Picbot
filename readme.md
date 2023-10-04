# Nahida_Picbot

一个 Telegram 发图机器人, 接收 Pixiv 链接, 发送图片到频道, 并发送原图到关联的评论区。

目前作为 [@gongzhutonghao](https://t.me/gongzhutonghao) 的发图机器人。


## 食用方式

1. `clone` 本项目并进入项目目录
2. `pip install -r requirements.txt` 
3. 复制 `.env.example`, 并改名为 `.env`, 填入所有配置
4. `cp gallery-dl.conf.example gallery-dl.conf`, 查找 twitter, 填入用户名密码

## 参考

Telegram 官方 Bot API 文档: https://core.telegram.org/bots/api

Python-Telegram-Bot 文档: https://docs.python-telegram-bot.org/en/v20.5/index.html

PixivPy 项目: https://github.com/upbit/pixivpy

gallery-dl 项目: https://github.com/mikf/gallery-dl