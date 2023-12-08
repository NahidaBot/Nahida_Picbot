from datetime import datetime
from db import Base, engine, session
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
    id: int = Column(Integer, primary_key=True)
    userid: int = Column(Integer)
    username: str = Column(String)
    create_time: datetime = Column(DateTime, default=datetime.now)
    platform: str = Column(String)
    title: str = Column(String)
    page: int = Column(Integer)
    size: int = Column(Integer)
    filename: str = Column(String)
    author: str = Column(String)
    authorid: int = Column(Integer)
    pid: int = Column(String)  # 对于 twitter, 是 tweet id, 其他平台类似
    extension: str = Column(String)  # 扩展名, 目前未使用
    rawurl: str = Column(String)
    thumburl: str = Column(String)
    r18: bool = Column(Boolean)
    width: int = Column(Integer)
    height: int = Column(Integer)
    guest: bool = Column(Boolean, default=False)
    ai: bool = Column(Boolean, default=False)


class ImageTag(Base):
    __tablename__ = "imagetags"
    id: int = Column(Integer, primary_key=True)
    pid: int = Column(String)
    tag = Column(String)


Base.metadata.create_all(engine)
