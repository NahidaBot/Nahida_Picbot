from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = True

    bot_token: str = ""
    bot_admin_chats: list[int] = []
    bot_channel: str = "@"
    bot_channel_comment_group: int = -1
    bot_deduplication_mode: bool = False
    bot_disable_notification_interval: int = 600

    bot_enable_ai_redirect: bool = False
    bot_enable_ai_redirect_channel: str = ""

    db_url: str = "sqlite://data/data.db"

    pixiv_refresh_token: str = ""
    pixiv_phpsessid: str = ""
    pixiv_device_token: str = ""

    # bilibili cookie (暂未启用)
    bilibili_cookie: str = ""

    txt_help: str = """\
此机器人还在测试中, 目前只有发图一个功能~\n
/post - 发送作品到频道, 命令语法: <code>/post URL #tag</code>
URL支持Pixiv或者Twitter链接, 后面必须有<b>至少一个</b>tag
例如: <code>/post https://www.pixiv.net/artworks/112166064 #明星ヒマリ #碧蓝档案</code>\n
成功获取后, 会直接发送到频道, 并将原图发到评论区~\n
请注意：稿件有多图时, 会将全部图片合并发送\
"""
    txt_msg_tail: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


config = Settings()

# if __name__ == "__main__":
#     print(config.dict())
