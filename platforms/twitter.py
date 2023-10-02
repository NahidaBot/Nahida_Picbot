from config import config
from entities import Image, ImageTag
from telegram import User, ext, constants
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from db import session
from sqlalchemy import func
import logging, telegram


async def getArtworks(
    url: str, tags: list, user: User, content: ContextTypes.DEFAULT_TYPE
) -> str:
    pass
