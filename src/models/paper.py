from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
from zoneinfo import ZoneInfo
from models.db import Base

def beijing_time():
    return datetime.now(ZoneInfo("Asia/Shanghai"))

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    upload_time = Column(DateTime(timezone=True), default=beijing_time)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # 分析结果
    title = Column(Text)     # 标题
    authors = Column(Text)    # 作者
    published_time = Column(Text)  # 发表时间
    arxiv_url = Column(Text)    # arxiv 网址
    abstract = Column(Text)    # 中文摘要
    summary = Column(Text)     # 一句话总结
    key_content = Column(Text)    # 核心内容概括（full_text精简版）
    terminology = Column(Text)    # 关键词列表
    research_context = Column(Text)   # 研究脉络
    related_papers_json = Column(Text, nullable=True) # 存储相关参考文献的JSON字符串
    full_text = Column(Text, nullable=True)   # 解析出的论文pdf全文
    s2_id = Column(String(100), nullable=True)  # Semantic Scholar Paper ID (弃用）

    processing_status = Column(String(50), default='uploaded')


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey('papers.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=beijing_time)
