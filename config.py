"""
AutoAPI - 多用户多AI-API管理工具
核心配置模块
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime

# 加载环境变量
load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).parent

# 配置文件路径
CONFIG_FILE = BASE_DIR / "config.yaml"
RULES_FILE = BASE_DIR / "rules.yaml"

# 默认配置
DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8001,
    "log_level": "INFO",
    "max_request_timeout": 120,
    "enable_metrics": True
}

# 日志配置
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": "autoapi.log",
            "mode": "a"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}


# 数据模型定义
class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: datetime
    version: str
    uptime: float


# 存储管理类
class Storage:
    """简化的存储类"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        logger = logging.getLogger(__name__)
        logger.info("Storage 初始化完成")
