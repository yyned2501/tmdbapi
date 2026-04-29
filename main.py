import uvicorn
from api.main import app
from core.config import config
from core.logger import logger

def start_server():
    """启动 FastAPI 服务器"""
    logger.info("正在通过根目录入口启动 TMDB API 媒体元数据管理后端...")
    
    # 获取配置
    host = "0.0.0.0"
    port = 8000
    
    # 运行服务器
    uvicorn.run(
        "api.main:app", 
        host=host, 
        port=port, 
        # reload=True  # 开发模式下开启热重载
    )

if __name__ == "__main__":
    start_server()
