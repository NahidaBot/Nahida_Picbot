import asyncio
import telegram
from config import config

with open('/Users/na/Desktop/photo_2024-01-12_17-04-33.jpg', 'rb') as f:
    asyncio.run(telegram.Bot(config.bot_token).send_photo(
        '-1001877746718',
        telegram.InputMediaPhoto(f)
    ))