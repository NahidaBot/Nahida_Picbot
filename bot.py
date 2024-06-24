import datetime
import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    InlineQueryHandler,
)
from config import config
from commands import *

if not os.path.exists(DefaultPlatform.base_downlad_path):
    os.makedirs(DefaultPlatform.base_downlad_path)

if config.debug:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )
    # set higher logging level for httpx to avoid all GET and POST requests being logged
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# global application
application = (
    Application.builder()
    .token(config.bot_token)
    .post_init(on_start)  # type: ignore
    .read_timeout(60)
    .write_timeout(60)
    .connect_timeout(60)
    .build()
)

# global bot
bot = application.bot
application.bot_data["last_msg"] = datetime.fromtimestamp(0)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start, block=False))
    application.add_handler(CommandHandler("ping", start, block=False))
    application.add_handler(CommandHandler("random", random, block=False))
    application.add_handler(CommandHandler("help", help_command, block=False))
    application.add_handler(CommandHandler("post", post, block=False))
    application.add_handler(CommandHandler("echo", echo, block=False))
    # application.add_handler(CommandHandler("mark_dup", mark))
    # application.add_handler(CommandHandler("unmark_dup", unmark))
    # application.add_handler(CommandHandler("repost_orig", repost_orig))
    application.add_handler(CommandHandler("set_commands", set_commands, block=False))
    application.add_handler(CommandHandler("update", update))
    application.add_handler(CommandHandler("get_admins", get_admins))
    application.add_handler(
        MessageHandler(
            filters.FORWARDED
            & filters.PHOTO
            # & filters.ChatType.GROUPS
            & filters.User(777000),
            get_channel_post,
            block=False,
        )
    )
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(
        MessageHandler(
            # filters.TEXT &
            filters.ChatType.PRIVATE
            & (filters.Entity("url") | filters.Entity("text_link") | filters.CaptionEntity("url") | filters.CaptionEntity("text_link")),
            callback=handle_private_share,
            block=False,
        )
    )
    application.add_handler(InlineQueryHandler(handle_inline_cmd, r'\/(post|echo).+',block=False))
    application.add_handler(InlineQueryHandler(handle_inline_query,block=False))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
