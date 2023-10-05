import logging, re, os

# from db import session

import telegram
from telegram import ForceReply, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from config import config
from platforms import pixiv, twitter
from entities import Image

MAX_FILE_SIZE = 10 * 1024 * 1024

logger = logging.getLogger(__name__)

if config.debug:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )
    # set higher logging level for httpx to avoid all GET and POST requests being logged
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(config.txt_help, parse_mode=ParseMode.HTML)


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理post命令, 直接将投稿发至频道
    """
    msg = update.message
    logging.info(msg.text)

    if msg.chat.id not in config.bot_admin_chats:
        await msg.reply_text("请求失败! 只支持在指定的对话中发布")
        return

    post_msg = (
        msg.text.replace("/post", "").replace(f"@{context.bot.username}", "").strip()
    )  # 处理原始命令

    user = msg.from_user

    splited_msg = post_msg.split()
    post_url = splited_msg[0]
    tags = splited_msg[1:]

    platform = None
    success = False

    if ("pixiv.net/artworks/" in post_msg) or re.match(r"[1-9]\d*", post_msg):
        platform = "Pixiv"
        await msg.reply_text(f"正在获取 {platform} 图片...")
        success, feedback, caption, images = await pixiv.get_artworks(
            post_url, tags, user
        )
    elif "twitter" in post_msg or "x.com" in post_msg:
        platform = "twitter"
        await msg.reply_text(f"正在获取 {platform} 图片...")
        post_url = post_url.replace("x.com", "twitter.com")
        success, feedback, caption, images = await twitter.get_artworks(
            post_url, tags, user
        )
    else:
        feedback = "不支持的url"
    if success:
        caption += config.txt_msg_tail
        feedback = await send_media_group(feedback, caption, images, platform)
    await msg.reply_text(feedback, ParseMode.HTML)


async def send_media_group(
    msg: str, caption: str, images: list[Image], platform: str
) -> str:
    reply_msg = None
    media_group = []
    for image in images:
        file_path = f"./{platform}/{image.filename}"
        if image.size >= MAX_FILE_SIZE:
            media_group.append(
                telegram.InputMediaPhoto(
                    image.thumburl, has_spoiler=image.r18
                )
            )
        else:
            with open(file_path, "rb") as f:
                media_group.append(
                    telegram.InputMediaPhoto(
                        f, has_spoiler=image.r18
                    )
                )
    logger.debug(media_group)
    reply_msg = await bot.send_media_group(
        config.bot_channel, media_group, caption=caption, parse_mode=ParseMode.HTML
    )
    logger.debug(reply_msg)
    reply_msg = reply_msg[0]

    if reply_msg:
        application.bot_data[reply_msg.id] = images
    logger.info(application.bot_data[reply_msg.id])

    msg += f"\n发送成功！"
    return msg


async def post_original_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(context.bot_data)
    msg = update.message
    if msg.forward_from_message_id in context.bot_data:
        images: list[Image] = context.bot_data.pop(msg.forward_from_message_id)
        media_group = []
        for image in images:
            file_path = f"./{image.platform}/{image.filename}"
            with open(file_path, "rb") as f:
                media_group.append(telegram.InputMediaDocument(f))
        await msg.reply_media_group(media=media_group)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    global application
    application = Application.builder().token(config.bot_token).build()

    global bot
    bot = application.bot

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("post", post))
    application.add_handler(MessageHandler(filters.FORWARDED, post_original_pic))

    # on non command i.e message - echo the message on Telegram
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
