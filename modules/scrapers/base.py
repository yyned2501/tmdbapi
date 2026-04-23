from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class ScraperMediaResult(BaseModel):
    """刮削结果的统一数据结构"""
    title: str
    original_title: Optional[str] = None
    overview: Optional[str] = None
    release_date: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    adult: bool = False
    source: str  # 来源刮削器名称
    source_id: str  # 在该来源中的唯一 ID
    raw_data: Dict[str, Any] = {}  # 原始 JSON 数据

class BaseScraper(ABC):
    """刮削器基类接口"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """刮削器名称"""
        pass

    @abstractmethod
    async def search(self, query: str, **kwargs) -> List[ScraperMediaResult]:
        """搜索媒体"""
        pass

    @abstractmethod
    async def get_detail(self, source_id: str, **kwargs) -> Optional[ScraperMediaResult]:
        """获取媒体详情"""
        pass
