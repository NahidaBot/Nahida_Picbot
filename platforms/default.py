import asyncio
from datetime import datetime
import json
import os
import logging
import subprocess
from typing import Any, Optional

import httpx
from telegram import User

from config import config
from entities import Image, ImageTag, ArtworkResult
from utils import check_duplication_via_url, check_cache, html_esc
from db import session

logger = logging.getLogger(__name__)

class GetArtInfoError(Exception):
    pass


class DefaultPlatform:

    platform = "default"
    base_downlad_path = f"./data/downloads"
    download_path = f"{base_downlad_path}/{platform}/"
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    @classmethod
    async def get_info_from_gallery_dl(cls, url: str) -> list[list[Any]]:
        try:
            # 要执行的命令, 包括 gallery-dl 命令和要下载的图库URL
            command = ["gallery-dl", url, "-j", "-q"]

            # 使用subprocess执行命令
            result: subprocess.CompletedProcess[str] = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.debug(result.stdout)
            logger.debug(f"获取 {cls.platform} 平台图片完成！")
            return json.loads(result.stdout)
        except Exception as e:
            logger.error(e)
            raise GetArtInfoError(f"获取 {cls.platform} 平台图片出错！")
    
    @classmethod
    async def check_duplication(cls, artwork_info: list[list[Any]], user: User, post_mode: bool) -> ArtworkResult:
        if post_mode and config.bot_deduplication_mode:
            existing_image = check_duplication_via_url(artwork_info[1][1])
            if existing_image:
                logger.warning(f"试图发送重复的图片: {cls.platform}" + existing_image)
                user = User(existing_image.userid, existing_image.username, is_bot=False)
                return ArtworkResult(
                    False,
                    f"该图片已经由 {user.mention_html()} 于 {str(existing_image.create_time)[:-7]} 发过"
                )
        return ArtworkResult(True)
    
    @classmethod
    def check_cache(cls, pid: str, post_mode: bool, user: User) -> Optional[list[Image]]:
        existing_images =  check_cache(pid, cls.platform)
        if existing_images:
            for image in existing_images:
                image.create_time = datetime.now()
                image.post_count += 1
                if image.post_by_guest or post_mode:
                    if post_mode:
                        image.post_by_guest = False
                    image.username = user.username
                    image.userid = user.id
            return existing_images
    
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
        pid: str = artwork_meta["id"]
        if existing_images := cls.check_cache(pid, post_mode, user):
            artwork_result.cached = True
            return existing_images
        images: list[Image] = []
        for i in range(page_count):
            image = artwork_info[i+1]
            if image[0] == 3:
                image_info: dict[str,Any] = image[2]
                extension = artwork_meta.get("extension") or artwork_meta.get("file_ext")
                img = Image(
                    userid=user.id,
                    username=user.name,
                    platform=cls.platform,
                    pid=pid,
                    title=artwork_meta.get("title") or artwork_meta.get("tweet_content") or artwork_meta.get("id"),
                    page=(i+1),
                    author=artwork_meta.get("author"),
                    authorid=(
                        artwork_meta.get("pixiv_id")
                        or artwork_meta.get("uploader_id") 
                        or artwork_meta.get("approver_id") 
                        or artwork_meta.get("creator_id") 
                        or (artwork_meta.get("user") and artwork_meta.get("user").get("id")) # type: ignore
                    ),
                    r18=artwork_result.is_NSFW,
                    extension=extension or image_info.get("extension") or image_info.get("file_ext"),
                    size=image_info.get("file_size"),
                    url_original_pic=image[1],
                    url_thumb_pic=image_info.get("jpeg_url") or image_info.get("sample_url") or image[1],
                    post_by_guest=(not post_mode),
                    width=image_info.get("width") or image_info.get("image_width"),
                    height=image_info.get("height") or image_info.get("image_height"),
                    ai=artwork_result.is_AIGC,
                    full_info=json.dumps(image_info),
                )
                img.filename = f"{img.pid}_{img.page}.{img.extension}"
                images.append(img)
                session.add(img)
                artwork_result.feedback += f'第{i+1}张图片：{img.width}x{img.height}\n'
        return images

    @classmethod
    async def download_image(cls, image: Image, refer: str = "") -> None:
        async with httpx.AsyncClient(http2=True) as client:
            headers = {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            }
            if refer:
                headers["referer"] = refer
            response = await client.get(image.url_original_pic, headers=headers, timeout=60)
            response.raise_for_status()
            file_path = cls.download_path + image.filename
            if os.path.exists(file_path):
                return
            with open(file_path, 'wb') as f:
                f.write(response.content)
            logger.debug(f"已下载：{image.filename}")
            if not image.size:
                image.size = os.path.getsize(file_path)

    @classmethod
    async def get_artworks(
        cls, url: str, input_tags: list[str], user: User, post_mode: bool = True
    ) -> ArtworkResult:
        try:
            artwork_info = await cls.get_info_from_gallery_dl(url)

            artwork_result = await cls.check_duplication(artwork_info, user, post_mode)
            if not artwork_result.success:
                return artwork_result

            page_count = len(artwork_info) - 1
            artwork_result.feedback = f"""获取成功！\n共有{page_count}张图片\n"""

            artwork_meta: dict[str, Any] = artwork_info[0][-1]

            artwork_result.images = await cls.get_images(user, post_mode, page_count, artwork_info, artwork_meta, artwork_result)
            artwork_result = await cls.get_tags(input_tags, artwork_meta, artwork_result)

            if not artwork_result.cached:
                tasks = [asyncio.create_task(cls.download_image(image)) for image in artwork_result.images]
                await asyncio.wait(tasks)
            
            # session.commit() # 移至 command handler 发出 Image Group 之后
            artwork_result = cls.get_caption(artwork_result, artwork_meta)
            artwork_result.success = True
            return artwork_result
        except:
            return ArtworkResult(False, "出错了呜呜呜，对不起主人喵，没能成功获取到图片")

    @classmethod
    def get_caption(cls, artwork_result: ArtworkResult, artwork_meta: dict[str, Any]) -> ArtworkResult:
        caption = ''
        if artwork_meta.get("title"):
            caption += f"<blockquote>{html_esc(artwork_meta.get("title"))}</blockquote>\n" # type: ignore
        if artwork_result.tags:
            caption += f'Tags: {" ".join(artwork_result.tags)}\n'
        if artwork_result.raw_tags:
            caption += f'<blockquote expandable>Raw Tags: {" ".join(artwork_result.raw_tags)}</blockquote>\n'
        artwork_result.caption = caption
        return artwork_result
        

    @classmethod
    async def get_tags(cls, input_tags: list[str], artwork_meta: dict[str, Any], artwork_result: ArtworkResult) -> ArtworkResult:
        raw_tags: list[str] = artwork_meta.get("tags", [])
        raw_tags += artwork_meta.get("characters", [])
        raw_tags += artwork_meta.get("artist", [])
        raw_tags += artwork_meta.get("type", [])
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split()
        
        input_set: set[str] = set()
        for tag in input_tags:
            if len(tag) <= 4:
                tag = tag.upper()
            tag = "#" + html_esc(tag.lstrip("#"))
            input_set.add(tag)

            if not artwork_result.cached:
                session.add(
                    ImageTag(
                        pid=artwork_meta.get("id") or artwork_meta.get("media_id"), 
                        tag=tag
                ))
        
        raw_tags_set: set[str] = set()
        for tag in raw_tags:
            if len(tag) <= 3:
                tag = tag.upper()
            # 切分长词
            # if len(tag.split()) > 3:
            #     raw_tags.append(tag.split())
            tag = tag.replace(" ", "_")
            tag = tag.replace("-", "_")
            raw_tags_set.add("#" + html_esc(tag.lstrip("#")))
            
        all_tags = input_set & raw_tags_set
        artwork_result.is_AIGC = "#AI" in all_tags
        artwork_result.is_NSFW = ("#R18" in all_tags) or ("#R-18" in all_tags) or ("#NSFW" in all_tags)
        artwork_result.tags = sorted(input_set)
        artwork_result.raw_tags = sorted(raw_tags_set)
        return artwork_result
