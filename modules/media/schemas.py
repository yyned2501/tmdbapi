from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any

# --- TMDB 兼容 Schema ---

class TMDBMovieResult(BaseModel):
    id: int
    title: Optional[str] = None
    name: Optional[str] = None  # TV 模式下使用
    original_title: Optional[str] = None
    original_name: Optional[str] = None  # TV 模式下使用
    overview: Optional[str] = None
    release_date: Optional[str] = None
    first_air_date: Optional[str] = None  # TV 模式下使用
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    adult: bool = False
    vote_average: float = 0.0
    vote_count: int = 0
    popularity: float = 0.0
    genre_ids: List[int] = []
    media_type: Optional[str] = None

class TMDBSearchResponse(BaseModel):
    page: int = 1
    results: List[TMDBMovieResult]
    total_pages: int = 1
    total_results: int

# --- 本地存储 Schema ---

class MediaBase(BaseModel):
    title: str
    original_title: Optional[str] = None
    overview: Optional[str] = None
    release_date: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    adult: bool = False
    scraper_source: str
    scraper_id: str
    raw_data: Optional[Dict[str, Any]] = None

class MediaCreate(MediaBase):
    pass

class MediaRead(MediaBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

# 转换工具：从本地 Media 模型转换为 TMDB 格式
def to_tmdb_movie(media: Any, media_type: Optional[str] = None) -> TMDBMovieResult:
    # 优先从 raw_data 中恢复原始 TMDB 字段，如果没有则使用本地字段
    raw = media.raw_data or {}
    
    # 自动判断 media_type
    if not media_type:
        media_type = "tv" if "name" in raw or "first_air_date" in raw else "movie"

    res = TMDBMovieResult(
        id=int(media.scraper_id) if media.scraper_source == "tmdb" else media.id,
        overview=media.overview,
        poster_path=media.poster_path,
        backdrop_path=media.backdrop_path,
        adult=media.adult,
        vote_average=raw.get("vote_average", 0.0),
        vote_count=raw.get("vote_count", 0),
        popularity=raw.get("popularity", 0.0),
        genre_ids=raw.get("genre_ids", []),
        media_type=media_type
    )
    
    if media_type == "movie":
        res.title = media.title
        res.original_title = media.original_title
        res.release_date = media.release_date
    else:
        res.name = media.title
        res.original_name = media.original_title
        res.first_air_date = media.release_date
        
    return res
