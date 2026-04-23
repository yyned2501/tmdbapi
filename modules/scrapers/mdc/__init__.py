from typing import List, Optional
from modules.scrapers.base import BaseScraper, ScraperMediaResult

class MDCScraper(BaseScraper):
    """MDC 刮削器实现 (预留)"""

    @property
    def name(self) -> str:
        return "mdc"

    async def search(self, query: str, **kwargs) -> List[ScraperMediaResult]:
        """MDC 搜索逻辑 (待实现)"""
        return []

    async def get_detail(self, source_id: str, **kwargs) -> Optional[ScraperMediaResult]:
        """MDC 详情获取逻辑 (待实现)"""
        return None

# 导出实例
mdc_scraper = MDCScraper()

__all__ = ["mdc_scraper"]
