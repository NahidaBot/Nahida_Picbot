import requests, json, os, logging, subprocess, re
from time import sleep

from retry import retry
from sqlalchemy import func

import telegram
from telegram import User
from telegram.constants import ParseMode

from config import config
from entities import Image
from utils.escaper import html_esc
from db import session

logger = logging.getLogger(__name__)

if not os.path.exists("./twitter/"):
    os.mkdir("./twitter/")


async def get_artworks(
    url: str, input_tags: list, user: User
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

    existing_image = session.query(Image).filter_by(pid=pid).first()
    if config.bot_deduplication_mode and existing_image:
        logger.warning("试图发送重复的图片: twitter" + pid)
        return (
            False,
            f"该图片已经由 @{existing_image.username} 于 {str(existing_image.create_time)[:-7]} 发过",
            None,
            None,
        )

    author = tweet_info["author"]
    tweet_content = tweet_info["content"]

    HASHTAG_PATTERN = r"""#[^\s!@#$%^&*(),.?":{}|<>]+"""
    tags = re.findall(HASHTAG_PATTERN, tweet_content)
    HASHTAG_PATTERN_SPACE = r"""(?:\s)?#[^\s!@#$%^&*(),.?":{}|<>]+(?:\s)?"""
    tweet_content = re.sub(HASHTAG_PATTERN_SPACE, "", tweet_content)

    tags = set(tags + input_tags)

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
                author=author["id"],
                authorid=author["name"],
                r18=True if image_json["possibly_sensitive"] else False,
                extension=extension,
                rawurl=image[1],
                thumburl=image[1].replace("orig", "large"),
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
    session.commit()
    page_count = len(images)

    msg = f"""获取成功！\n共有{page_count}张图片\n"""
    caption = f"""\
{html_esc(images[0].title)}
<a href="https://twitter.com/{author["name"]}/status/{pid}">Source</a> by <a href="https://twitter.com/{author["name"]}">twitter @{author["name"]}</a>
{" ".join(tags)}
"""

    return (True, msg, caption, images)
