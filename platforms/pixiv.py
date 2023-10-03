from pixivpy3 import *
from config import config
from entities import Image, ImageTag
from telegram import User
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from db import session
from sqlalchemy import func
import logging, telegram
from retry import retry
import os

if not os.path.exists("./Pixiv/"):
    os.mkdir("./Pixiv/")

api = AppPixivAPI()
api.set_accept_language("zh-cn")
api.auth(refresh_token=config.pixiv_refresh_token)

logger = logging.getLogger(__name__)

# TODO 注意，ImageTags尚未启用


def refresh_token() -> None:
    api.auth(refresh_token=config.pixiv_refresh_token)
    from time import sleep

    sleep(1)


@retry(tries=3)
def get_illust(pid: int | str) -> None:
    try:
        illust = api.illust_detail(pid)["illust"]
        return illust
    except Exception as e:
        logger.error("获取失败，可能是Pixiv_refresh_token过期，正在尝试刷新")
        refresh_token()
        raise e


async def get_artworks(
    url: str, input_tags: list, user: User, context: ContextTypes.DEFAULT_TYPE
) -> str:
    pid = url.strip("/").split("/")[-1]  # 取 PID

    illust = get_illust(pid)

    translated_tags = await get_translated_tags(illust["tags"])
    page_count = illust["page_count"]

    existing_image = session.query(Image).filter_by(pid=pid).first()
    if config.bot_deduplication_mode and existing_image:
        logger.warning("试图发送重复的图片: Pixiv" + pid)
        return f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过"

    meta_pages = illust["meta_pages"]

    image_width_height_info = await get_artworks_width_height(pid)
    msg = f"""获取成功！
<b>{illust["title"]}</b>
共有{page_count}张图片
"""
    images: list[Image] = []

    for tag in translated_tags:
        image_tag = ImageTag(pid=pid, tag=tag)
        session.add(image_tag)

    for i in range(page_count):
        img = Image(
            userid=user.id,
            username=user.username,
            platform="Pixiv",
            pid=pid,
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
<a href="https://www.pixiv.net/artworks/{pid}">Source</a> by <a href="https://www.pixiv.net/users/{images[0].authorid}">Pixiv @{html_esc(images[0].author)}</a>
{" ".join(input_tags if input_tags else translated_tags)}
{config.txt_msg_tail}
"""
    reply_msg = None
    if page_count > 1:
        media_group = []
        for i in range(page_count):
            file_path = f"./Pixiv/{images[i].rawurl.split('/')[-1]}"
            logger.debug(file_path)
            file_size = os.path.getsize(file_path)
            if file_size >= (1024 * 1024 * 10 - 1024):
                file_path = images[i].thumburl
            with open(file_path, "rb") as f:
                if i == 0:
                    media_group.append(
                        telegram.InputMediaPhoto(
                            f,
                            caption,
                            parse_mode=ParseMode.HTML,
                            has_spoiler=True if images[i].r18 else False,
                        )
                    )
                else:
                    media_group.append(
                        telegram.InputMediaPhoto(
                            f,
                            has_spoiler=True if images[i].r18 else False,
                        )
                    )
        logger.debug(media_group)
        reply_msg = await context.bot.send_media_group(config.bot_channel, media_group)
        reply_msg = reply_msg[0]
    else:
        file_path = f"./Pixiv/{images[0].rawurl.split('/')[-1]}"
        logger.debug(file_path)
        file_size = os.path.getsize(file_path)
        if file_size >= (1024 * 1024 * 10 - 1024):
            file_path = images[0].thumburl
        logger.debug(images[0])
        with open(file_path, "rb") as f:
            reply_msg = await context.bot.send_photo(
                config.bot_channel,
                f,
                caption,
                parse_mode=ParseMode.HTML,
                has_spoiler=True if images[i].r18 else False,
            )

    if reply_msg:
        context.bot_data[reply_msg.id] = images
    logger.info(str(context.bot_data[reply_msg.id]))

    msg += f"\n发送成功！"
    return msg


async def get_artworks_width_height(pid: int) -> list | None:
    import requests, json

    cookies = {"PHPSESSID": config.pixiv_phpsessid}
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(
            f"https://www.pixiv.net/ajax/illust/{pid}/pages",
            cookies=cookies,
            headers=headers,
        )
        logger.info(response.content)
        return json.loads(response.content)["body"]
    except Exception as e:
        logger.error("在请求Pixiv Web API的时候发生了一个错误")
        logger.error(e)
    return None


async def get_translated_tags(tags: list[dict[str, str]]) -> list[str]:
    logger.debug(tags)
    CHINESE_REGEXP = "[一-龥]"
    # https://github.com/xuejianxianzun/PixivBatchDownloader/blob/397c16670bb480810d93bba70bb784bd0707bdee/src/ts/Tools.ts#L399
    # 如果用户在 Pixiv 的页面语言是中文，则应用优化策略
    # 如果翻译后的标签是纯英文，则判断原标签是否含有至少一部分中文，如果是则使用原标签
    # 这是为了解决一些中文标签被翻译成英文的问题，如 原神 被翻译为 Genshin Impact
    # 能代(アズールレーン) Noshiro (Azur Lane) 也会使用原标签
    # 但是如果原标签里没有中文则依然会使用翻译后的标签，如 フラミンゴ flamingo
    use_origin_tag = True
    translated_tags = []
    import re

    for tag in tags:
        if tag["translated_name"]:
            use_origin_tag = False
            if tag["translated_name"].isascii():
                if re.match(CHINESE_REGEXP, tag["name"]):
                    use_origin_tag = True
        ptn = r"""[!"$%&'()*+,-./:;<=>?@[\]^`{|}~．！？｡。＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､　、〃〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏﹑﹔·]"""
        tag = (tag["name"] if use_origin_tag else tag["translated_name"]).replace(
            " ", "_"
        )
        tag = re.sub(ptn, "", tag)
        translated_tags.append("#" + tag)
    logger.debug(translated_tags)
    return translated_tags
