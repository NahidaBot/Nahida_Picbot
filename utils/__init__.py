import io
import logging
import os
import re
from typing import Optional
import PIL.Image
from db import session
from sqlalchemy import func
from entities import ArtworkParam, Image
from telegram import Message

logger = logging.getLogger(__name__)

MAX_SIDE = 2560
MAX_FILE_SIZE = 10 * 1024 * 1024


"""
转义标题、描述等字符串, 防止与 telegram markdown_v2 或 telegram html 符号冲突
"""


def md_esc(markdownv2_str: str) -> str:
    """
    Telegram 的 Markdown 格式, 只有 v2 才支持元素嵌套, 同时需要在正文中对以下字符进行额外的转义。
    详见：https://core.telegram.org/bots/api#formatting-options
    """
    chars = "_*[]()~`>#+-=|{}.!"
    for char in chars:
        markdownv2_str = markdownv2_str.replace(char, "\\" + char)
    return markdownv2_str


def html_esc(html_str: str) -> str:
    """
    Telegram 的 HTML 格式
    详见：https://core.telegram.org/bots/api#formatting-options
    """
    return html_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def compress_image(
    input_path: str, output_path: str, target_size_mb: int = 10, quality=100
) -> None:
    """
    Compress an image to the target size (in MB) to upload it.
    """
    # Open the image
    with PIL.Image.open(input_path) as img:
        # If the image has an alpha (transparency) channel, convert it to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size
        if (max_side := max(height, width)) > MAX_SIDE:
            logger.info("meet limits. resized.")
            scale_factor = MAX_SIDE / max_side
            img = img.resize(
                (int(width * scale_factor), int(height * scale_factor)),
                PIL.Image.LANCZOS,
            )

        # Check if the image size is already acceptable
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG", quality=quality)
        size = img_byte_arr.tell() / (1024 * 1024)  # Convert to MB

        # While the image size is larger than the target, reduce the quality
        while size > target_size_mb and quality > 10:
            print("size=" + str(size))
            quality -= 5
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="JPEG", quality=quality)
            size = img_byte_arr.tell() / (1024 * 1024)  # Convert to MB

        # Save the compressed image
        with open(output_path, "wb") as f_out:
            f_out.write(img_byte_arr.getvalue())


def is_within_size_limit(input_path: str) -> bool:
    size = os.path.getsize(input_path)
    if size >= MAX_FILE_SIZE:
        return False

    with PIL.Image.open(input_path) as img:
        width, height = img.size
        if max(height, width) > MAX_SIDE:
            return False
    return True


def check_duplication(pid: int | str) -> Image | None:
    image = session.query(Image).filter_by(pid=pid, post_by_guest=False).first()
    logger.debug(image)
    return image


def check_duplication_via_url(url: str) -> Image | None:
    image = session.query(Image).filter_by(url=url, post_by_guest=False).first()
    logger.debug(image)
    return image


def check_cache(pid: str, platform: str) -> Optional[list[Image]]:
    image = (
        session.query(Image)
        .filter_by(pid=pid, platform=platform)
        .order_by(Image.page)
        .group_by(Image.page)
        .all()
    )
    logger.debug(image)
    return image


def get_random_image() -> Image:
    return session.query(Image).order_by(func.random()).first()


def unmark_deduplication(pid: int | str) -> None:
    """
    反标记
    直接删除匹配 pid 的项 (
    """
    images_to_delete = session.query(Image).filter(Image.pid == str(pid)).all()

    # 删除查询到的数据
    for image in images_to_delete:
        session.delete(image)

    # 提交更改
    session.commit()


def find_url(message: Message) -> list[str]:
    logger.debug(message)
    logger.debug(message.entities)
    entities = message.entities if message.entities else message.caption_entities
    urls: list[str] = []
    text = message.text if message.text else message.caption
    for entity in entities:
        if entity.type == "text_link":
            logger.debug("\n-----\nfound text_link\n-----\n")
            logger.debug(msg=entity)
            urls.append(entity.url)
        if entity.type == "url":
            logger.debug("\n-----\nfound url\n-----\n")
            logger.debug(msg=entity)
            urls.append(text[entity.offset : entity.offset + entity.length])
    return urls


def parse_page_ranges(page_ranges: str) -> list[int]:
    pages: set[int] = set()
    ranges = page_ranges.split(",")

    for r in ranges:
        if "-" in r:
            start, end = map(int, r.split("-"))
            pages.update(range(start, end + 1))
        else:
            pages.add(int(r))

    return sorted(pages)


def prase_params(words: list[str]) -> ArtworkParam:
    # TODO
    params = ArtworkParam()
    for word in words:
        if "#" in word:
            params.input_tags.append(word)
        elif "=" in word:
            key, value = word.split("=")
            if "p" in key:
                # pages
                params.pages = parse_page_ranges(value)
            elif "tag" in key:
                value = value.replace("，", ",")
                params.input_tags += value.split(",")
            elif "f" in key or "v" in key:
                # from / via
                word = word.split("=")[-1]
                if "t.me" in value:
                    params.source_from_channel = word
                elif "@" in value:
                    params.source_from_username = word
                # elif value.isdigit():
                #     params.source_from_userid = word
            # elif 'upscale' in key:
            #     params.upscale = int(value)
            elif "silent" in key or "s=" in word:
                params.silent = "t" in value.lower()
            elif "spoiler" in key or "s=" in word:
                params.silent = "t" in value.lower()
            elif "nsfw" in key.lower():
                params.is_NSFW = "t" in value.lower()
            elif "sfw" in key.lower():
                params.is_NSFW = "f" in value.lower()
        elif "silent" in word:
            params.silent = True
        elif "spoiler" in word:
            params.spoiler = True
        elif "nsfw" in word.lower():
            params.is_NSFW = True
        elif "sfw" in word.lower():
            params.is_NSFW = False
    return params


def get_source_str(artwork_param: ArtworkParam) -> str:
    s = ""
    if artwork_param.source_from_channel:
        reg = re.compile(
            r"^(?:https?:\/\/)?(?:www\.)?t.me\/([A-Za-z0-9_]+)\/?(?:\d+)?\/?$"
        )
        try:
            channel_name: str = reg.split(artwork_param.source_from_channel)[1]
        except Exception as e:
            logger.error("在正则匹配时发生了一个错误")
            return s
        s = f'from <a href="{artwork_param.source_from_channel}">@{channel_name}</a> '
    if artwork_param.source_from_username:
        s += f"via {artwork_param.source_from_username}"
    return s
