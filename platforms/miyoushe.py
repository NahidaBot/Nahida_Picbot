import asyncio
from datetime import datetime
import json
import os
import logging
import re
from typing import Any, Optional

from telegram import User
import requests

from entities import Image, ImageTag, ArtworkResult
from platforms.default import DefaultPlatform
from platforms.pixiv import Pixiv
from utils.escaper import html_esc
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
        images: list[Image] = []
        assert isinstance(artwork_info, list)
        x_oss_process = "?x-oss-process=image//resize,l_2560/quality,q_100/auto-orient,0/interlace,1/format,jpg"
        for i in range(page_count):
            image_info: dict[str, Any] = artwork_info[i]
            img = Image(
                userid=user.id,
                username=user.name,
                platform=cls.platform,
                title=artwork_meta["post"]["subject"],
                page=(i + 1),
                size=int(image_info["size"]),
                filename=f'{artwork_meta["post"]["post_id"]}_{i+1}.{image_info["format"]}',
                author=artwork_meta["user"]["nickname"],
                authorid=artwork_meta["user"]["uid"],
                pid=artwork_meta["post"]["post_id"],
                extension=image_info["format"],
                url_original_pic=image_info["url"],
                url_thumb_pic=(image_info["url"]+x_oss_process),
                r18=False,
                width=image_info["width"],
                height=image_info["height"],
                post_by_guest=(not post_mode),
                ai=artwork_result.is_AIGC,
                full_info=json.dumps(image_info if i else artwork_meta),
            )
            images.append(img)
            session.add(img)
            assert isinstance(artwork_result.feedback, str)
            artwork_result.feedback += f"第{i+1}张图片：{img.width}x{img.height}\n"
        logger.debug(images)
        return images

    @classmethod
    async def check_duplication(cls, post_id: str, user: User, post_mode: bool) -> ArtworkResult:  # type: ignore
        return await Pixiv.check_duplication(post_id, user, post_mode)

    @classmethod
    async def get_artworks(
        cls, url: str, input_tags: list[str], user: User, post_mode: bool = True
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
            post_id = reg.split(url)[1]
            artwork_meta = await cls.get_post(post_id, False)
            assert artwork_meta
            image_list: list[dict[str, Any]] = artwork_meta["image_list"]

            artwork_result = await cls.check_duplication(post_id, user, post_mode)
            if not artwork_result.success:
                return artwork_result

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
                input_tags, artwork_meta, artwork_result
            )

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
        post_id = artwork_result.images[0].id
        author = artwork_result.images[0].author
        _, url_path = cls.get_game(artwork_meta)
        article_url = f"https://www.miyoushe.com/{url_path}/article/{post_id}"
        author_url = f"https://www.miyoushe.com/{url_path}/accountCenter/postList?id={artwork_result.images[0].authorid}"
        article_context: str = artwork_meta["post"]["content"]
        created_at = datetime.fromtimestamp(artwork_meta["post"]["created_at"])
        artwork_result.caption = (
            f"<b>{html_esc(artwork_meta["post"]["subject"])}</b>\n"
            f'<a href="{article_url}">Source</a>'
            f' by <a href="{author_url}">米游社 @{author}</a>\n'
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

        post_id: int = artwork_result.images[0].id
        artwork_result.raw_tags = [ ('#'+topic["name"]) for topic in artwork_meta["topics"] ]
        artwork_result.raw_tags.append(game)

        input_set: set[str] = set()
        input_set.add(game)
        for tag in input_tags:
            if len(tag) <= 5:
                tag = tag.upper()
            tag = "#" + html_esc(tag.lstrip("#"))
            input_set.add(tag)
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


# async def get_artworks(
#     url: str, input_tags: list, user: User, post_mode: bool = True
# ) -> ArtworkResult:
#     """
#     只有 post_mode 和 config.bot_deduplication_mode 都为 True, 才检测重复
#     """
#     id = url.strip("/").split("/")[-1]
#     is_global = "hoyolab" in url

#     post_json = await get_post(id, is_global)
#     image_list: list = post_json["image_list"]
#     post_info = post_json["post"]
#     page_count = len(image_list)
#     title = post_info["subject"]
#     r18 = False
#     ai: bool = False
#     x_oss_process = "?x-oss-process=image//resize,l_2560/quality,q_100/auto-orient,0/interlace,1/format,jpg"
#     msg = f"获取成功！\n" f"<b>{title}</b>\n" f"共有{page_count}张图片\n"

#     if post_mode and config.bot_deduplication_mode:
#         existing_image = check_duplication(id)
#         if existing_image:
#             logger.warning(f"试图发送重复的图片: {platform}" + str(id))
#             user = User(existing_image.userid, existing_image.username, is_bot=False)
#             return (
#                 False,
#                 f"该图片已经由 {user.mention_html()} 于 {str(existing_image.create_time)[:-7]} 发过",
#                 None,
#                 None,
#             )

#     tag_game, url_path = get_game(post_info)
#     tags: set[str] = set()
#     for tag in input_tags:
#         tag = "#" + tag.strip("#")
#         if len(tag) <= 3:
#             tag = tag.upper()
#         image_tag = ImageTag(pid=id, tag=tag)
#         session.add(image_tag)
#         tags.add(tag)
#     tags.add("#" + tag_game)
#     if "#AI" in tags:
#         tags.add("#AI")
#         ai = True

#     images: list[Image] = []
#     for i in range(page_count):
#         if is_global:
#             extension: str = image_list[i]["url"].split("/")[-1].split(".")[-1]
#         else:
#             extension = image_list[i]["format"]
#         filename: str = f"{id}_{i+1}.{extension}"
#         await download(image_list[i]["url"], download_path, filename)
#         image = Image(
#             userid=user.id,
#             username=user.name,
#             platform=platform,
#             pid=id,
#             title=title,
#             page=i,
#             size=image_list[i]["size"],
#             filename=filename,
#             author=post_json["user"]["nickname"],
#             authorid=post_json["user"]["uid"],
#             r18=r18,
#             extension=extension,
#             url_original_pic=image_list[i]["url"],
#             url_thumb_pic=image_list[i]["url"] + x_oss_process,
#             post_by_guest=(not post_mode),
#             width=image_list[i]["width"],
#             height=image_list[i]["height"],
#             ai=ai,
#         )
#         images.append(image)
#         session.add(image)
#         msg += f"第{i+1}张图片：{image.width}x{image.height}\n"
#     session.commit()

#     if is_global:
#         article_url = f"https://www.hoyolab.com/article/{id}"
#         author_url = (
#             f"https://www.hoyolab.com/accountCenter?id={post_json['user']['uid']}"
#         )
#     else:
#         article_url = f"https://www.miyoushe.com/{url_path}/article/{id}"
#         author_url = f"https://www.miyoushe.com/{url_path}/accountCenter/postList?id={images[0].authorid}"

#     caption = (
#         f"<b>{html_esc(images[0].title)}</b>\n"
#         f'<a href="{article_url}">Source</a> by <a href="{author_url}">{"HoYoLab" if is_global else "米游社"} @{html_esc(images[0].author)}</a>\n'
#         f'{" ".join(tags)}\n'
#     )

#     return ArtworkResult(True, msg, caption, images)
