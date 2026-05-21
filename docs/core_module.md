# Core 核心基础模块说明文档

`core` 模块是本项目的底层基础结构，负责整个应用的配置加载、日志格式化、数据库连接池及生命周期管理，以及底层 TMDB 官方 API 的复用连接客户端。

---

## 1. 模块职责与调用关系

- **`core.config` (配置加载)**: 负责使用 `dynaconf` 加载环境及本地配置文件。供整个项目（如 `core.database`、`core.tmdb_client` 和缓存组件）读取环境变量和策略配置。
- **`core.logger` (日志模块)**: 统一整编和格式化系统控制台/文件日志，方便 AI 运维 (`runner`) 或人工分析故障。
- **`core.database` (数据库组件)**: 核心连接池、异步会话控制、数据库断线自动探活、释放连接池等数据库自愈重试逻辑。
- **`core.tmdb_client` (TMDB 官方客户端)**: 封装 `httpx.AsyncClient`，提供代理路由、SSL 安全请求、网络超时或重置异常时的自动连接重建自愈机制。

---

## 2. 数据库组件 (`core.database`)

### 核心函数/接口说明

#### ① `ensure_database_ready`
*   **用途**: 在应用启动或异常恢复时，显式发起一次数据库测试（执行 `SELECT 1`），探测数据库连接可用性。
*   **输入参数**: 无。
*   **返回值**:
    *   `bool`: 若测试执行成功返回 `True`，发生任何异常（如连接失效）则记录错误并返回 `False`。

#### ② `is_database_connection_error`
*   **用途**: 分析数据库底层抛出的 Exception 是否属于“可自动恢复/网络中断”的数据库连接层错误。
*   **输入参数**:
    *   `exc` (`Exception`, 必填): 数据库层抛出的原始异常实例。
*   **返回值**:
    *   `bool`: 若是因 `InterfaceError` / `DBAPIError` 或断开管道等连接中断返回 `True`；否则返回 `False`。

#### ③ `run_with_db_recovery`
*   **用途**: 提供高级数据库重载保护，封装操作。在数据库连接丢失并触发可恢复错误时，自动执行自愈流程——释放旧引擎并重试操作。
*   **输入参数**:
    *   `operation` (`Callable[[], Awaitable[T]]`, 必填): 异步数据库回调操作，需返回一个 Awaitable。
    *   `context` (`str`, 必选命名参数): 当前执行动作的上下文描述（用于日志记录定位）。
    *   `retries` (`int`, 必选命名参数, 默认 `1`): 连接异常重试的次数上限。
*   **返回值**:
    *   `T`: 传入的 `operation` 成功执行后的原始返回值。

#### ④ `get_session`
*   **用途**: FastAPI 依赖注入项，为单个 API 请求周期创建、交付、并在请求结束时安全关闭的 `AsyncSession` 生成器。
*   **输入参数**: 无。
*   **返回值**:
    *   `AsyncGenerator[AsyncSession, None]`: 供请求调用的 SQLAlchemy 异步会话。

---

## 3. TMDB 官方 API 客户端 (`core.tmdb_client`)

### `TMDBClient` 类公共接口说明

#### ① `get_client`
*   **用途**: 获取当前的 `httpx.AsyncClient` 客户端实例，若为空或已被关闭则安全地惰性创建新实例。
*   **输入参数**: 无。
*   **返回值**:
    *   `httpx.AsyncClient`: 供外部发起 HTTP 请求的客户端。

#### ② `reset_client`
*   **用途**: 在检测到代理失效、网络重置或生命周期结束时，主动关闭并释放旧的异步客户端连接池。
*   **输入参数**:
    *   `reason` (`str`, 必填): 重置客户端的底层诱因描述。
*   **返回值**: 无。

#### ③ `get_full_params`
*   **用途**: 构建完整的 API 参数字典。主要用于强制注入内置的语言包参数（如 `zh-CN`）、成人过滤解锁（`include_adult=true`）以及当未配置 Bearer Token 时自动追加 `api_key` 参数。
*   **输入参数**:
    *   `params` (`Optional[Dict[str, Any]]`, 选填): 用户请求传入的原始参数字典。
*   **返回值**:
    *   `Dict[str, Any]`: 组装及注入完毕的完整查询参数包。

#### ④ `request`
*   **用途**: 底层统一的异步网络发起器，支持连接超时、重试逻辑。在捕获由于网络/代理重置引起的 httpx 连接错误时，自动尝试重置 HTTP 客户端连接池自愈并重试。
*   **输入参数**:
    *   `method` (`str`, 必填): HTTP 方法（如 `"GET"`, `"POST"`）。
    *   `endpoint` (`str`, 必填): 相对 API 端点（如 `"movie/popular"`）。
    *   `params` (`Optional[Dict[str, Any]]`, 选填): 查询参数字典。
    *   `headers` (`Optional[Dict[str, str]]`, 选填): 额外的头信息字典。
*   **返回值**:
    *   `Dict[str, Any]`: TMDB 官方返回的 JSON 响应数据包。

#### ⑤ `get`
*   **用途**: `request` 请求器的快捷 `GET` 形式封装。
*   **输入参数**: 与 `request` (排除 `method`) 保持一致。
*   **返回值**: 与 `request` 保持一致。
