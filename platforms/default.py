import requests
import json
import os
import logging
import subprocess

from retry import retry
from sqlalchemy import func

from telegram import User

from config import config
from entities import Image, ImageTag, ArtworkResult
from utils.escaper import html_esc
from utils import check_deduplication_via_url
from db import session

logger = logging.getLogger(__name__)

class GetArtInfoError(Exception):
    pass


class DefaultPlatform:

    platform = "default"
    download_path = f"./downloads/{platform}/"
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    @classmethod
    async def get_info_from_gallery_dl(cls, url: str) -> list[list]:
        try:
            # 要执行的命令, 包括 gallery-dl 命令和要下载的图库URL
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
            logger.debug(f"获取 {cls.platform} 平台图片完成\！")
            return json.loads(result.stdout)
        except Exception as e:
            logger.error(e)
            raise GetArtInfoError(f"获取 {cls.platform} 平台图片出错\！")
    
    @classmethod
    async def get_artworks(
        cls, url: str, input_tags: list, user: User, post_mode: bool = True
    ) -> ArtworkResult:
        try:
            artwork_info = await cls.get_info_from_gallery_dl(url)

            if post_mode and config.bot_deduplication_mode:
                existing_image = check_deduplication_via_url(artwork_info[1][1])
                if existing_image:
                    logger.warning(f"试图发送重复的图片: {cls.platform}" + existing_image)
                    user = User(existing_image.userid, existing_image.username, is_bot=False)
                    return ArtworkResult(
                        False,
                        f"该图片已经由 {user.mention_html()} 于 {str(existing_image.create_time)[:-7]} 发过"
                    )

            page_count = len(artwork_info) - 1
            msg = f"""获取成功！\n共有{page_count}张图片\n"""

            artwork_result = await cls.get_tags(input_tags, artwork_info)
            artwork_meta: dict = artwork_info[0][-1]
            images = []

            for i in range(page_count):
                image = artwork_info[i+1]
                if image[0] == 3:
                    image_info: dict = image[2]
                    extension = artwork_meta.get("extension") or artwork_meta.get("file_ext")
                    img = Image(
                        userid=user.id,
                        username=user.name,
                        platform=cls.platform,
                        pid=artwork_meta.get("id"),
                        title=artwork_meta.get("title") or artwork_meta.get("tweet_content") or artwork_meta.get("id"),
                        page=(i+1),
                        author=artwork_meta.get("author"),
                        authorid=(
                            artwork_meta.get("pixiv_id")
                            or artwork_meta.get("uploader_id") 
                            or artwork_meta.get("approver_id") 
                            or artwork_meta.get("creator_id") 
                            or artwork_meta.get("creator_id") 
                            or artwork_meta.get("creator_id") 
                            or artwork_meta.get("user").get("id")
                        ),
                        r18=artwork_result.is_NSFW,
                        extension=extension or image_info.get("extension") or image_info.get("file_ext"),
                        url_original_pic=image[1],
                        url_thumb_pic=image_info.get("jpeg_url") or image_info.get("sample_url") or image[1],
                        post_by_guest=(not post_mode),
                        width=image_info.get("width") or image_info.get("image_width"),
                        height=image_info.get("height") or image_info.get("image_height"),
                        ai=artwork_result.is_AIGC,
                        full_info=json.dumps(image_info),
                    )
                    images.append(img)
                    r = requests.get(img.url_original_pic)
                    filename = f"{img.pid}_{img.page}.{extension}"
                    file_path = cls.download_path + filename
                    with open(file_path, "wb") as f:
                        f.write(r.content)
                    img.size = os.path.getsize(file_path)
                    img.filename = filename
                    session.add(img)
                    msg += f'第{i+1}张图片：{img.width}x{img.height}\n'
            session.commit()
            artwork_result.feedback = msg
            artwork_result.images = images
            artwork_result.success = True
            cls.get_caption(artwork_result, artwork_meta)

            return artwork_result
        except:
            pass

    @classmethod
    def get_caption(cls, artwork_result: ArtworkResult, artwork_meta: list[list]) -> ArtworkResult:
        caption = ''
        if artwork_meta.get("title"):
            caption += f"<blockquote>{html_esc(artwork_meta.get("title"))}</blockquote>\n"
        if artwork_result.tags:
            caption += f'Tags: {" ".join(artwork_result.tags)}\n'
        if artwork_result.raw_tags:
            caption += f'<blockquote expandable>Raw Tags: {" ".join(artwork_result.raw_tags)}</blockquote>\n'
        artwork_result.caption = caption
        

    @classmethod
    async def get_tags(cls, input_tags: list[str], artwork_info: list[list]) -> ArtworkResult:
        artwork_meta: dict = artwork_info[0][1]
        raw_tags: list[str] = artwork_meta.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split()
        artwork_result = ArtworkResult()
        
        input_set = set()
        for tag in input_tags:
            if len(tag) <= 4:
                tag = tag.upper()
            input_set.add("#" + html_esc(tag.lstrip("#")))
        
        raw_tags_set: set[str] = set()
        for tag in raw_tags:
            if len(tag) <= 3:
                tag = tag.upper()
            # 切分长词
            # if len(tag.split()) > 3:
            #     raw_tags.append(tag.split())
            tag = tag.replace(" ", "_")
            raw_tags_set.add("#" + html_esc(tag.lstrip("#")))
            
        all_tags = input_set & raw_tags_set
        artwork_result.is_AIGC = "#AI" in all_tags
        artwork_result.is_NSFW = ("#R18" in all_tags) or ("#R-18" in all_tags) or ("#NSFW" in all_tags)
        artwork_result.tags = sorted(input_set)
        artwork_result.raw_tags = sorted(raw_tags_set)
        return artwork_result
