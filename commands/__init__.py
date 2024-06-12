import re
import os
import json
import math
import time
import logging
import datetime
import subprocess

from typing import Callable

from db import session

import telegram
from telegram import Update, BotCommand, Message
from telegram.ext import (
    Application,
    ContextTypes,
)
from telegram.constants import ParseMode
from config import config
from platforms import pixiv, twitter, miyoushe, bilibili
from entities import *
from utils import *

MAX_FILE_SIZE = 10 * 1024 * 1024
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

    def __init__(self, func):
        self.func = func

    async def __call__(self, *args, **kwargs) -> Callable:
        logger.debug(args)
        logger.debug(kwargs)
        context: ContextTypes.DEFAULT_TYPE = args[1]
        if not context:
            raise KeyError("Need context!")
        message: Message = args[0].message
        user = message.from_user
        if not is_admin(user, context):
            await message.reply_text("你不是管理！再这样我叫大风纪官了喵！")
            raise PermissionError
        result = await self.func(*args, **kwargs)
        return result


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        # reply_markup=ForceReply(selective=False),
    )


async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(config.txt_help, parse_mode=ParseMode.HTML)


@admin
async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理post命令, 直接将投稿发至频道
    """
    msg = update.message
    logging.info(msg.text)

    artwork_result = await get_artworks(update.message)

    if artwork_result.success:
        await update.message.reply_chat_action("upload_photo")
        artwork_result.caption += config.txt_msg_tail
        artwork_result = await send_media_group(artwork_result, context=context)
        await artwork_result.hint_msg.edit_text(artwork_result.feedback, ParseMode.HTML)
    else:
        await update.message.reply_text(artwork_result.feedback)


async def get_artworks(
    msg: telegram.Message,
    post_mode: bool = True,
    instant_feedback: bool = True,
) -> ArtworkResult:
    """
    post_mode 为 True 时, 发送到频道, 否则, 直接将消息返回给用户。
    只有发送到频道时才会尝试去重。
    """
    artwork_result = ArtworkResult()
    try:
        splited_msg = msg.text.split()[1:]
        post_url = splited_msg[0]
        tags = splited_msg[1:]
        user = msg.from_user
    except:
        artwork_result.feedback = "笨喵，哪里写错了？再检查一下呢？"
    else:
        if ("pixiv.net/artworks/" in post_url) or re.match(r"[1-9]\d*", post_url):
            if instant_feedback:
                hint_msg = await msg.reply_text("正在获取 Pixiv 图片喵...")
            artwork_result = await pixiv.get_artworks(post_url, tags, user, post_mode)
        elif "twitter" in post_url or "x.com" in post_url:
            if instant_feedback:
                hint_msg = await msg.reply_text("正在获取 twitter 图片喵...")
            post_url = post_url.replace("x.com", "twitter.com")
            artwork_result = await twitter.get_artworks(post_url, tags, user, post_mode)
        elif (
            "miyoushe.com" in post_url
            or "bbs.mihoyo" in post_url
            or "hoyolab" in post_url
        ):
            if instant_feedback:
                hint_msg = await msg.reply_text("正在获取米游社图片喵...")
            artwork_result = await miyoushe.get_artworks(
                post_url, tags, user, post_mode
            )
        elif "bilibili.com" in post_url:
            if instant_feedback:
                hint_msg = await msg.reply_text("正在获取 bilibili 图片喵...")
            artwork_result = await bilibili.get_artworks(
                post_url, tags, user, post_mode
            )
        else:
            if instant_feedback:
                hint_msg = await msg.reply_text("检测到神秘的平台喵……\n咱正在试试能不能帮主人获取到，主人不要抱太大期望哦…")
            from platforms.default import DefaultPlatform
            artwork_result = await DefaultPlatform.get_artworks(
                post_url, tags, user, post_mode
            ) 
            # artwork_result.feedback = "没有检测到支持的 URL 喵！主人是不是打错了喵！"
        artwork_result.hint_msg = hint_msg

    return artwork_result


async def send_media_group(
    artwork_result: ArtworkResult,
    chat_id: int | str = config.bot_channel,
    context: ContextTypes.DEFAULT_TYPE = None,
) -> ArtworkResult:
    """
    发送图片(组)
    参数：
    artwork_result: 拿到的图片结果
    chat_id: 可能是用户 群聊, 如果是发图流程则是默认的发图频道
    context: bot 上下文
    """
    media_group = []
    for image in artwork_result.images:
        file_path = f"./downloads/{image.platform}/{image.filename}"
        if not is_within_size_limit(file_path):
            # TODO 可能有潜在的bug，在多图达到压缩阈值时，将压缩后的图片写入了同一路径
            IMG_COMPRESSED = "./downloads/IMG_COMPRESSED.jpg"
            compress_image(file_path, IMG_COMPRESSED)
            file_path = IMG_COMPRESSED
        with open(file_path, "rb") as f:
            media_group.append(telegram.InputMediaPhoto(f, has_spoiler=image.r18))
    logger.debug(media_group)

    # 防打扰, 若干秒内不开启通知音
    disable_notification = False
    now = datetime.now()
    context.bot_data["last_msg"] = now
    interval: datetime.timedelta = now - context.bot_data["last_msg"]
    if interval.total_seconds() < config.bot_disable_notification_interval:
        disable_notification = True

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
        logger.debug(page_count)
        reply_msg = await context.bot.send_media_group(
            chat_id,
            media_group[i * batch_size : (i + 1) * batch_size],
            caption=page_count + artwork_result.caption,
            parse_mode=ParseMode.HTML,
            disable_notification=disable_notification,
        )
        reply_msg = reply_msg[0]

        if (
            reply_msg
            and (chat_id == config.bot_channel)
            or (chat_id == config.bot_enable_ai_redirect_channel)
        ):
            # 发原图
            context.bot_data[reply_msg.id] = artwork_result.images[:batch_size]
            logger.info(context.bot_data[reply_msg.id])
        artwork_result.images = artwork_result.images[batch_size:]

    artwork_result.feedback += f"\n发送成功了喵！"
    return artwork_result


async def get_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 匹配 bot_data, 匹配到则发送原图, 否则忽略该消息
    logger.info(context.bot_data)
    msg: Message = update.message
    # TODO forward_from_message_id 已废弃
    if (
        msg.api_kwargs["forward_from_message_id"]
        and msg.api_kwargs["forward_from_message_id"] in context.bot_data
    ):
        await update.message.reply_chat_action("upload_document")
        await post_original_pic(msg, context)


async def post_original_pic(
    msg: telegram.Message = None,
    context: ContextTypes.DEFAULT_TYPE = None,
    chat_id: int | str = config.bot_channel,
    images: list[Image] = None,
) -> None:
    """
    msg 与 chat_id, images 互斥, 前者用于捕获频道消息并回复原图, 后者直接发送到指定 chat_id, 目前用于获取图片信息
    """
    if not images:
        images: list[Image] = context.bot_data.pop(
            msg.api_kwargs["forward_from_message_id"]
        )
    media_group = []
    for image in images:
        file_path = f"./downloads/{image.platform}/{image.filename}"
        with open(file_path, "rb") as f:
            media_group.append(telegram.InputMediaDocument(f))
    if msg:
        await msg.reply_media_group(
            media=media_group, write_timeout=60, read_timeout=60
        )
    else:
        await context.bot.send_media_group(
            chat_id, media_group, write_timeout=60, read_timeout=60
        )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    logging.info(msg.text)

    artwork_result: ArtworkResult = await get_artworks(update.message, post_mode=False)
    if artwork_result.success:
        await update.message.reply_chat_action("upload_photo")
        artwork_result.caption += config.txt_msg_tail
        await send_media_group(artwork_result, msg.chat_id)
    await update.message.reply_chat_action("upload_document")
    await post_original_pic(
        context=context, chat_id=msg.chat_id, images=artwork_result.images
    )


@admin
async def set_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


@admin
async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    artwork_result = await get_artworks(update.message, instant_feedback=False)
    if artwork_result.success:
        await update.message.reply_text("标记为已发送了喵！")
    else:
        await update.message.reply_text("呜呜，标记失败了喵, 主人快看看日志喵")
        logger.error(artwork_result)


@admin
async def unmark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = update.message
        pid = message.text.split()[-1].strip("/").split("/")[-1].split("?")[0]
        if update.message.reply_to_message:
            pid = find_url(update.message)[0].strip("/").split("/")[-1]
        unmark_deduplication(pid)
        await update.message.reply_text("成功从数据库里删掉了喵！")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("呜呜，出错了喵！服务器熟了！")


@admin
async def repost_orig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        urls = find_url(update.message)
        if len(urls) == 0:
            await update.message.reply_text("笨蛋喵！消息里没有 url 喵！")
            raise AttributeError

        pid = urls[0].strip("/").split("/")[-1]
        images = (
            session.query(Image)
            .filter_by(pid=pid, post_by_guest=False)
            .order_by(Image.page)
            .all()
        )

        await update.message.reply_chat_action("upload_document")
        media_group = []
        for image in images:
            file_path = f"./downloads/{image.platform}/{image.filename}"
            with open(file_path, "rb") as f:
                media_group.append(telegram.InputMediaDocument(f))
        await update.message.reply_to_message.reply_media_group(
            media_group, write_timeout=60, read_timeout=20
        )
        await update.message.delete(read_timeout=20)

    except Exception as e:
        return await update.message.reply_text(
            "呜呜，获取失败了喵，检查下是不是在原图评论区发的喵！"
        )

@admin
async def get_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await _get_admins(chat_id, context)
    msg_posted = await update.message.reply_text("更新管理员列表成功喵！")
    time.sleep(3)
    await update.message.delete()
    await msg_posted.delete()


async def _get_admins(
    chat_id: int | str,
    context: ContextTypes.DEFAULT_TYPE = None,
    application: Application = None,
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
        admins = [
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
async def on_start(application: Application):
    # 在这里调用 _get_admins 函数
    await _get_admins(config.bot_channel_comment_group, application=application)
    # 这里还可以添加其他在机器人启动前需要执行的代码
    await restore_from_restart(application)
    application.bot_data["me"] = await application.bot.get_me()


@admin
async def restart(
    update: Update, context: ContextTypes.DEFAULT_TYPE, update_msg: str = ""
) -> None:
    msg = await update.message.reply_text(update_msg + "正在重启喵，请主人等咱一会儿喵...")
    with open(restart_data, "w", encoding="utf-8") as f:
        f.write(msg.to_json())
    context.application.stop_running()


async def restore_from_restart(application: Application) -> None:
    if os.path.exists(restart_data):
        with open(restart_data) as f:
            msg: Message = Message.de_json(json.load(f), application.bot)
            await msg.edit_text("重启成功了喵！")
        os.remove(restart_data)


@admin
async def update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        command = ["git", "pull"]

        # 使用subprocess执行命令
        result: subprocess.CompletedProcess = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug(result.stdout)
        logger.debug("更新成功啦喵！")
    except subprocess.CalledProcessError as e:
        logger.error("呜呜，更新出错了喵:" + e)
        return await update.message.reply_text("Update failed! Please check logs.")
    await restart(update, context, "Update success! ")
