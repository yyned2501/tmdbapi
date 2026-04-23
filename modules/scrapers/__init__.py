from modules.scrapers.tmdb import tmdb_scraper
from modules.scrapers.mdc import mdc_scraper

# 刮削器注册表
SCRAPERS = {
    tmdb_scraper.name: tmdb_scraper,
    mdc_scraper.name: mdc_scraper,
}

__all__ = ["tmdb_scraper", "mdc_scraper", "SCRAPERS"]
