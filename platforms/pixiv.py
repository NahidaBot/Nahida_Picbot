import os
import re
import requests
import logging
from time import sleep

from pixivpy3 import *
from retry import retry
from sqlalchemy import func

import telegram
from telegram import User
from telegram.constants import ParseMode

from config import config
from entities import Image, ImageTag
from utils.escaper import html_esc
from utils import check_deduplication
from db import session

platform = "Pixiv"
download_path = f"./downloads/{platform}/"

if not os.path.exists(download_path):
    os.mkdir(download_path)

api = AppPixivAPI()
api.set_accept_language("zh-cn")
api.auth(refresh_token=config.pixiv_refresh_token)

logger = logging.getLogger(__name__)


def refresh_token() -> None:
    api.auth(refresh_token=config.pixiv_refresh_token)
    sleep(1)


@retry(tries=3)
def get_illust(pid: int | str) -> dict:
    try:
        illust = api.illust_detail(pid)["illust"]
        logger.debug(illust)
        return illust
    except Exception as e:
        logger.error("获取失败, 可能是 Pixiv_refresh_token 过期, 正在尝试刷新")
        refresh_token()
        raise e


async def get_artworks(
    url: str, input_tags: list[str], user: User, post_mode: bool = True
) -> (bool, str, str, list[Image]):
    """
    只有 post_mode 和 config.bot_deduplication_mode 都为 True, 才检测重复
    """
    pid = url.strip("/").split("/")[-1]  # 取 PID

    illust = get_illust(pid)

    page_count = illust["page_count"]

    existing_image = check_deduplication(pid)
    if post_mode and config.bot_deduplication_mode and existing_image:
        logger.warning(f"试图发送重复的图片: {platform}" + str(pid))
        return (
            False,
            f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过",
            None,
            None,
        )

    image_width_height_info = await get_artworks_width_height(pid)
    msg = f"获取成功！\n" f'<b>{illust["title"]}</b>\n' f"共有{page_count}张图片\n"

    images: list[Image] = []
    r18: bool = illust["x_restrict"] == 1 or ("#NSFW" in input_tags)

    # tag 处理
    if not input_tags:
        input_tags: list[str] = await get_translated_tags(illust["tags"])
    tags: set = set()
    for tag in input_tags:
        tag = "#" + tag.lstrip("#")
        image_tag = ImageTag(pid=pid, tag=tag)
        session.add(image_tag)
        tags.add(tag)
    # if r18:
    #     tags.add("#NSFW")
    if illust["illust_ai_type"]:
        tags.add("AI")

    meta_pages = illust["meta_pages"]
    for i in range(page_count):
        if page_count > 1:
            rawurl: str = meta_pages[i]["image_urls"]["original"]
        else:
            rawurl: str = illust["meta_single_page"]["original_image_url"]
        api.download(rawurl, path=download_path)
        filename = rawurl.split("/")[-1]
        file_path = f"./downloads/{platform}/{filename}"
        file_size = os.path.getsize(file_path)
        img = Image(
            userid=user.id,
            username=user.username,
            platform=platform,
            pid=pid,
            title=illust["title"],
            page=i,
            size=file_size,
            filename=filename,
            author=illust["user"]["name"],
            authorid=illust["user"]["id"],
            r18=r18,
            extension=rawurl.split(".")[-1],
            rawurl=rawurl,
            thumburl=meta_pages[i]["image_urls"]["large"]
            if page_count > 1
            else illust["image_urls"]["large"],
            guest=(not post_mode),
        )
        if image_width_height_info:
            logger.debug(image_width_height_info)
            img.width = image_width_height_info[i]["width"]
            img.height = image_width_height_info[i]["height"]
            msg += f"第{i+1}张图片：{img.width}x{img.height}\n"
        images.append(img)
        session.add(img)
    session.commit()

    caption = (
        f"<b>{html_esc(images[0].title)}</b>\n"
        f'<a href="https://www.pixiv.net/artworks/{pid}">Source</a> by <a href="https://www.pixiv.net/users/{images[0].authorid}">Pixiv @{html_esc(images[0].author)}</a>\n'
        f'{" ".join(tags)}\n'
    )

    return (True, msg, caption, images)


async def get_artworks_width_height(pid: int) -> list | None:
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
        return response.json()["body"]
    except Exception as e:
        logger.error("在请求 Pixiv Web API 时发生了一个错误")
        logger.error(e)
    return None


async def get_translated_tags(tags: list[dict[str, str]]) -> list[str]:
    PUNCTUATION_PATTERN = r"""[!"$%&'()*+,-./:;<=>?@[\]^`{|}~．！？｡。＂＃＄％＆＇（）＊＋, －／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､　、〃〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏﹑﹔·]"""
    logger.debug(tags)
    CHINESE_REGEXP = "[一-龥]"
    # https://github.com/xuejianxianzun/PixivBatchDownloader/blob/397c16670bb480810d93bba70bb784bd0707bdee/src/ts/Tools.ts#L399
    # 如果用户在 Pixiv 的页面语言是中文, 则应用优化策略
    # 如果翻译后的标签是纯英文, 则判断原标签是否含有至少一部分中文, 如果是则使用原标签
    # 这是为了解决一些中文标签被翻译成英文的问题, 如 原神 被翻译为 Genshin Impact
    # 能代(アズールレーン) Noshiro (Azur Lane) 也会使用原标签
    # 但是如果原标签里没有中文则依然会使用翻译后的标签, 如 フラミンゴ flamingo
    use_origin_tag = True
    translated_tags = []

    for tag in tags:
        if "users入り" in tag["name"]:
            continue
        if tag["translated_name"]:
            use_origin_tag = False
            if tag["translated_name"].isascii():
                if re.match(CHINESE_REGEXP, tag["name"]):
                    use_origin_tag = True
        tag = tag["name"] if use_origin_tag else tag["translated_name"]
        if tag:
            if len(tag.split()) > 3:
                # 防止出现过长的英文标签
                continue
            tag = (tag).replace(" ", "_")
            tag = re.sub(PUNCTUATION_PATTERN, "", tag)
            translated_tags.append("#" + tag)
    logger.debug(translated_tags)
    return translated_tags
