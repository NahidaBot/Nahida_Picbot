import json
import os
import logging
from typing import Any

from telegram import User

from entities import Image, ImageTag, ArtworkResult
from utils import get_source_str, html_esc
from db import session
from .default import DefaultPlatform

logger = logging.getLogger(__name__)


class Twitter(DefaultPlatform):

    platform = "twitter"
    download_path = f"{DefaultPlatform.base_downlad_path}/{platform}/"
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    @classmethod
    async def get_images(
        cls, 
        user: User, 
        post_mode: bool, 
        page_count: int, 
        artwork_info: list[list[Any]], 
        artwork_meta: dict[str, Any], 
        artwork_result: ArtworkResult
    ) -> list[Image]:
        pid: str = artwork_meta["tweet_id"]
        if existing_images := cls.check_cache(pid, post_mode, user):
            artwork_result.cached = True
            return existing_images
        images: list[Image] = []
        pages = list(range(1, page_count + 1))
        if artwork_result.artwork_param.pages is not None:
            pages = artwork_result.artwork_param.pages
        is_nsfw: bool = artwork_result.is_NSFW or artwork_meta["sensitive"]
        if artwork_result.artwork_param.is_NSFW is not None:
            is_nsfw = artwork_result.artwork_param.is_NSFW
        for i in pages:
            image = artwork_info[i]
            if image[0] == 3:
                image_info: dict[str,Any] = image[2]
                img = Image(
                    userid=user.id,
                    username=user.name,
                    platform=cls.platform,
                    pid=pid,
                    title=artwork_meta["content"],
                    page=i,
                    author=artwork_meta["user"]["name"],
                    authorid=artwork_meta["user"]["id"],
                    r18=is_nsfw,
                    extension=image_info["extension"],
                    size=None,
                    url_original_pic=image[1],
                    url_thumb_pic=image[1]
                    .replace("orig", "large")
                    .replace("png", "jpg"),
                    post_by_guest=(not post_mode),
                    width=image_info["width"],
                    height=image_info["height"],
                    ai=artwork_result.is_AIGC,
                    full_info=json.dumps(image_info),
                )
                img.filename = f"{img.pid}_{img.page}.{img.extension}"
                images.append(img)
                session.add(img)
                artwork_result.feedback += f"第{i}张图片：{img.width}x{img.height}\n"
        logger.debug(images)
        return images

    @classmethod
    def get_caption(cls, artwork_result: ArtworkResult, artwork_meta: dict[str, Any]) -> ArtworkResult:
        tweet_id = artwork_result.images[0].pid
        tweet_author = artwork_result.images[0].author
        tweet_author_url = f"https://twitter.com/{tweet_author}"
        tweet_url = f"{tweet_author_url}/status/{tweet_id}"
        tags = f'{" ".join(artwork_result.tags)}'
        source_str = ''
        if s := get_source_str(artwork_result.artwork_param):
            source_str += s + '\n'
        artwork_result.caption = (
            f'<a href="{tweet_url}">Source</a>'
            f' by <a href="{tweet_author_url}">twitter @{tweet_author}</a>\n'
            f'{source_str}'
            f'{tags+'\n' if tags else ''}'
            f"<blockquote expandable>{html_esc(artwork_result.images[0].title)}</blockquote>\n"
        )
        logger.debug(artwork_result)
        return artwork_result

    @classmethod
    async def get_tags(
        cls,
        input_tags: list[str],
        artwork_meta: dict[str, Any],
        artwork_result: ArtworkResult,
    ) -> ArtworkResult:
        # twitter tag 一般情况下完全符合 telegram hashtag 规则
        artwork_result.raw_tags = artwork_meta.get("hashtags") or list()

        tweet_id = artwork_result.images[0].pid

        input_set: set[str] = set()
        for tag in input_tags:
            if len(tag) <= 4:
                tag = tag.upper()
            tag = "#" + html_esc(tag.lstrip("#"))
            input_set.add(tag)
            if not artwork_result.cached:
                session.add(ImageTag(pid=tweet_id, tag=tag))

        all_tags = input_set & set(artwork_result.raw_tags)
        artwork_result.is_AIGC = "#AI" in all_tags
        artwork_result.is_NSFW = (
            artwork_meta["sensitive"]
            or ("#R18" in all_tags)
            or ("#R-18" in all_tags)
            or ("#NSFW" in all_tags)
        )
        artwork_result.tags = sorted(input_set)
        logger.debug(artwork_result)
        return artwork_result
