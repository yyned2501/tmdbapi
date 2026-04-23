import os
from dynaconf import Dynaconf

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 初始化 Dynaconf
settings = Dynaconf(
    envvar_prefix="TMDB",  # 环境变量前缀，例如 TMDB_DATABASE__URL
    settings_files=[
        os.path.join(BASE_DIR, "config/default.toml"),
        os.path.join(BASE_DIR, "config/config.toml"),
    ],
    load_dotenv=True,
    base_dir=BASE_DIR,
)

# 强制规则：成人内容始终开启
# 无论配置文件如何设置，代码中强制覆盖为 True
settings.tmdb.include_adult = True

# 导出配置对象
config = settings

__all__ = ["config"]
