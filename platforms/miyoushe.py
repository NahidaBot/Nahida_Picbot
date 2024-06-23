import asyncio
from datetime import datetime
import json
import os
import logging
import re
from typing import Any, Optional

from telegram import User
import requests

from entities import ArtworkParam, Image, ImageTag, ArtworkResult
from platforms.default import DefaultPlatform
from platforms.pixiv import Pixiv
from utils import html_esc
from db import session

logger = logging.getLogger(__name__)


class MiYouShe(DefaultPlatform):

    platform = "miyoushe"
    download_path = f"{DefaultPlatform.base_downlad_path}/{platform}/"
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    @classmethod
    async def get_post(
        cls, post_id: str, is_global: bool = False
    ) -> Optional[dict[str, Any]]:
        headers = {
            "referer": "https://www.miyoushe.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            "X-Rpc-Language": "zh-cn",
        }
        url = f"https://bbs-api.miyoushe.com/post/wapi/getPostFull?post_id={post_id}"
        if is_global:
            headers["referer"] = "https://www.hoyolab.com/"
            url = f"https://bbs-api-os.hoyolab.com/community/post/wapi/getPostFull?post_id={post_id}"
        try:
            response = requests.get(
                url,
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

    @classmethod
    async def get_images(  # type: ignore
        cls,
        user: User,
        post_mode: bool,
        page_count: int,
        artwork_info: Optional[list[dict[str, Any]]],
        artwork_meta: dict[str, Any],
        artwork_result: ArtworkResult,
    ) -> list[Image]:
        pid: str = artwork_meta["id"]
        if existing_images := cls.check_cache(pid, post_mode, user):
            artwork_result.cached = True
            return existing_images
        images: list[Image] = []
        assert isinstance(artwork_info, list)
        x_oss_process = "?x-oss-process=image//resize,l_2560/quality,q_100/auto-orient,0/interlace,1/format,jpg"
        pages = list(range(1, page_count + 1))
        if artwork_result.artwork_param.pages is not None:
            pages = artwork_result.artwork_param.pages
        for i in pages:
            image_info: dict[str, Any] = artwork_info[i-1]
            extension = image_info["format"]
            if artwork_result.is_international:
                if extension == "JPEG":
                    extension = 'jpg'
                elif extension == 'PNG':
                    extension = 'png'
            img = Image(
                userid=user.id,
                username=user.name,
                platform=cls.platform,
                title=artwork_meta["post"]["subject"],
                page=i,
                size=int(image_info["size"]),
                filename=f'{artwork_meta["post"]["post_id"]}_{i}.{extension}',
                author=artwork_meta["user"]["nickname"],
                authorid=artwork_meta["user"]["uid"],
                pid=pid,
                extension=extension,
                url_original_pic=image_info["url"],
                url_thumb_pic=(image_info["url"]+x_oss_process),
                r18=False,
                width=image_info["width"],
                height=image_info["height"],
                post_by_guest=(not post_mode),
                ai=artwork_result.is_AIGC,
                full_info=json.dumps(image_info if i!=1 else artwork_meta),
            )
            images.append(img)
            session.add(img)
            assert isinstance(artwork_result.feedback, str)
            artwork_result.feedback += f"第{i}张图片：{img.width}x{img.height}\n"
        logger.debug(images)
        return images

    @classmethod
    async def check_duplication(cls, post_id: str, user: User, post_mode: bool) -> ArtworkResult:  # type: ignore
        return await Pixiv.check_duplication(post_id, user, post_mode)

    @classmethod
    async def get_artworks(
        cls, url: str, artwork_param: ArtworkParam, user: User, post_mode: bool = True
    ) -> ArtworkResult:
        '''
        :param url 支持如下形式的：
            https://miyoushe.com/ys/article/54064752
            https://www.miyoushe.com/sr/article/54064752
            https://bbs.mihoyo.com/ys/article/54064752
            https://hoyolab.com/article/30083385
            https://www.hoyolab.com/article/30083385
        '''
        try:
            # url 识别
            reg = re.compile(
                r"^(?:https?:\/\/)?(?:www\.)?(?:(?:miyoushe|hoyolab|bbs.mihoyo)\.com\/(?:[a-z]+\/)?)article\/(\d+)"
            )
            is_global = False
            post_id = reg.split(url)[1]
            if 'hoyolab' in url:
                is_global = True
            artwork_meta = await cls.get_post(post_id, is_global)
            assert artwork_meta
            image_list: list[dict[str, Any]] = artwork_meta["image_list"]

            artwork_result = await cls.check_duplication(post_id, user, post_mode)
            if not artwork_result.success:
                return artwork_result
            artwork_result.artwork_param = artwork_param
            if is_global:
                artwork_result.is_international = True

            page_count = len(image_list)
            if not page_count:
                artwork_result.success = False
                artwork_result.feedback = '没有获取到图片，主人再检查一下吧'
                return artwork_result

            artwork_result.feedback = f"""获取成功！\n共有{page_count}张图片\n"""

            artwork_result.images = await cls.get_images(
                user, post_mode, page_count, image_list, artwork_meta, artwork_result
            )
            artwork_result = await cls.get_tags(
                artwork_param.input_tags, artwork_meta, artwork_result
            )

            if not artwork_result.cached:
                tasks = [
                    asyncio.create_task(cls.download_image(image))
                    for image in artwork_result.images
                ]
                await asyncio.wait(tasks)

            # session.commit() # 移至 command handler 发出 Image Group 之后
            artwork_result = cls.get_caption(artwork_result, artwork_meta)
            artwork_result.success = True
            return artwork_result
        except:
            return ArtworkResult(
                False, "出错了呜呜呜，对不起主人喵，没能成功获取到图片"
            )

    @classmethod
    def get_caption(
        cls, artwork_result: ArtworkResult, artwork_meta: dict[str, Any]
    ) -> ArtworkResult:
        post_id = artwork_result.images[0].pid
        author = artwork_result.images[0].author
        if artwork_result.is_international:
            article_url = f"https://www.hoyolab.com/article/{post_id}"
            author_url = f"https://www.hoyolab.com/accountCenter?id={artwork_result.images[0].authorid}"
            article_context: str = artwork_meta["post"]["desc"]
        else:
            _, url_path = cls.get_game(artwork_meta)
            article_url = f"https://www.miyoushe.com/{url_path}/article/{post_id}"
            author_url = f"https://www.miyoushe.com/{url_path}/accountCenter/postList?id={artwork_result.images[0].authorid}"
            article_context: str = artwork_meta["post"]["content"]
        created_at = datetime.fromtimestamp(artwork_meta["post"]["created_at"])
        artwork_result.caption = (
            f"<b>{html_esc(artwork_meta["post"]["subject"])}</b>\n"
            f'<a href="{article_url}">Source</a>'
            f' by <a href="{author_url}">{"HoYoLab" if artwork_result.is_international else "米游社"} @{author}</a>\n'
            f"<blockquote expandable>{article_context+'\n' if article_context else ''}"
            f"Topics: {' '.join(artwork_result.raw_tags)}\n{created_at.strftime('%Y-%m-%d %H:%M:%S')}</blockquote>\n"
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
        game, _ = cls.get_game(artwork_meta)
        game = '#' + game

        post_id: str = artwork_result.images[0].pid
        artwork_result.raw_tags = [ ('#'+topic["name"]) for topic in artwork_meta["topics"] ]
        artwork_result.raw_tags.append(game)

        input_set: set[str] = set()
        input_set.add(game)
        for tag in input_tags:
            if len(tag) <= 5:
                tag = tag.upper()
            tag = "#" + html_esc(tag.lstrip("#"))
            input_set.add(tag)
            if not artwork_result.cached:
                session.add(ImageTag(pid=post_id, tag=tag))

        all_tags = input_set & set(artwork_result.raw_tags)
        artwork_result.is_AIGC = "#AI" in all_tags
        artwork_result.is_NSFW = False
        artwork_result.tags = sorted(input_set)
        logger.debug(artwork_result)
        return artwork_result

    @classmethod
    def get_game(cls, post_info: dict[str, Any]) -> tuple[str, str]:
        game_id: int = post_info["post"]["game_id"]
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
            case 5:
                name = "大别野"
                url_path = "dby"
            case 6:
                name = "星铁"
                url_path = "sr"
            case 7:
                name = "大别野"
                url_path = "dby"
            case 8:
                name = "绝区零"
                url_path = "zzz"
            case _:
                raise Exception("未知分区")
        return name, url_path
