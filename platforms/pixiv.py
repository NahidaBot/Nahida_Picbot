from pixivpy3 import *
from config import config
from entities import Image
from telegram import User, ext, constants
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from db import session
from sqlalchemy import func
import bot
import logging, telegram

api = AppPixivAPI()
api.set_accept_language("zh-cn")
api.auth(refresh_token=config.pixiv_refresh_token)

# TODO 注意，ImageTags尚未启用


async def getArtworks(
    url: str, tags: list, user: User, context: ContextTypes.DEFAULT_TYPE
) -> str:
    pid = url.strip("/").split("/")[-1]  # 取 PID

    illust = api.illust_detail(pid)["illust"]
    id = illust["id"]
    page_count = illust["page_count"]

    existing_image = session.query(Image).filter_by(pid=id).first()
    if config.bot_deduplication_mode and existing_image:
        logging.log(logging.WARNING, "试图发送重复的图片: Pixiv" + str(id))
        return f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过"

    meta_pages = illust["meta_pages"]

    image_width_height_info = await getArtworksWidthHeight(pid)
    msg = f"""获取成功！
<b>{illust["title"]}</b>
共有{page_count}张图片
"""
    images: list[Image] = []

    for i in range(page_count):
        img = Image(
            userid=user.id,
            username=user.username,
            platform="Pixiv",
            pid=id,
            title=illust["title"],
            page=i,
            author=illust["user"]["name"],
            authorid=illust["user"]["id"],
            r18=True if illust["x_restrict"] == 1 else False,
            rawurl=meta_pages[i]["image_urls"]["original"]
            if page_count > 1
            else illust["meta_single_page"]["original_image_url"],
            thumburl=meta_pages[i]["image_urls"]["large"]
            if page_count > 1
            else illust["image_urls"]["large"],
        )
        if image_width_height_info:
            img.width = image_width_height_info[i]["width"]
            img.height = image_width_height_info[i]["height"]
            msg += f"第{i+1}张图片：{img.width}x{img.height}\n"
        images.append(img)
        session.add(img)
        api.download(img.rawurl, path="./Pixiv/")
    session.commit()

    from utils.escaper import html_esc

    caption = f"""<b>{html_esc(images[0].title)}</b>
<a href="https://pixiv.net/artworks/{pid}">Source</a> by <a href="https://pixiv.net/users/{images[0].authorid}">Pixiv @{html_esc(images[0].author)}</a>
Tags: {" ".join(tags)}
{config.txt_msg_tail}
"""
    reply_msg = None
    if page_count > 1:
        media_group = []
        for i in range(page_count):
            if i == 0:
                media_group.append(
                    telegram.InputMediaPhoto(
                        images[i].thumburl,
                        caption,
                        parse_mode=ParseMode.HTML,
                        has_spoiler=True if images[i].r18 else False,
                    )
                )
            else:
                media_group.append(
                    telegram.InputMediaPhoto(
                        images[i].thumburl, has_spoiler=True if images[i].r18 else False
                    )
                )
        reply_msg = await context.bot.send_media_group(config.bot_channel, media_group)
        reply_msg = reply_msg[0]
    else:
        reply_msg = await context.bot.send_photo(
            config.bot_channel,
            images[0].thumburl,
            caption,
            parse_mode=ParseMode.HTML,
            has_spoiler=True if images[i].r18 else False,
        )

    if reply_msg:
        context.bot_data[reply_msg.id] = images
    print("\n\n"+str(context.bot_data[reply_msg.id])+"\n\n")

    msg += f"\n发送成功！"
    return msg


async def getArtworksWidthHeight(pid: int) -> list | None:
    import requests, json

    cookies = {"PHPSESSID": config.pixiv_phpsessid}
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(
            "https://www.pixiv.net/ajax/illust/112213666/pages",
            cookies=cookies,
            headers=headers,
        )
        logging.log(logging.INFO, response.context)
        return json.loads(response.context)["body"]
    except Exception as e:
        logging.log(logging.ERROR, e)
    return None
