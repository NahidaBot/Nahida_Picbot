import re
import os
import json
import math
import asyncio
import logging
import datetime
import subprocess

from typing import Callable, Optional, Any

import telegram
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    BotCommand,
    Message,
    InputMediaDocument,
    InputMediaPhoto,
    User,
)
from telegram.ext import (
    ContextTypes,
)
from telegram.constants import ParseMode
from config import config
from db import session
from entities import *
from platforms import *
from utils import *

DOWNLOADS: str = DefaultPlatform.base_downlad_path
restart_data = os.path.join(os.getcwd(), "restart.json")

logger = logging.getLogger(__name__)
if config.debug:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )
    # set higher logging level for httpx to avoid all GET and POST requests being logged
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class admin:
    class PermissionError(Exception):
        pass

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    async def __call__(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> Any:
        logger.debug(args)
        logger.debug(kwargs)
        context: ContextTypes.DEFAULT_TYPE = args[1]
        if not context:
            raise KeyError("Need context!")
        message: Message = args[0].message
        assert isinstance(message.from_user, User)
        user: telegram.User = message.from_user
        if not is_admin(user, context):
            await message.reply_text("你不是管理！再这样我叫大风纪官了喵！")
            raise PermissionError
        result = await self.func(*args, **kwargs)
        return result


async def random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    image = get_random_image()
    await context.bot.send_photo(
        update.message.chat_id,
        image.file_id_thumb,
        caption=config.txt_msg_tail,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("more info", image.sent_message_link),
                    InlineKeyboardButton(
                        "original", image.sent_message_link + "?comment=1"
                    ),
                ]
            ]
        ),
    )


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    assert isinstance(user, User)
    assert isinstance(update.message, Message)
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        # reply_markup=ForceReply(selective=False),
    )


async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert isinstance(update.message, Message)
    await update.message.reply_text(config.txt_help, parse_mode=ParseMode.HTML)


