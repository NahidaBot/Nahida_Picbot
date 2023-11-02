import requests
import json
import os
import logging
import subprocess
import re
from time import sleep

from retry import retry
from sqlalchemy import func

from telegram import User

from config import config
from entities import Image, ImageTag
from utils.escaper import html_esc
from utils import check_deduplication
from db import session

logger = logging.getLogger(__name__)

if not os.path.exists("./twitter/"):
    os.mkdir("./twitter/")


async def get_artworks(
    url: str, input_tags: list, user: User, post_mode: bool = True
) -> (bool, str, str, list[Image]):
    try:
        # 要执行的命令，包括 gallery-dl 命令和要下载的图库URL
        command = ["gallery-dl", url, "-j", "-q"]

        # 使用subprocess执行命令
        result: subprocess.CompletedProcess = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug(result.stdout)
        logger.debug("获取完成！")
    except subprocess.CalledProcessError as e:
        logger.error("获取出错:" + e)
        return (False, "获取失败! ", None, None)
    tweet_json: list[list] = json.loads(result.stdout)
    if len(tweet_json) <= 1:
        return (False, "推文中没有获取到图片", None, None)
    images = []
    tweet_info = tweet_json[0][1]
    pid = tweet_info["tweet_id"]

    existing_image = check_deduplication(pid)
    if post_mode and config.bot_deduplication_mode and existing_image:
        logger.warning("试图发送重复的图片: twitter" + str(pid))
        return (
            False,
            f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过",
            None,
            None,
        )

    author = tweet_info["author"]
    tweet_content = tweet_info["content"]
    page_count = len(images)
    msg = f"""获取成功！\n共有{page_count}张图片\n"""

    HASHTAG_PATTERN = r"""#[^\s!@#$%^&*(),.?":{}|<>]+"""
    HASHTAG_PATTERN_SPACE = r"""(?:\s)?#[^\s!@#$%^&*(),.?":{}|<>]+(?:\s)?"""
    tags = re.findall(HASHTAG_PATTERN, tweet_content)
    tweet_content = re.sub(HASHTAG_PATTERN_SPACE, "", tweet_content)

    input_tags: set[str] = set(tags + input_tags)
    r18 = tweet_info["possibly_sensitive"] or ("#NSFW" in tags)
    tags = set()
    for tag in input_tags:
        tags.add('#'+tag.lstrip('#'))
        image_tag = ImageTag(pid=pid, tag=tag)
        session.add(image_tag)
    if r18:
        tags.add("#NSFW")

    for image in tweet_json:
        if image[0] == 3:
            image_json = image[2]
            extension = image_json["extension"]
            img = Image(
                userid=user.id,
                username=user.username,
                platform="twitter",
                pid=pid,
                title=tweet_content,
                page=image_json["num"],
                author=author["name"],
                authorid=author["id"],
                r18=r18,
                extension=extension,
                rawurl=image[1],
                thumburl=image[1].replace("orig", "large"),
                guest=(not post_mode),
                width=image_json["width"],
                height=image_json["height"],
            )
            images.append(img)
            r = requests.get(img.rawurl)
            filename = f"{img.pid}_{img.page}.{extension}"
            file_path = f"./twitter/{filename}"
            with open(file_path, "wb") as f:
                f.write(r.content)
            img.size = os.path.getsize(file_path)
            img.filename = filename
            session.add(img)
            msg += f'第{image_json["num"]}张图片：{img.width}x{img.height}\n'
    session.commit()
    caption = (
        f"{html_esc(images[0].title)}\n"
        f'<a href="https://twitter.com/{author["name"]}/status/{pid}">Source</a> by <a href="https://twitter.com/{author["name"]}">twitter @{author["name"]}</a>\n'
        f'{" ".join(tags)}\n'
    )

    return (True, msg, caption, images)
