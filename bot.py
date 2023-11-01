import logging
import re
import datetime

# from db import session

import telegram
from telegram import ForceReply, Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from config import config
from platforms import pixiv, twitter, miyoushe
from entities import Image
from utils import compress_image, is_within_size_limit, unmark_deduplication

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

    if update.message.chat_id not in config.bot_admin_chats:
        return await permission_denied(update.message)

    success, feedback, caption, images = await get_artworks(update.message)

    if success:
        caption += config.txt_msg_tail
        feedback = await send_media_group(feedback, caption, images)
    await msg.reply_text(feedback, ParseMode.HTML)


async def get_artworks(
    msg: telegram.Message, post_mode: bool = True, feedback: bool = True
) -> tuple:
    """
    post_mode 为 True 时，发送到频道，否则，直接将消息返回给用户。
    只有发送到频道时才会尝试去重。
    """
    splited_msg = msg.text.split()[1:]
    post_url = splited_msg[0]
    tags = splited_msg[1:]
    user = msg.from_user

    platform = None
    success = False
    caption = ""
    feedback = ""
    images = None

    if ("pixiv.net/artworks/" in post_url) or re.match(r"[1-9]\d*", post_url):
        if feedback:
            await msg.reply_text("正在获取 Pixiv 图片...")
        success, feedback, caption, images = await pixiv.get_artworks(
            post_url, tags, user, post_mode
        )
    elif "twitter" in post_url or "x.com" in post_url:
        if feedback:
            await msg.reply_text("正在获取 twitter 图片...")
        post_url = post_url.replace("x.com", "twitter.com")
        success, feedback, caption, images = await twitter.get_artworks(
            post_url, tags, user, post_mode
        )
    elif "miyoushe.com" in post_url or "bbs.mihoyo" in post_url:
        if feedback:
            await msg.reply_text("正在获取米游社图片...")
        success, feedback, caption, images = await miyoushe.get_artworks(
            post_url, tags, user, post_mode
        )
    else:
        feedback = "不支持的url"

    return (success, feedback, caption, images)


async def send_media_group(
    msg: str, caption: str, images: list[Image], chat_id: int | str = config.bot_channel
) -> str:
    reply_msg = None
    media_group = []
    for image in images:
        file_path = f"./{image.platform}/{image.filename}"
        if image.size >= MAX_FILE_SIZE or not is_within_size_limit(file_path):
            img_compressed = "./Pixiv/cache.jpg"
            compress_image(file_path, img_compressed)
            file_path = img_compressed
        with open(file_path, "rb") as f:
            media_group.append(telegram.InputMediaPhoto(f, has_spoiler=image.r18))
    logger.debug(media_group)

    # 防打扰，5分钟内不开启通知音
    disable_notification = False
    now = datetime.datetime.now()
    interval = now - application.bot_data["last_msg"]
    if interval.total_seconds() < config.bot_disable_notification_interval:
        disable_notification = True
    application.bot_data["last_msg"] = now

    reply_msg = await bot.send_media_group(
        chat_id,
        media_group,
        caption=caption,
        parse_mode=ParseMode.HTML,
        disable_notification=disable_notification,
    )
    logger.debug(reply_msg)
    reply_msg = reply_msg[0]

    if reply_msg and chat_id == config.bot_channel:
        # 发原图
        application.bot_data[reply_msg.id] = images
        logger.info(application.bot_data[reply_msg.id])

    msg += f"\n发送成功！"
    return msg


async def get_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 匹配 bot_data, 匹配到则发送原图, 否则忽略该消息
    logger.info(context.bot_data)
    msg = update.message
    if msg.forward_from_message_id and msg.forward_from_message_id in context.bot_data:
        await post_original_pic(msg)


async def post_original_pic(
    msg: telegram.Message = None,
    chat_id: int | str = config.bot_channel,
    images: list[Image] = None,
) -> None:
    """
    msg 与 chat_id, images 互斥, 前者用于捕获频道消息并回复原图, 后者直接发送到指定 chat_id, 目前用于获取图片信息
    """
    if not images:
        images: list[Image] = application.bot_data.pop(msg.forward_from_message_id)
    media_group = []
    for image in images:
        file_path = f"./{image.platform}/{image.filename}"
        with open(file_path, "rb") as f:
            media_group.append(telegram.InputMediaDocument(f))
    if msg:
        await msg.reply_media_group(media=media_group)
    else:
        await bot.send_media_group(chat_id, media_group)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    logging.info(msg.text)

    success, feedback, caption, images = await get_artworks(
        update.message, post_mode=False
    )
    if success:
        caption += config.txt_msg_tail
        feedback = await send_media_group(feedback, caption, images, msg.chat_id)
    await post_original_pic(chat_id=msg.chat_id, images=images)


async def set_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat_id not in config.bot_admin_chats:
        return await permission_denied(update.message)

    commands = [
        BotCommand("post", "(admin)  /post url #tag1 #tag2 发图到频道"),
        BotCommand("echo", "/echo url #tag1 #tag2 返回预览"),
        BotCommand("mark_dup", "(admin) /mark_dup url 标记图片已被发送过"),
        BotCommand("unmark_dup", "(admin) /unmark_dup url 反标记该图片信息"),
        BotCommand("ping", "hello"),
    ]

    r = await context.bot.set_my_commands(commands)
    await update.message.reply_text(str(r))


async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat_id not in config.bot_admin_chats:
        return await permission_denied(update.message)
    success, msg, tmp, tmp = await get_artworks(update.message, feedback=False)
    if success:
        await update.message.reply_text("成功标记为已发送！")
    else:
        await update.message.reply_text("标记失败，请查看日志！")
        logger.error(msg)


async def unmark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat_id not in config.bot_admin_chats:
        return await permission_denied(update.message)
    try:
        pid = update.message.text.split()[1].strip("/").split("/")[-1].split("?")[0]
        unmark_deduplication(pid)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("发生了一个错误，请查看日志！")
        return
    await update.message.reply_text("操作成功！")


async def permission_denied(message: telegram.Message) -> None:
    # TODO 鉴权这块可以改成装饰器实现
    await message.reply_text("permission denied")


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    global application
    application = Application.builder().token(config.bot_token).build()

    global bot
    bot = application.bot
    application.bot_data["last_msg"] = datetime.datetime.fromtimestamp(0)

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("post", post))
    application.add_handler(CommandHandler("echo", echo))
    application.add_handler(CommandHandler("mark_dup", mark))
    application.add_handler(CommandHandler("unmark_dup", unmark))
    application.add_handler(CommandHandler("set_commands", set_commands))
    application.add_handler(MessageHandler(filters.FORWARDED, get_channel_post))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
