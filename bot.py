import logging, telegram, re
from config import config
from platforms import pixiv
from entities import Image

# from db import session

from telegram import ForceReply, Update, ext
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode, ChatType

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# id_to_comment: dict[int,list[Image]] = {}

# Define a few command handlers. These usually take the two arguments update and
# context.
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

    post_msg = msg.text.replace("/post", "").replace(f"@{context.bot.username}","").strip()  # 处理原始命令

    user = msg.from_user

    splited_msg = post_msg.split()
    post_url = splited_msg[0]
    tags = splited_msg[1:]

    if len(tags) < 1:
        await msg.reply_text("请添加tag")
        return

    if ("pixiv.net/artworks/" in post_msg) or re.match(r"[1-9]\d*", post_msg):
        # print("pixiv")
        await msg.reply_text("正在获取 Pixiv 图片...")
        result = await pixiv.getArtworks(post_url, tags, user, context)
        await msg.reply_text(result, ParseMode.HTML)
    elif "twitter" in post_msg:
        print("twitter")
    else:
        await msg.reply_text("获取失败，请检查url")

    pass


async def post_original_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("\n\n" + str(context.bot_data) + "\n\n")
    msg = update.message
    if msg.forward_from_message_id in context.bot_data:
        images = context.bot_data.pop(msg.forward_from_message_id)
        page_count = len(images)
        if page_count > 1:
            media_group = []
            for i in range(page_count):
                media_group.append(telegram.InputMediaDocument(images[i].rawurl))
            await msg.reply_media_group(media=media_group)
        else:
            await msg.reply_document(images[0].rawurl)


# async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     await update.message.reply_text(update.message.text)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(config.bot_token).build()

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
