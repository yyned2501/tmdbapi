from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime, func
from core.database import Base

class Media(Base):
    """媒体元数据模型"""
    __tablename__ = "media"

    id = Column(Integer, primary_key=True, index=True)
    
    # 刮削器来源信息
    scraper_source = Column(String(50), nullable=False, index=True)  # 如 'tmdb', 'mdc'
    scraper_id = Column(String(100), nullable=False, index=True)    # 来源中的唯一 ID
    
    # 核心元数据
    title = Column(String(255), nullable=False, index=True)
    original_title = Column(String(255))
    overview = Column(Text)
    release_date = Column(String(50))
    
    # 图片路径
    poster_path = Column(String(255))
    backdrop_path = Column(String(255))
    
    # 成人内容标记
    adult = Column(Boolean, default=False, index=True)
    
    # 原始数据
    raw_data = Column(JSON)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Media(title='{self.title}', source='{self.scraper_source}')>"

class APICache(Base):
    """API 响应缓存模型"""
    __tablename__ = "api_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(512), unique=True, index=True, nullable=False)
    response_data = Column(JSON, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<APICache(key='{self.cache_key}', expires='{self.expires_at}')>"
