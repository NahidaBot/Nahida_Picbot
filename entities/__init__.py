from dataclasses import dataclass, field
import os
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

if not os.path.exists("./data"):
    os.makedirs("./data")

class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)  # id 一般自增
    userid = Column(Integer)  # telegram user id
    username = Column(String)  # telegram username 对于没有用户名的用户 为全名
    create_time = Column(DateTime, default=datetime.now())  # 图片发送时间
    platform = Column(String)  # 图片所属平台, 例如 Pixiv
    title = Column(
        String
    )  # 图片标题 对于没有标题的平台, 例如 twitter, 是 tweet 原文
    page = Column(Integer)  # 图片页数 大部分平台可以有多页, 此为当前页。
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
    update_time = Column(DateTime, default=datetime.now()) # 最后一次发送时间
    post_count = Column(Integer(), default=1) # 发送次数计数


class ImageTag(Base):
    __tablename__ = "imagetags"
    id = Column(Integer, primary_key=True)  # 没什么用
    pid = Column(String)  # pid
    tag = Column(String)  # tag


Base.metadata.create_all(engine)


@dataclass
class ArtworkParam:
    '''
    传递 /post 和 /echo 中的可选参数
    :param input_tags: 给出的作品 tag
    :param pages: 发图的页码范围。如果为空, 默认全部发送。
    :param source_from_channel: 来源的频道 (直接从别的频道薅.jpg) 
    :param source_from_username: 来源的用户 (常见于投稿, 或者看到人形bot发图) 
    :param source_from_userid: 来源的用户id
    :param upscale: 上采样倍数 (需要waifu2x) 
    :param silent: 是否静默发图 (覆盖默认行为) 
    :param spoiler: 是否打上spoiler, 覆盖默认的行为 (给NSFW图片自动加上) 
    '''
    input_tags: list[str] = field(default_factory=list)
    pages: Optional[list[int]] = None
    source_from_channel: Optional[str] = None
    source_from_username: Optional[str] = None
    # source_from_userid: Optional[int|str] = None
    upscale: Optional[int] = None
    silent: Optional[bool] = None
    spoiler: Optional[bool] = None
    is_NSFW: Optional[bool] = None


@dataclass
class ArtworkResult:
    '''
    用于在调用中传递一些 ~~脏~~ 东西
    :param success: bool 获取图片是否成功
    :param feedback: str admin chat 中 bot 对命令的反馈
    :param caption str 图片的描述
    :param images: list[Image] 
    :param hint_msg: Message feedback 对应的消息, 用作后续编辑
    :param is_NSFW: bool
    :param is_AIGC: bool
    :param tags: list[str]
    :param raw_tags: list[str]
    :param sent_channel_msg: 频道成功发出消息后, bot api 返回的引用
    :param is_international: 仅对米游社生效, 用于标记是否来源为 hoyolab
    :param cached: 数据库中是否找到了有效的缓存
    :param artwork_param: 传入的参数
    '''
    success: bool = False
    feedback: Optional[str] = None
    caption: Optional[str] = None
    images: list[Image] = field(default_factory=list)
    hint_msg: Optional[Message] = None
    is_NSFW: bool = False
    is_AIGC: bool = False
    tags: list[str] = field(default_factory=list)
    raw_tags: list[str] = field(default_factory=list)
    sent_channel_msg: Optional[Message] = None
    is_international: bool = False
    cached: bool = False
    artwork_param: ArtworkParam = field(default_factory=ArtworkParam)
