from datetime import datetime
from db import Base, engine
from telegram import Message
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
)
from datetime import datetime
from typing import Optional


class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)  # id 一般自增
    userid = Column(Integer)  # telegram user id
    username = Column(String)  # telegram username 对于没有用户名的用户 为全名
    create_time = Column(DateTime, default=datetime.now)  # 图片发送时间
    platform = Column(String)  # 图片所属平台，例如 Pixiv
    title = Column(
        String
    )  # 图片标题 对于没有标题的平台，例如 twitter，是 tweet 原文
    page = Column(Integer)  # 图片页数 大部分平台可以有多页，此为当前页。
    size = Column(Integer)  # 图片大小 操作系统读取出来的大小。
    filename = Column(String)  # 文件名 包含扩展名
    author = Column(String)  # 作者名 是 username 而不是显示名称
    authorid = Column(Integer)  # 作者id 一般为数字
    pid = Column(String)  # 对于 twitter, 是 tweet id, 其他平台类似
    extension = Column(String)  # 扩展名, 目前未使用
    url_original_pic = Column(String)  # 原图的 url
    url_thumb_pic = Column(String)  # 缩略图的 url 一般为 1000px 左右
    r18 = Column(
        Boolean
    )  # 是否为 r18 作品 依赖平台返回值 不同平台可能判断标准不一样
    width = Column(Integer)  # 图片宽度
    height = Column(Integer)  # 图片高度
    post_by_guest = Column(Boolean, default=False)  # 是否为临时查看
    ai = Column(
        Boolean, default=False
    )  # 是否为 AI 生成 依赖平台返回值 大部分平台未提供接口
    full_info = Column(String)  # 原始 json 数据
    sent_message_link = Column(String)  # telegram file_id 预览图
    file_id_thumb = Column(String)  # telegram file_id 预览图
    file_id_original = Column(String) # telegram file_id 原图


class ImageTag(Base):
    __tablename__ = "imagetags"
    id = Column(Integer, primary_key=True)  # 没什么用
    pid = Column(String)  # pid
    tag = Column(String)  # tag


Base.metadata.create_all(engine)


class ArtworkResult:
    def __init__(
        self,
        success: bool = False,
        feedback: Optional[str] = None,
        caption: Optional[str] = None,
        images: list[Image] = [],
        hint_msg: Optional[Message] = None,
        is_NSFW: bool = False,
        is_AIGC: bool = False,
        tags: list[str] = [],
        raw_tags: list[str] = [],
        sent_channel_msg: Optional[Message] = None,
        is_international: bool = False,
    ) -> None:
        """
        用于在调用中传递一些 ~~脏~~ 东西
        :param success: bool 获取图片是否成功
        :param feedback: str admin chat 中 bot 对命令的反馈
        :param caption str 图片的描述
        :param images: list[Image] 
        :param hint_msg: Message feedback 对应的消息，用作后续编辑
        :param is_NSFW: bool
        :param is_AIGC: bool
        :param tags: list[str]
        :param raw_tags: list[str]
        :param sent_channel_msg: 频道成功发出消息后, bot api 返回的引用
        """
        self.success = success
        self.feedback = feedback
        self.caption = caption
        self.images = images
        self.hint_msg = hint_msg
        self.is_NSFW = is_NSFW
        self.is_AIGC = is_AIGC
        self.tags = tags
        self.raw_tags = raw_tags
        self.sent_channel_msg = sent_channel_msg
        self.is_international = is_international
