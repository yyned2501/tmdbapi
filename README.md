# TMDB API 媒体元数据管理后端 (Adult Unlocked)

本项目是一个基于 **FastAPI** 和 **PostgreSQL** 构建的 TMDB API 代理与媒体元数据管理服务。

## 🌟 核心特性

- **强制成人内容解锁**：底层自动注入 `include_adult=true`，确保所有请求均可获取成人资源。
- **TMDB API 完美兼容**：提供 `/3` 前缀路由，支持作为自定义 TMDB API 代理供其他应用（如 Telegram Userbots, 媒体服务器等）使用。
- **多来源刮削架构**：支持从 TMDB 获取数据，并预留了 MDC (Metadata Collector) 刮削接口。
- **高可用缓存系统**：基于 PostgreSQL 实现，支持“双重过期”与“Stale-While-Revalidate”机制。在缓存过期但未彻底失效时，优先尝试更新数据；若 TMDB 访问失败，自动回退使用过期缓存，确保服务高可用。
- **自动异步同步**：在请求数据的同时，自动将元数据异步同步到本地数据库。
- **全栈异步**：基于 `FastAPI` + `SQLAlchemy Async` + `HTTPX` 构建。

## 🛠️ 技术栈

- **框架**: FastAPI
- **数据库**: PostgreSQL
- **ORM**: SQLAlchemy (Async)
- **配置管理**: Dynaconf (TOML)
- **HTTP 客户端**: HTTPX

## 🚀 快速开始

### 1. 环境准备
确保已安装 Python 3.10+ 和 PostgreSQL。

### 2. 安装依赖
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt  # 如果有 requirements.txt
# 或者手动安装
pip install fastapi uvicorn sqlalchemy asyncpg httpx dynaconf toml pydantic-settings
```

### 3. 配置项目
复制配置示例并修改：
```powershell
copy config/config.example.toml config/config.toml
```
编辑 `config/config.toml`：
- 填入您的 `api_key` 和 `read_access_token`。
- 配置 PostgreSQL 数据库连接字符串。
- 如有需要，配置代理。

### 4. 启动服务
```powershell
.\.venv\Scripts\python.exe main.py
```
服务默认运行在 `http://localhost:8000`。

## 接口说明

### TMDB 兼容接口 (代理模式)
- `GET /3/search/movie?query=...`
- `GET /3/search/tv?query=...`
- `GET /3/movie/{id}`
- `GET /3/tv/{id}`
- `GET /3/tv/{id}/season/{number}`
- `GET /3/.../keywords`
- `GET /3/.../episode_groups`

### 本地管理接口
- `GET /api/v1/media/search?query=...`：搜索并同步数据。
- `GET /api/v1/media/{id}`：获取本地存储的媒体元数据。

## 📂 项目结构
- `api/`: FastAPI 路由定义。
- `core/`: 核心组件（配置、数据库、日志、TMDB 客户端）。
- `modules/`: 业务逻辑。
    - `media/`: 媒体模型、服务、缓存逻辑。
    - `scrapers/`: 刮削器实现。
- `config/`: 配置文件。
- `main.py`: 项目统一入口。

## 📝 开发规范
请参考 [`.clinerules`](.clinerules) 了解详细的开发规范。

## 📄 许可证
MIT License
