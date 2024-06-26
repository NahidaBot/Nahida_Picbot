import asyncio
import os
import re
import logging
import json
from datetime import datetime
from typing import Any, Optional, Union

from telegram import User
import httpx

from config import config
from entities import ArtworkParam, Image, ImageTag, ArtworkResult
from utils import check_duplication, get_source_str, html_esc
from db import session
from .default import DefaultPlatform

logger = logging.getLogger(__name__)


class Pixiv(DefaultPlatform):

    platform = "Pixiv"
    download_path = f"{DefaultPlatform.base_downlad_path}/{platform}/"
    if not os.path.exists(download_path):
        os.mkdir(download_path)

    cookies = {
        "PHPSESSID": config.pixiv_phpsessid,
        "device_token": config.pixiv_device_token,
    }

    @classmethod
    async def get_info_from_web_api(
        cls, pid: int | str, language: str = ""
    ) -> dict[str, Any]:
        """
        尝试使用 Pixiv Web API 获取作品信息
        :param language: zh / en
        示例: ./json_examples/pixiv_web.json
        """
        url = f"https://www.pixiv.net/ajax/illust/{pid}"
        headers = {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }
        if language == "en":
            headers["Accept-Language"] = "en"
        else:
            headers["Accept-Language"] = "zh-CN,zh;q=0.9"

        async with httpx.AsyncClient(http2=True) as client:
            response = await client.get(
                url, cookies=cls.cookies, headers=headers, timeout=30
            )
            response.raise_for_status()
            j: dict[str, Any] = response.json()
            logger.debug(j)
            return j["body"]

    @classmethod
    async def get_multi_page(cls, pid: str) -> list[dict[str, Any]]:
        """
        示例: ./json_examples/pixiv_web_pages.json
        """
        url = f"https://www.pixiv.net/ajax/illust/{pid}/pages"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "max-age=0",
            "dnt": "1",
            "priority": "u=0, i",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }
        async with httpx.AsyncClient(http2=True) as client:
            # await asyncio.sleep(0.5)
            response = await client.get(url, headers=headers, cookies=cls.cookies)
            response.raise_for_status()
            j: dict[str, Any] = response.json()
            return j["body"]

    @classmethod
    async def check_duplication(cls, pid: str, user: User, post_mode: bool) -> ArtworkResult:  # type: ignore
        if post_mode and config.bot_deduplication_mode:
            existing_image = check_duplication(pid)
            if existing_image:
                logger.warning(f"试图发送重复的图片: {cls.platform}" + existing_image)
                user = User(
                    existing_image.userid, existing_image.username, is_bot=False
                )
                return ArtworkResult(
                    False,
                    f"该图片已经由 {user.mention_html()} 于 {str(existing_image.create_time)[:-7]} 发过",
                )
        return ArtworkResult(True)

    @classmethod
    async def get_artworks(
        cls, url: str, artwork_param: ArtworkParam, user: User, post_mode: bool = True
    ) -> ArtworkResult:
        """
        :param url 匹配下列任意一种
        123456
        pixiv.net/i/123456
        http://pixiv.net/i/123456
        https://pixiv.net/i/123456
        https://pixiv.net/artworks/123456
        https://www.pixiv.net/en/artworks/123456
        https://www.pixiv.net/member_illust.php?mode=medium&illust_id=123456
        """
        reg = re.compile(
            r"^(?:https?:\/\/)?(?:www\.)?(?:pixiv\.net\/(?:en\/)?(?:(?:i|artworks)\/|member_illust\.php\?(?:mode=[a-z_]*&)?illust_id=))?(\d+)$"
        )
        try:
            pid: str = reg.split(url)[1]

            artwork_meta, artwork_meta_en = await asyncio.gather(
                cls.get_info_from_web_api(pid), cls.get_info_from_web_api(pid, "en")
            )

            artwork_result = await cls.check_duplication(pid, user, post_mode)
            if not artwork_result.success:
                return artwork_result
            artwork_result.artwork_param = artwork_param

            page_count: int = artwork_meta["pageCount"]
            artwork_result.feedback = f"""获取成功！\n共有{page_count}张图片\n"""

            artwork_info: list[dict[str, Any]] = [artwork_meta]
            if page_count > 1:
                artwork_info = await cls.get_multi_page(pid)

            artwork_result.images = await cls.get_images(
                user, post_mode, page_count, artwork_info, artwork_meta, artwork_result
            )
            artwork_result: ArtworkResult = await cls.get_tags(
                artwork_param.input_tags, artwork_meta, artwork_result
            )
            artwork_result = await cls.get_en_tags(
                artwork_param.input_tags, artwork_meta_en, artwork_result
            )

            if not artwork_result.cached:
                tasks = [
                    asyncio.create_task(
                        cls.download_image(image, refer="https://www.pixiv.net/")
                    )
                    for image in artwork_result.images
                ]
                await asyncio.wait(tasks)

            # session.commit() # 移至 command handler 发出 Image Group 之后
            artwork_result = cls.get_caption(artwork_result, artwork_meta)
            artwork_result.success = True
            return artwork_result

        except Exception as e:
            logger.error(e)
            return ArtworkResult(
                False, "出错了呜呜呜，对不起主人喵，没能成功获取到图片"
            )

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
        pages = list(range(1, page_count + 1))
        if artwork_result.artwork_param.pages is not None:
            pages = artwork_result.artwork_param.pages
        is_nsfw: bool = artwork_result.is_NSFW or artwork_meta["xRestrict"]==1
        if artwork_result.artwork_param.is_NSFW is not None:
            is_nsfw = artwork_result.artwork_param.is_NSFW
        for i in pages:
            image_info: dict[str, Union[dict[str, str], str]] = artwork_info[i - 1]
            assert isinstance(image_info["urls"], dict)
            urls: dict[str, str] = image_info["urls"]
            img = Image(
                userid=user.id,
                username=user.name,
                platform=cls.platform,
                title=artwork_meta["title"],
                page=i,
                size=None,
                filename=urls["original"].split("/")[-1],
                author=artwork_meta["userName"],
                authorid=artwork_meta["userId"],
                pid=pid,
                extension=urls["original"].split(".")[-1],
                url_original_pic=urls["original"],
                url_thumb_pic=urls["regular"],
                r18=is_nsfw,
                width=image_info["width"],
                height=image_info["height"],
                post_by_guest=(not post_mode),
                ai=artwork_result.is_AIGC or artwork_meta["aiType"] == 2,
                full_info=json.dumps(image_info if i!=1 else artwork_meta),
            )
            images.append(img)
            session.add(img)
            assert isinstance(artwork_result.feedback, str)
            artwork_result.feedback += f"第{i}张图片：{img.width}x{img.height}\n"
        logger.debug(images)
        return images

    @classmethod
    def get_caption(
        cls, artwork_result: ArtworkResult, artwork_meta: dict[str, Any]
    ) -> ArtworkResult:
        pid: int = artwork_meta["id"]
        title: str = artwork_meta["title"]
        description: str = html_esc(
            artwork_meta["extraData"]["meta"]["twitter"]["description"]
        )
        uploadDate: datetime = datetime.fromisoformat((artwork_meta["uploadDate"]))

        title_sharp = "#" + title
        is_title_included = (title_sharp in artwork_result.raw_tags) or (
            title_sharp in artwork_result.tags
        )
        title = f"<b>{html_esc((title))}</b>\n" if not is_title_included else ""
        tags = " ".join(artwork_result.tags)
        source_str = ''
        if s := get_source_str(artwork_result.artwork_param):
            source_str += s + '\n'
        artwork_result.caption = (
            f"{title}"
            f'<a href="https://pixiv.net/artworks/{pid}">Source</a>'
            f' by <a href="https://pixiv.net/users/{artwork_meta["userId"]}">Pixiv {artwork_meta["userName"]}</a>\n'
            f'{source_str}'
            f'{tags+'\n' if tags else ''}'
            f"<blockquote expandable>{description+'\n' if description else ''}"
            f"Raw Tags: {' '.join(artwork_result.raw_tags)}\n{uploadDate.strftime('%Y-%m-%d %H:%M:%S')}</blockquote>\n"
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
        # https://github.com/xuejianxianzun/PixivBatchDownloader/blob/master/src/ts/Tools.ts#L399-L403
        # 如果用户在 Pixiv 的页面语言是中文, 则应用优化策略
        # 如果翻译后的标签是纯英文, 则判断原标签是否含有至少一部分中文, 如果是则使用原标签
        # 这是为了解决一些中文标签被翻译成英文的问题, 如 原神 被翻译为 Genshin Impact
        # 能代(アズールレーン) Noshiro (Azur Lane) 也会使用原标签
        # 但是如果原标签里没有中文则依然会使用翻译后的标签, 如 フラミンゴ flamingo
        raw_tags: list[dict[str, Any]] = artwork_meta["tags"]["tags"]
        tags_translated: list[str] = []
        tags_all: list[str] = []
        CHINESE_REGEXP = "[一-龥]"
        PUNCTUATION_PATTERN = r"""[!"$%&'()*+,-./:;<=>?@[\]^`{|}~．！？｡。＂＃＄％＆＇（）＊＋, －／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､　、〃〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏﹑﹔·]"""
        for tag in raw_tags:
            tag_raw = tag["tag"]
            if "users入り" in tag_raw:
                continue
            tag_raw = re.sub(PUNCTUATION_PATTERN, "", tag_raw)
            tags_all.append("#" + html_esc((tag_raw)))
            use_origin_tag = True
            if tag.get("translation"):
                use_origin_tag = False
                if tag["translation"]["en"].isascii():
                    if re.match(CHINESE_REGEXP, tag_raw):
                        use_origin_tag = True
            tag_translated: str = (
                tag_raw if use_origin_tag else tag["translation"]["en"]
            )
            tag_translated = tag_translated.replace(" ", "_")
            tag_translated = re.sub(PUNCTUATION_PATTERN, "", tag_translated)
            tags_translated.append("#" + html_esc(tag_translated))

        artwork_result.raw_tags = list(set(tags_translated + tags_all))

        pid = artwork_result.images[0].pid

        input_set: set[str] = set()
        for tag in input_tags:
            tag = "#" + html_esc(tag.lstrip("#"))
            input_set.add(tag)
            if not artwork_result.cached:
                session.add(ImageTag(pid=pid, tag=tag))

        all_tags: set[str] = input_set & set(artwork_result.raw_tags)
        artwork_result.is_AIGC = "#AI" in all_tags
        artwork_result.is_NSFW = "NSFW" in all_tags
        artwork_result.tags = sorted(input_set)
        logger.debug(artwork_result)
        return artwork_result

    @classmethod
    async def get_en_tags(
        cls,
        _: list[str],
        artwork_meta: dict[str, Any],
        artwork_result: ArtworkResult,
    ) -> ArtworkResult:
        raw_tags: list[dict[str, Any]] = artwork_meta["tags"]["tags"]
        tags_en: list[str] = []
        PUNCTUATION_PATTERN = r"""[!"$%&'()*+,-./:;<=>?@[\]^`{|}~．！？｡。＂＃＄％＆＇（）＊＋, －／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､　、〃〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏﹑﹔·]"""
        for tag in raw_tags:
            tag_raw: str = tag["tag"]
            if "users入り" in tag_raw:
                continue
            use_origin_tag = True
            if tag.get("translation") and tag["translation"]["en"].isascii():
                use_origin_tag = False
            tag_en: str = tag_raw if use_origin_tag else tag["translation"]["en"]
            tag_en = tag_en.replace(" ", "_").replace("-", "_")
            tag_en = re.sub(PUNCTUATION_PATTERN, "", tag_en)
            tags_en.append("#" + html_esc(tag_en))

        artwork_result.raw_tags = list(set(tags_en + artwork_result.raw_tags))

        logger.debug(artwork_result)
        return artwork_result
