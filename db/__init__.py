from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from config import config

# 创建数据库引擎
engine = create_engine(config.db_url, echo=True)


# 创建一个会话工厂
Session = sessionmaker(bind=engine)
session = Session()

# 创建基础模型类
Base = declarative_base()
