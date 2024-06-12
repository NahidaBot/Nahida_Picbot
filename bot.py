import datetime
import os
import logging

from db import session

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from config import config
from entities import Image
from utils import compress_image, is_within_size_limit, unmark_deduplication, find_url
from commands import *

if not os.path.exists("./downloads/"):
    os.mkdir("./downloads/")

logger = logging.getLogger(__name__)

if config.debug:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )
    # set higher logging level for httpx to avoid all GET and POST requests being logged
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# global application
application = (
    Application.builder()
    .token(config.bot_token)
    .post_init(on_start)
    .read_timeout(20)
    .write_timeout(20)
    .connect_timeout(20)
    .build()
)

# global bot
bot = application.bot
application.bot_data["last_msg"] = datetime.fromtimestamp(0)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("post", post))
    application.add_handler(CommandHandler("echo", echo))
    application.add_handler(CommandHandler("mark_dup", mark))
    application.add_handler(CommandHandler("unmark_dup", unmark))
    application.add_handler(CommandHandler("set_commands", set_commands))
    application.add_handler(CommandHandler("repost_orig", repost_orig))
    application.add_handler(CommandHandler("update", update))
    application.add_handler(CommandHandler("get_admins", get_admins))
    application.add_handler(
        MessageHandler(
            filters.FORWARDED & filters.PHOTO & filters.User(777000),
            get_channel_post,
        )
    )
    application.add_handler(CommandHandler("restart", restart))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
