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
    author: str = Column(String)
    authorid: int = Column(Integer)
    pid: int = Column(String)  # 对于 twitter，是 tweet id
    rawurl: str = Column(String)
    thumburl: str = Column(String)
    r18: bool = Column(Boolean)
    width: int = Column(Integer)
    height: int = Column(Integer)


class ImageTag(Base):
    __tablename__ = "imagetags"
    id: int = Column(Integer, primary_key=True)
    pid: int = Column(String)
    tag = Column(String)


Base.metadata.create_all(engine)
