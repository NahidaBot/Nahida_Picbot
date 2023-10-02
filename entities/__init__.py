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
    id = Column(Integer, primary_key=True)
    userid = Column(Integer)
    username = Column(String)
    create_time = Column(DateTime, default=datetime.now)
    platform = Column(String)
    title = Column(String)
    page = Column(Integer)
    author = Column(String)
    authorid = Column(Integer)
    pid = Column(String)  # 对于 twitter，是 tweet id
    rawurl = Column(String)
    thumburl = Column(String)
    r18 = Column(Boolean)
    width = Column(Integer)
    height = Column(Integer)


# TODO 想个办法自动化生成tag
# class ImageTag(Base):
#     __tablename__ = "imagetags"
#     id = Column(Integer, primary_key=True)
#     image_id = Column(Integer, ForeignKey("images.id"))
#     tag = Column(String)


Base.metadata.create_all(engine)
