from datetime import datetime
from db import Base, engine, session
from telegram import Message
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from datetime import datetime


class Image(Base):
    __tablename__ = "images"
    id: int = Column(Integer, primary_key=True)  # id 一般自增
    userid: int = Column(Integer)  # telegram user id
    username: str = Column(String)  # telegram username 对于没有用户名的用户 为全名
    create_time: datetime = Column(DateTime, default=datetime.now)  # 图片发送时间
    platform: str = Column(String)  # 图片所属平台，例如 Pixiv
    title: str = Column(
        String
    )  # 图片标题 对于没有标题的平台，例如 twitter，是 tweet 原文
    page: int = Column(Integer)  # 图片页数 大部分平台可以有多页，此为当前页。
    size: int = Column(Integer)  # 图片大小 操作系统读取出来的大小。
    filename: str = Column(String)  # 文件名 包含扩展名
    author: str = Column(String)  # 作者名 是 username 而不是显示名称
    authorid: int = Column(Integer)  # 作者id 一般为数字
    pid: int = Column(String)  # 对于 twitter, 是 tweet id, 其他平台类似
    extension: str = Column(String)  # 扩展名, 目前未使用
    url_original_pic: str = Column(String)  # 原图的 url
    url_thumb_pic: str = Column(String)  # 缩略图的 url 一般为 1000px 左右
    r18: bool = Column(
        Boolean
    )  # 是否为 r18 作品 依赖平台返回值 不同平台可能判断标准不一样
    width: int = Column(Integer)  # 图片宽度
    height: int = Column(Integer)  # 图片高度
    post_by_guest: bool = Column(Boolean, default=False)  # 是否为临时查看
    ai: bool = Column(
        Boolean, default=False
    )  # 是否为 AI 生成 依赖平台返回值 大部分平台未提供接口
    full_info: str = Column(String)  # 原始 json 数据


class ImageTag(Base):
    __tablename__ = "imagetags"
    id: int = Column(Integer, primary_key=True)  # 没什么用
    pid: int = Column(String)  # pid
    tag = Column(String)  # tag


Base.metadata.create_all(engine)


class ArtworkResult:
    def __init__(
        self,
        success: bool = False,
        feedback: str = None,
        caption: str = None,
        images: list[Image] = [],
        hint_msg: Message = None,
        is_NSFW: bool = False,
        is_AIGC: bool = False,
        tags: list[str] = [],
        raw_tags: list[str] = [],
    ) -> None:
        """
        success: bool 获取图片是否成功
        feedback: str admin chat 中 bot 对命令的反馈
        caption: str 图片的描述
        images: list[Image]
        hint_msg: Message feedback 对应的消息，用作后续编辑
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
