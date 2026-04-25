# 项目架构文档 (ARCHITECTURE.md)

## 1. 概述
本项目是一个基于 FastAPI 和 PostgreSQL 的媒体元数据管理后端，支持从 TMDB 和未来可能的 MDC (Metadata Collector) 获取数据。

## 2. 核心设计原则
- **统一入口**: 所有业务模块通过 `core` 包引用配置、日志和数据库。
- **强制成人内容解锁**: 在底层 `TMDBClient` 中硬编码 `include_adult=true`。
- **刮削器抽象 (Scraper Abstraction)**: 采用统一的 `BaseScraper` 接口，使系统能够轻松扩展新的元数据来源。
- **异步驱动**: 全栈异步实现，提升高并发下的性能。

## 3. 目录结构与职责
- `api/`: 接口层，定义 FastAPI 路由。
- `core/`: 核心层，包含配置加载、数据库连接、日志工具及底层 API 客户端。
- `modules/`: 业务逻辑层。
    - `media/`: 媒体元数据模型、Schema 及业务服务。
    - `scrapers/`: 刮削器实现（TMDB, MDC 预留）。
- `config/`: 配置层，存储 TOML 配置文件。

## 4. 数据流向
1. 用户发起 `GET /3/search/movie?query=xxx` (兼容 TMDB 格式) 请求。
2. `api/v1/tmdb_proxy.py` 拦截请求并生成缓存键。
3. **缓存检查**:
    - **命中新鲜缓存** (在 `prefer_cache_hours` 内): 直接返回缓存数据。
    - **命中过期缓存** (超过 `prefer_cache_hours` 但在 `cleanup_cache_hours` 内): 尝试请求 TMDB。
        - **TMDB 成功**: 更新缓存并返回新数据。
        - **TMDB 失败**: 回退使用过期缓存数据。
    - **缓存未命中/彻底过期**: 请求 TMDB。
        - **TMDB 成功**: 写入缓存并返回。
        - **TMDB 失败**: 返回错误响应。
4. **异步同步**: 请求成功后，异步触发 `media_service` 将结果持久化到 `media` 表。
5. 返回数据给用户。

## 6. TMDB API 兼容性
本项目通过 `/3` 前缀的路由实现了对官方 TMDB API 的部分兼容，包括：
- `GET /3/search/movie`: 搜索电影，返回标准 TMDB 搜索响应。
- `GET /3/movie/{id}`: 获取电影详情，返回标准 TMDB 电影对象。
这使得本项目可以直接作为自定义 TMDB API 代理供其他支持 TMDB 的应用使用。

## 5. 扩展 MDC 刮削器
若要添加 MDC 刮削能力：
1. 在 `modules/scrapers/mdc.py` 中实现 `search` 和 `get_detail` 方法。
2. 在 `modules/scrapers/__init__.py` 的 `SCRAPERS` 字典中注册。
3. 业务逻辑和 API 路由将自动支持 `scraper=mdc` 参数。
