import os
import logging

from telegram import User
import requests

from config import config
from entities import Image, ImageTag
from utils.escaper import html_esc
from utils import check_deduplication
from db import session

logger = logging.getLogger(__name__)

platform = "bilibili"
download_path = f"./downloads/{platform}/"


if not os.path.exists(download_path):
    os.mkdir(download_path)


async def get_post(post_id: int | str) -> dict:
    headers = {
        "referer": "https://t.bilibili.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    }
    url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?timezone_offset=-480&platform=web&id={post_id}&features=itemOpusStyle"
    try:
        response = requests.get(
            url,
            headers=headers,
        )
        logger.info(response.content)
        j = response.json()
        if j["code"] == 0 and j["data"]["item"]["type"] == "DYNAMIC_TYPE_DRAW":
            return j["data"]["item"]["modules"]
        else:
            logger.error(j)
    except Exception as e:
        logger.error("在请求 bilibili Web API 时发生了一个错误")
        logger.error(e)
    return None


async def download(url: str, path: str, filename: str) -> bool:
    if os.path.exists(path + filename):
        return True
    try:
        req = requests.get(url)
        with open(path + filename, "wb") as f:
            f.write(req.content)
        return True
    except Exception as e:
        logger.error("在下载 bilibili 图片时发生了一个错误")
        logger.error(e)
    return False


async def get_artworks(
    url: str, input_tags: list, user: User, post_mode: bool = True
) -> (bool, str, str, list[Image]):
    """
    只有 post_mode 和 config.bot_deduplication_mode 都为 True, 才检测重复
    """
    id = url.strip("/").split("/")[-1]

    post_json = await get_post(id)
    image_list: list = post_json["module_dynamic"]["major"]["opus"]["pics"]
    author_info = post_json["module_author"]
    author = author_info["name"]
    authorid = author_info["mid"]
    page_count = len(image_list)
    title = post_json["module_dynamic"]["major"]["opus"]["summary"]["text"]
    r18 = False
    msg = f"获取成功！\n" f"<b>{title}</b>\n" f"共有{page_count}张图片\n"

    existing_image = check_deduplication(id)
    if post_mode and config.bot_deduplication_mode and existing_image:
        logger.warning(f"试图发送重复的图片: {platform}" + str(id))
        user = User(existing_image.userid, existing_image.username, is_bot=False)
        return (
            False,
            f"该图片已经由 {user.mention_html()} 于 {str(existing_image.create_time)[:-7]} 发过",
            None,
            None,
        )

    tags: set[str] = set()
    for tag in input_tags:
        tag = "#" + tag.strip("#")
        image_tag = ImageTag(pid=id, tag=tag)
        session.add(image_tag)
        tags.add(tag)

    images: list[Image] = []
    for i in range(page_count):
        extension: str = image_list[i]["url"].split("/")[-1].split(".")[-1]
        filename: str = f"{id}_{i+1}.{extension}"
        size = int(image_list[i]["size"] * 1024)
        await download(image_list[i]["url"], download_path, filename)
        image = Image(
            userid=user.id,
            username=user.name,
            platform=platform,
            pid=id,
            title=title,
            page=i,
            size=size,
            filename=filename,
            author=author,
            authorid=authorid,
            r18=r18,
            extension=extension,
            rawurl=image_list[i]["url"],
            thumburl=image_list[i]["url"],
            guest=(not post_mode),
            width=image_list[i]["width"],
            height=image_list[i]["height"],
        )
        images.append(image)
        session.add(image)
        msg += f"第{i+1}张图片：{image.width}x{image.height}\n"
    session.commit()

    post_url = f"https://www.bilibili.com/opus/{id}"
    author_url = f"https://space.bilibili.com/{authorid}"

    caption = (
        f"{html_esc(title)}\n"
        f'<a href="{post_url}">Source</a> by <a href="{author_url}">{platform} @{html_esc(author)}</a>\n'
    )
    if tags:
        caption += f'{" ".join(tags)}\n'

    return (True, msg, caption, images)
