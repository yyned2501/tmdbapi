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

## 5. 连接自愈与恢复策略
### 5.1 数据库自愈
- `core/database.py` 统一管理异步引擎、连接池和会话工厂。
- 异步引擎必须开启连接预检测（`pool_pre_ping=True`），在从连接池借出连接前先验证可用性。
- 连接池必须配置连接回收时间（`pool_recycle`），降低数据库或网络层重启后陈旧连接长期驻留的概率。
- 当出现 `sqlalchemy.exc.InterfaceError`、`DBAPIError`、`connection is closed` 等可恢复错误时，必须执行连接池失效回收（`engine.dispose()`）并重建后续连接。
- 请求链路与后台任务都必须通过统一的数据库自愈包装调用，避免只修复主请求、不修复后台同步。

### 5.2 TMDB HTTP 客户端自愈
- `core/tmdb_client.py` 统一管理 `httpx.AsyncClient` 单例及其代理配置。
- 当代理重启、连接池污染、远端连接中断时，客户端必须主动关闭旧实例并创建新实例。
- 对网络层可恢复异常允许有限重试 1~2 次，禁止无限重试。
- 日志必须记录 `endpoint`、异常类型、异常详情、当前是否启用代理，便于区分 TMDB 故障与代理故障。

### 5.3 API 层降级策略
- `api/v1/tmdb_proxy.py` 中缓存读取、TMDB 请求、缓存写回、后台同步必须解耦处理，不能因为单点失败导致整条链路硬失败。
- 当数据库短时不可用时，允许跳过缓存读写与后台同步，只要 TMDB 请求成功，仍应向调用方返回结果。
- 当 TMDB 请求失败且存在过期缓存时，必须继续使用 stale cache 兜底。
- 当数据库恢复后，首个成功请求应能自动恢复缓存读写与后台同步，无需手动重启服务。

### 5.4 启动与恢复行为
- `api/main.py` 在应用启动阶段除建表外，还必须执行显式数据库探活。
- 若数据库暂不可用，启动日志必须明确标记当前处于“降级运行”还是“阻止启动”模式。
- 是否允许数据库不可用时继续启动，应由配置控制，避免在不同部署环境中行为不一致。

## 6. TMDB API 兼容性
本项目通过 `/3` 前缀的路由实现了对官方 TMDB API 的部分兼容，包括：
- `GET /3/search/movie`: 搜索电影，返回标准 TMDB 搜索响应。
- `GET /3/movie/{id}`: 获取电影详情，返回标准 TMDB 电影对象。
这使得本项目可以直接作为自定义 TMDB API 代理供其他支持 TMDB 的应用使用。

## 7. 扩展 MDC 刮削器
若要添加 MDC 刮削能力：
1. 在 `modules/scrapers/mdc.py` 中实现 `search` 和 `get_detail` 方法。
2. 在 `modules/scrapers/__init__.py` 的 `SCRAPERS` 字典中注册。
3. 业务逻辑和 API 路由将自动支持 `scraper=mdc` 参数。
