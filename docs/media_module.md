# Media 媒体业务与缓存模块说明文档

`modules/media` 模块封装了本项目的核心业务数据结构、Pydantic 输入输出校验模式，以及本地搜索、刮削同步和数据库事务高并发自愈降级的业务控制逻辑。

---

## 1. 模块职责与调用关系

- **`models.py` (数据模型)**: 
  - `Media`: 物理存储刮削到本地的媒体（电影/剧集）元数据，声明了 `(scraper_source, scraper_id)` 的**联合唯一约束**（从底层物理杜绝多机并发重复插入）。
  - `APICache`: 物理存储 API 代理请求的源 JSON 响应数据。
- **`schemas.py` (数据模型校验与转换)**: 
  - 声明 Pydantic 校验和序列化模型（如 `MediaRead`, `TMDBMovieResult`, `TMDBSearchResponse`）。
  - 提供 `to_tmdb_movie` 转换函数（无缝将本地格式逆向适配为标准的 TMDB 官方 API 响应结构）。
- **`cache_service.py` (缓存机制)**: 
  - 计算排序参数生成的唯一哈希缓存键。
  - 提供缓存安全读（被动读取过期时**不执行物理删除**，彻底解决多机读取彻底过期缓存时的 `StaleDataError` 锁竞争冲突）。
  - 提供基于 PostgreSQL `ON CONFLICT` 语法的并发冲突自动复写和更新缓存的安全写入。
- **`service.py` (核心业务控制层)**:
  - `search_and_sync`: 搜索并同步远程电影到本地数据库，采用 **批量一次性 Select 校验的性能优化**。
  - 核心实现了 `IntegrityError` (并发唯一性约束冲突) 的业务自愈：一旦捕获到其他服务器抢先写入数据库的唯一冲突，**立即安全回滚（rollback）当前事务，并重新从库中查回最新写入的数据完整返回**。
  - `sync_results`: 批量后台静默同步数据，在并发写入冲突时安全回滚（以第一台写入的数据为准）。

---

## 2. 缓存业务接口 (`modules.media.cache_service`)

### `CacheService` 类公共接口说明

#### ① `get`
*   **用途**: 获取指定 Endpoint 和请求参数的缓存数据。
*   **输入参数**:
    *   `db` (`AsyncSession`, 必填): 数据库异步会话。
    *   `endpoint` (`str`, 必填): 端点相对路径。
    *   `params` (`Dict[str, Any]`, 必填): 完整的查询参数包。
*   **返回值**:
    *   `Tuple[Optional[Dict[str, Any]], bool]`:
        - 第一个元素为缓存的 JSON 响应数据字典（若无缓存或彻底过期则返回 `None`）。
        - 第二个元素为 `bool`，代表是否已经越过了优先缓存期（`prefer_cache_hours`）（若为 `True` 则代理接口会启动异步更新）。

#### ② `set`
*   **用途**: 使用 Postgres 的 `ON CONFLICT` 原子语法安全写入或复写 API 哈希缓存键，防并发冲突。
*   **输入参数**:
    *   `db` (`AsyncSession`, 必填): 数据库异步会话。
    *   `endpoint` (`str`, 必填): 端点相对路径。
    *   `params` (`Dict[str, Any]`, 必填): 完整的查询参数包。
    *   `data` (`Dict[str, Any]`, 必填): 要写入的原始 JSON 响应字典。
*   **返回值**: 无。

---

## 3. 业务逻辑控制层 (`modules.media.service`)

### `MediaService` 类公共接口说明

#### ① `search_and_sync`
*   **用途**: 使用指定刮削器（默认 `tmdb`）搜索电影并执行本地数据库同步。支持多机分布式唯一约束并发自愈回滚并重查，保证返回结果正确且 API 绝不报 500。
*   **输入参数**:
    *   `db` (`AsyncSession`, 必填): 数据库异步会话。
    *   `query` (`str`, 必填): 电影或剧集搜索词。
    *   `scraper_name` (`str`, 选填, 默认 `"tmdb"`): 执行刮削的刮削器键。
*   **返回值**:
    *   `List[Media]`: 同步并写入/更新完毕的本地 `Media` 数据对象列表。

#### ② `get_by_id`
*   **用途**: 根据本地自增主键 `id` 检索存储的单条媒体元数据。
*   **输入参数**:
    *   `db` (`AsyncSession`, 必填): 数据库异步会话。
    *   `media_id` (`int`, 必填): 本地元数据主键。
*   **返回值**:
    *   `Optional[Media]`: 查询到的 `Media` 对象；若未查询到则返回 `None`。

#### ③ `sync_results`
*   **用途**: 后台线程/异步任务调用的批量同步逻辑。基于批量 Select 进行冲突排查，在检测到并发底层唯一约束异常时自动回滚并跳过（以抢先一步写入成功的数据为准）。
*   **输入参数**:
    *   `db` (`AsyncSession`, 必填): 数据库异步会话。
    *   `results` (`List[ScraperMediaResult]`, 必填): 要同步的标准化刮削元数据结构列表。
*   **返回值**: 无。
