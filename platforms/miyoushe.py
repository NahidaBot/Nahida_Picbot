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

platform = "miyoushe"
download_path = f"./{platform}/"


if not os.path.exists(download_path):
    os.mkdir(download_path)


async def get_post(post_id: int | str) -> dict:
    headers = {
        "referer": "https://www.miyoushe.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(
            f"https://bbs-api.miyoushe.com/post/wapi/getPostFull?post_id={
                post_id}",
            headers=headers,
        )
        logger.info(response.content)
        j = response.json()
        if j["retcode"] == 0:
            return j["data"]["post"]
        else:
            logger.error(j)
    except Exception as e:
        logger.error("在请求米游社 Web API 时发生了一个错误")
        logger.error(e)
    return None


async def download(url: str, path: str, filename: str) -> bool:
    try:
        req = requests.get(url)
        with open(path+filename, "wb") as f:
            f.write(req.content)
        return True
    except Exception as e:
        logger.error("在下载米游社图片时发生了一个错误")
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
    image_list: list = post_json["image_list"]
    post_info = post_json["post"]
    page_count = len(image_list)
    title = post_info["subject"]
    r18 = False
    x_oss_process = "?x-oss-process=image//resize,l_2560/quality,q_100/auto-orient,0/interlace,1/format,jpg"
    msg = (f'获取成功！\n'
           f'<b>{title}</b>\n'
           f'共有{page_count}张图片\n')

    existing_image = check_deduplication(id)
    if post_mode and config.bot_deduplication_mode and existing_image:
        logger.warning(f"试图发送重复的图片: {platform}" + str(id))
        return (
            False,
            f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过",
            None,
            None,
        )

    tag_game, url_path = get_game(post_info)
    tags: set = set(input_tags)
    tags.add(tag_game)
    for tag in input_tags:
        image_tag = ImageTag(pid=id, tag=tag)
        session.add(image_tag)

    images: list[Image] = []
    for i in range(page_count):
        filename = f"{image_list[i]["image_id"]}.{image_list[i]["format"]}"
        await download(image_list[i]["url"], download_path, filename)
        image = Image(
            userid=user.id,
            username=user.username,
            platform=platform,
            pid=id,
            title=title,
            page=i,
            size=image_list[i]['size'],
            filename=filename,
            author=post_json["user"]["nickname"],
            authorid=post_json["user"]["uid"],
            r18=r18,
            extension=image_list[i]["format"],
            rawurl=image_list[i]["url"],
            thumburl=image_list[i]["url"]+x_oss_process,
            guest=(not post_mode),
            width=image_list[i]["width"],
            height=image_list[i]["height"]
        )
        images.append(image)
        session.add(image)
        msg += f"第{i+1}张图片：{image.width}x{image.height}\n"
    session.commit()

    caption = (
        f'<b>{html_esc(images[0].title)}</b>\n'
        f'<a href="https://www.miyoushe.com/{url_path}/article/{id}">Source</a> by <a href="https://www.miyoushe.com/{url_path}/accountCenter/postList?id={images[0].authorid}">米游社 @{html_esc(images[0].author)}</a>\n'
        f'{" ".join(input_tags)}\n'
    )

    return (True, msg, caption, images)


def get_game(post_info: dict) -> tuple[str]:
    game_id = post_info["game_id"]
    name = ""
    match game_id:
        case 1:
            name = "崩坏3"
            url_path = "bh3"
        case 2:
            name = "原神"
            url_path = "ys"
        case 3:
            name = "崩坏学园2"
            url_path = "bh2"
        case 4:
            name = "未定事件簿"
            url_path = "wd"
        case 6:
            name = "星铁"
            url_path = "sr"
        case 7:
            name = "大别野"
            url_path = "dby"
        case 8:
            name = "绝区零"
            url_path = "zzz"
    return name, url_path