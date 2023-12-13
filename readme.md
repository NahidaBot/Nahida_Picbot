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
sudo cp gallery-dl.conf.example /etc/gallery-dl.conf

sudo vi /etc/gallery-dl.conf # 或者你顺手的编辑器
# 目前只需要更改 twitter 的用户名和密码, 似乎不支持 2fa, 介意可以注册小号
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

6. Linux 自启动参考

将以下文件保存到 /etc/systemd/system/nahida_bot.service 

```.service
[Unit]
Description=Nahida Picbot for telegram channel
After=network.target

[Install]
WantedBy=multi-user.target

[Service]
Type=simple
WorkingDirectory=/path/to/Nahida_Picbot/
ExecStart=/usr/bin/python3 bot.py
Restart=always
```

systemctl 常用命令参考

```shell
# 添加自启动, 且立即启动
systemctl enable --now nahida_bot.service 
# 关闭自启动, 且立即停止
systemctl disable --now nahida_bot.service 
# 去掉 --now 参数, 则仅影响下次自启动

# 查看运行状态
systemctl restart nahida_bot.service 
# 开启
systemctl start nahida_bot.service 
# 关闭
systemctl stop nahida_bot.service 
# 重启 适用于重载配置文件等
systemctl restart nahida_bot.service 

# 查看日志 (遇到错误可以打开 debug 模式)
journalctl -u nahida_bot.service # 可以使用 Pg Up/Down 翻页
```

## 参考

Telegram 官方 Bot API 文档: https://core.telegram.org/bots/api

Python-Telegram-Bot 文档: https://docs.python-telegram-bot.org/en/v20.5/index.html

PixivPy 项目: https://github.com/upbit/pixivpy

gallery-dl 项目: https://github.com/mikf/gallery-dl