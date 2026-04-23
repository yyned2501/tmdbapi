from typing import List, Optional
from modules.scrapers.base import BaseScraper, ScraperMediaResult
from core.tmdb_client import tmdb_client, logger


class TMDBScraper(BaseScraper):
    """TMDB 刮削器实现"""

    @property
    def name(self) -> str:
        return "tmdb"

    async def search(self, query: str, **kwargs) -> List[ScraperMediaResult]:
        """搜索电影"""
        # 默认搜索电影，可以扩展支持 TV
        media_type = kwargs.get("media_type", "movie")
        endpoint = f"search/{media_type}"

        data = await tmdb_client.get(endpoint, params={"query": query})
        results = []

        logger.info(f"TMDB 搜索返回结果数量: {len(data.get('results', []))}")

        for item in data.get("results", []):
            results.append(
                ScraperMediaResult(
                    title=item.get("title") or item.get("name"),
                    original_title=item.get("original_title")
                    or item.get("original_name"),
                    overview=item.get("overview"),
                    release_date=item.get("release_date") or item.get("first_air_date"),
                    poster_path=item.get("poster_path"),
                    backdrop_path=item.get("backdrop_path"),
                    adult=item.get("adult", False),
                    source=self.name,
                    source_id=str(item.get("id")),
                    raw_data=item,
                )
            )
        return results

    async def get_detail(
        self, source_id: str, **kwargs
    ) -> Optional[ScraperMediaResult]:
        """获取详情"""
        media_type = kwargs.get("media_type", "movie")
        endpoint = f"{media_type}/{source_id}"

        try:
            item = await tmdb_client.get(endpoint)
            return ScraperMediaResult(
                title=item.get("title") or item.get("name"),
                original_title=item.get("original_title") or item.get("original_name"),
                overview=item.get("overview"),
                release_date=item.get("release_date") or item.get("first_air_date"),
                poster_path=item.get("poster_path"),
                backdrop_path=item.get("backdrop_path"),
                adult=item.get("adult", False),
                source=self.name,
                source_id=str(item.get("id")),
                raw_data=item,
            )
        except Exception:
            return None


# 导出实例
tmdb_scraper = TMDBScraper()

__all__ = ["tmdb_scraper"]