@admin
async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理post命令, 直接将投稿发至频道
    """
    message = update.message
    assert isinstance(message, Message)
    logging.debug(message.text)

    artwork_result = await get_artworks(message)

    if artwork_result.success:
        await message.reply_chat_action("upload_photo")
        assert isinstance(artwork_result.caption, str)
        artwork_result.caption += config.txt_msg_tail
        artwork_result = await send_media_group(context, artwork_result)
        if artwork_result.hint_msg:
            sent_channel_msg = artwork_result.sent_channel_msg
            assert sent_channel_msg
            assert sent_channel_msg.link
            link = sent_channel_msg.link
            await artwork_result.hint_msg.edit_text(
                artwork_result.feedback,
                ParseMode.HTML,
                InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("跳转到频道➡️", link),
                            InlineKeyboardButton("转到评论区➡️", link + "?comment=1"),
                        ]
                    ]
                ),
            )
    else:
        await message.reply_text(artwork_result.feedback)


async def get_artworks(
    message: telegram.Message,
    post_mode: bool = True,
    instant_feedback: bool = True,
) -> ArtworkResult:
    """
    post_mode 为 True 时, 发送到频道, 否则, 直接将消息返回给用户。
    只有发送到频道时才会尝试去重。
    """
    artwork_result = ArtworkResult()
    try:
        assert isinstance(message.text, str)
        splited_msg = message.text.split()[1:]
        post_url = splited_msg[0]
        artwork_param = prase_params(splited_msg[1:])
        user = message.from_user
        assert isinstance(user, User)
    except:
        artwork_result.feedback = "笨喵，哪里写错了？再检查一下呢？"
    else:
        if ("pixiv" in post_url) or re.match(r"[1-9]\d*", post_url):
            if instant_feedback:
                hint_msg = await message.reply_text("正在获取 Pixiv 图片喵...")
            artwork_result = await Pixiv.get_artworks(
                post_url, artwork_param, user, post_mode
            )
        elif "twitter" in post_url or "x.com" in post_url:
            if instant_feedback:
                hint_msg = await message.reply_text("正在获取 twitter 图片喵...")
            post_url = post_url.replace("x.com", "twitter.com")
            artwork_result = await Twitter.get_artworks(
                post_url, artwork_param, user, post_mode
            )
        elif (
            "miyoushe.com" in post_url
            or "bbs.mihoyo" in post_url
            or "hoyolab" in post_url
        ):
            if instant_feedback:
                hint_msg = await message.reply_text("正在获取米游社图片喵...")
            artwork_result = await MiYouShe.get_artworks(
                post_url, artwork_param, user, post_mode
            )
        elif "bilibili.com" in post_url:
            if instant_feedback:
                hint_msg = await message.reply_text("正在获取 bilibili 图片喵...")
            artwork_result = await bilibili.get_artworks(
                post_url, artwork_param, user, post_mode
            )
        else:
            if instant_feedback:
                hint_msg = await message.reply_text(
                    "检测到神秘的平台喵……\n咱正在试试能不能帮主人获取到，主人不要抱太大期望哦…"
                )
            artwork_result = await DefaultPlatform.get_artworks(
                post_url, artwork_param, user, post_mode
            )
            # artwork_result.feedback = "没有检测到支持的 URL 喵！主人是不是打错了喵！"
        if hint_msg:
            artwork_result.hint_msg = hint_msg  # type: ignore

    return artwork_result


async def send_media_group(
    context: ContextTypes.DEFAULT_TYPE,
    artwork_result: ArtworkResult,
    chat_id: int | str = config.bot_channel,
) -> ArtworkResult:
    """
    发送图片(组)
    参数：
    artwork_result: 拿到的图片结果
    chat_id: 可能是用户 群聊, 如果是发图流程则是默认的发图频道
    context: bot 上下文
    """
    media_group: list[InputMediaPhoto] = []
    has_spoiler: Optional[bool] = artwork_result.artwork_param.spoiler
    for image in artwork_result.images:
        if image.file_id_thumb:
            media_group.append(InputMediaPhoto(image.file_id_thumb))
            continue
        file_path = f"{DOWNLOADS}/{image.platform}/{image.filename}"
        if not is_within_size_limit(file_path):
            img_compressed = f"{DOWNLOADS}/{image.platform}/compressed_{image.filename}"
            compress_image(file_path, img_compressed)
            file_path = img_compressed
        with open(file_path, "rb") as f:
            media_group.append(
                InputMediaPhoto(
                    f, has_spoiler=has_spoiler if has_spoiler is not None else image.r18
                )
            )
    logger.debug(media_group)

    # 防打扰, 若干秒内不开启通知音
    disable_notification = False
    if chat_id == config.bot_channel:
        now = datetime.now()
        context.bot_data["last_msg"] = now
        interval = now - context.bot_data["last_msg"]
        if interval.total_seconds() < config.bot_disable_notification_interval:
            disable_notification = True
        if artwork_result.artwork_param.silent is not None:
            disable_notification = artwork_result.artwork_param.silent

    # 发图流程 检测到AI图则分流
    if (
        config.bot_enable_ai_redirect
        and chat_id == config.bot_channel
        and artwork_result.images[0].ai
    ):
        chat_id = config.bot_enable_ai_redirect_channel

    MAX_NUM = 10
    total_page = math.ceil(len(media_group) / MAX_NUM)
    batch_size = math.ceil(len(media_group) / total_page)
    for i in range(total_page):
        page_count = ""
        if total_page > 1:
            page_count = f"({i+1}/{total_page})\n"
        reply_msgs = await context.bot.send_media_group(
            chat_id,
            media_group[i * batch_size : (i + 1) * batch_size],
            caption=page_count + artwork_result.caption,
            parse_mode=ParseMode.HTML,
            disable_notification=disable_notification,
        )
        for j in range(len(reply_msgs)):
            img: Image = artwork_result.images[i * batch_size + j]
            img.sent_message_link = reply_msgs[0].link
            img.file_id_thumb = reply_msgs[j].photo[3].file_id
        reply_msg = reply_msgs[0]
        artwork_result.sent_channel_msg = reply_msg

        media_group = media_group[batch_size:]
        # 防止 API 速率限制
        await asyncio.sleep(3 * batch_size)

    if (chat_id == config.bot_channel) or (
        chat_id == config.bot_enable_ai_redirect_channel
    ):
        # 发原图
        context.bot_data[artwork_result.sent_channel_msg.id] = artwork_result.images
        logger.info(context.bot_data)
    # session.commit()

    artwork_result.feedback += f"\n发送成功了喵！"
    return artwork_result


async def get_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 匹配 bot_data, 匹配到则发送原图, 否则忽略该消息
    logger.info(context.bot_data)
    if not update.message:
        return
    msg: Message = update.message
    if (
        msg.api_kwargs["forward_from_message_id"]
        and msg.api_kwargs["forward_from_message_id"] in context.bot_data
    ):
        await update.message.reply_chat_action("upload_document")
        await post_original_pic(context, msg)


async def post_original_pic(
    context: ContextTypes.DEFAULT_TYPE,
    message: Optional[telegram.Message] = None,
    chat_id: int | str = config.bot_channel,
    images: Optional[list[Image]] = None,  # type: ignore
) -> None:
    """
    message 与 chat_id, images 互斥, 前者用于捕获频道消息并回复原图, 后者直接发送到指定 chat_id, 目前用于获取图片信息
    """
    if not images:
        assert isinstance(message, Message)
        images: list[Image] = context.bot_data.pop(
            message.api_kwargs["forward_from_message_id"]
        )
    media_group: list[InputMediaDocument] = []
    for image in images:
        if image.file_id_original:
            media_group.append(InputMediaDocument(image.file_id_original))
            continue
        file_path = f"{DOWNLOADS}/{image.platform}/{image.filename}"
        with open(file_path, "rb") as f:
            media_group.append(telegram.InputMediaDocument(f))

    MAX_NUM = 10
    total_page = math.ceil(len(media_group) / MAX_NUM)
    batch_size = math.ceil(len(media_group) / total_page)
    for i in range(total_page):
        if message:
            reply_msgs = await message.reply_media_group(
                media=media_group[i * batch_size : (i + 1) * batch_size]
            )
        else:
            reply_msgs = await context.bot.send_media_group(
                chat_id,
                media_group[i * batch_size : (i + 1) * batch_size],
            )
        for j in range(len(reply_msgs)):
            img: Image = images[i * batch_size + j]
            img.file_id_original = reply_msgs[j].document.file_id
        images = images[batch_size:]
        # 防止 API 速率限制
        await asyncio.sleep(3 * batch_size)
    session.commit()


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert isinstance(update.message, Message)
    msg = update.message
    logging.info(msg.text)

    artwork_result: ArtworkResult = await get_artworks(update.message, post_mode=False)
    if artwork_result.success:
        await update.message.reply_chat_action("upload_photo")
        artwork_result.caption += config.txt_msg_tail
        await send_media_group(context, artwork_result, msg.chat_id)
    await update.message.reply_chat_action("upload_document")
    await post_original_pic(
        context=context, chat_id=msg.chat_id, images=artwork_result.images
    )


@admin
async def set_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert isinstance(update.message, Message)
    r = await context.bot.set_my_commands(
        [
            BotCommand("post", "(admin)  /post url #tag1 #tag2 发图到频道"),
            BotCommand("echo", "/echo url #tag1 #tag2 返回预览"),
            BotCommand("mark_dup", "(admin) /mark_dup url 标记图片已被发送过"),
            BotCommand("unmark_dup", "(admin) /unmark_dup url 反标记该图片信息"),
            BotCommand("repost_orig", "(admin) /repost_orig 在频道评论区回复"),
            BotCommand("ping", "hello"),
        ]
    )
    await update.message.reply_text(str(r))


# @admin
# async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     assert isinstance(update.message, Message)
#     artwork_result = await get_artworks(update.message, instant_feedback=False)
#     if artwork_result.success:
#         await update.message.reply_text("标记为已发送了喵！")
#     else:
#         await update.message.reply_text("呜呜，标记失败了喵, 主人快看看日志喵")
#         logger.error(artwork_result)


# @admin
# async def unmark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     assert isinstance(update.message, Message)
#     message = update.message
#     try:
#         assert isinstance(message.text, str)
#         pid = message.text.split()[-1].strip("/").split("/")[-1].split("?")[0]
#         if message.reply_to_message:
#             pid = find_url(update.message)[0].strip("/").split("/")[-1]
#         unmark_deduplication(pid)
#         await message.reply_text("成功从数据库里删掉了喵！")
#     except Exception as e:
#         logger.error(e)
#         await message.reply_text("呜呜，出错了喵！服务器熟了！")


@admin
async def repost_orig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    assert isinstance(msg, Message)
    try:
        urls = find_url(msg)
        if len(urls) == 0:
            await msg.reply_text("笨蛋喵！消息里没有 url 喵！")
            raise AttributeError

        pid = urls[0].strip("/").split("/")[-1]
        images = (
            session.query(Image)
            .filter_by(pid=pid, post_by_guest=False)
            .order_by(Image.page)
            .all()
        )

        await msg.reply_chat_action("upload_document")
        media_group: list[InputMediaDocument] = []
        for image in images:
            file_path = f"{DOWNLOADS}/{image.platform}/{image.filename}"
            with open(file_path, "rb") as f:
                media_group.append(InputMediaDocument(f))
        assert isinstance(msg.reply_to_message, Message)
        await msg.reply_to_message.reply_media_group(
            media_group, write_timeout=60, read_timeout=20
        )
        await msg.delete(read_timeout=20)

    except Exception:
        await msg.reply_text("呜呜，获取失败了喵，检查下是不是在原图评论区发的喵！")


@admin
async def get_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert isinstance(update.message, Message)
    chat_id = update.message.chat_id
    await _get_admins(chat_id, context)
    msg_posted = await update.message.reply_text("更新管理员列表成功喵！")
    await asyncio.sleep(3)
    await update.message.delete()
    await msg_posted.delete()


async def _get_admins(
    chat_id: int | str,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    application: Any = None,
) -> None:
    if context:
        # 命令调用
        admins = [
            admin.user.id
            for admin in await context.bot.get_chat_administrators(chat_id)
        ]
        context.bot_data["admins"] = admins
    else:
        # 初始化调用
        admins: list[int] = [
            admin.user.id
            for admin in await application.bot.get_chat_administrators(chat_id)
        ]
        application.bot_data["admins"] = admins
    logger.debug(application.bot_data)


def is_admin(user: telegram.User, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # from bot import application

    result = (
        user.id in context.bot_data.get("admins", [])
        or user.id in config.bot_admin_chats
        or user.id == config.bot_channel_comment_group
        or user.username == config.bot_channel
        or user.username == config.bot_enable_ai_redirect_channel
    )
    logger.debug(user)
    logger.debug(context.bot_data)
    logger.debug(result)
    return result


# 定义一个异步的初始化函数
async def on_start(application: Any):
    # 在这里调用 _get_admins 函数
    await _get_admins(config.bot_channel_comment_group, application=application)
    # 这里还可以添加其他在机器人启动前需要执行的代码
    await restore_from_restart(application)
    application.bot_data["me"] = await application.bot.get_me()


@admin
async def restart(
    update: Update, context: ContextTypes.DEFAULT_TYPE, update_msg: str = ""
) -> None:
    assert isinstance(update.message, Message)
    msg = await update.message.reply_text(
        update_msg + "正在重启喵，请主人等咱一会儿喵..."
    )
    with open(restart_data, "w", encoding="utf-8") as f:
        f.write(msg.to_json())
    context.application.stop_running()


async def restore_from_restart(application: Any) -> None:
    if os.path.exists(restart_data):
        with open(restart_data) as f:
            msg: Message = Message.de_json(json.load(f), application.bot)  # type: ignore
            await msg.edit_text("重启成功了喵！")
        os.remove(restart_data)


@admin
async def update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert isinstance(update.message, Message)
    try:
        command = ["git", "pull", "-f"]
        result: subprocess.CompletedProcess[str] = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug(result.stdout)
        logger.debug("更新成功了喵！")
    except subprocess.CalledProcessError as e:
        logger.error("呜呜，更新出错了喵:" + str(e))
        await update.message.reply_text("呜呜，更新失败了喵，请主人看下日志吧")
        return
    await restart(update, context, "更新成功了喵！")
