"""
AutoAPI - 系统配置管理
加载和管理 System.json 配置文件,提供超时、重试、代理、连接池、
熔断器、日志、缓存等子配置的读取方法,支持缓存和深度合并。
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SystemConfig:
    """
    系统配置管理器
    负责加载和管理 System.json 配置文件
    """

    def __init__(self, base_dir: Path, cache_ttl: int = 60) -> None:
        """
        初始化系统配置管理器
        """
        self.base_dir = base_dir
        self.config_file = base_dir / "System.json"
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0
        self._cache_ttl: int = cache_ttl
        self._lock = threading.Lock()

        # 默认配置
        self._defaults = {
            "error_messages": {"429": "429 请求过于频繁，请稍后重试", "500": "500 服务器内部错误，请稍后重试"},
            "forwarding": {
                "timeout": {"connect": 10, "request": 120, "read": 60},
                "retry": {"max_attempts": 3, "backoff_factor": 2, "retry_on_status": [429, 500, 502, 503, 504]},
                "proxy": {"enabled": False, "http": "", "https": ""},
                "connection_pool": {"max_keepalive_connections": 20, "max_connections": 100, "keepalive_expiry": 30},
                "streaming": {"chunk_size": 1024, "buffer_size": 8192},
                "rate_limit": {"enabled": True, "requests_per_second": 10, "burst": 20},
                "headers": {
                    "default": {"Content-Type": "application/json", "Accept": "application/json"},
                    "custom": {},
                },
                "circuit_breaker": {"enabled": True, "failure_threshold": 5, "recovery_timeout": 60},
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": "autoapi.log",
                "max_size_mb": 10,
                "backup_count": 5,
            },
            "cache": {"enabled": True, "ttl": 60, "max_size": 1000},
        }

    def _load_config(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        加载配置文件（带缓存）

        Args:
            use_cache: 是否使用缓存

        Returns:
            配置字典
        """
        if use_cache and self._cache is not None:
            if time.time() - self._cache_time < self._cache_ttl:
                return self._cache

        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # 移除 description 字段（仅用于文档说明）
                    config = self._remove_descriptions(config)
                    with self._lock:
                        self._cache = config
                        self._cache_time = time.time()
                    return config
            return self._defaults.copy()
        except Exception as e:
            logger.error(f"加载系统配置失败: {e}")
            return self._defaults.copy()

    def _remove_descriptions(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归移除配置中的 description 字段

        Args:
            config: 原始配置字典

        Returns:
            清理后的配置字典
        """
        result = {}
        for key, value in config.items():
            if key == "description":
                continue
            if isinstance(value, dict):
                result[key] = self._remove_descriptions(value)
            else:
                result[key] = value
        return result

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        深度合并两个字典

        Args:
            base: 基础字典
            override: 覆盖字典

        Returns:
            合并后的字典
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self) -> Dict[str, Any]:
        """
        获取完整配置

        Returns:
            完整配置字典
        """
        config = self._load_config()
        return self._deep_merge(self._defaults, config)

    def get_error_message(self, status_code: int) -> str:
        """
        获取错误消息

        Args:
            status_code: HTTP 状态码

        Returns:
            错误消息
        """
        config = self.get_config()
        error_messages = config.get("error_messages", {})
        return error_messages.get(str(status_code), f"{status_code} 服务器错误")

    def get_forwarding_config(self) -> Dict[str, Any]:
        """
        获取转发配置

        Returns:
            转发配置字典
        """
        config = self.get_config()
        return config.get("forwarding", self._defaults["forwarding"])

    def get_timeout_config(self) -> Dict[str, int]:
        """
        获取超时配置

        Returns:
            超时配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("timeout", self._defaults["forwarding"]["timeout"])

    def get_retry_config(self) -> Dict[str, Any]:
        """
        获取重试配置

        Returns:
            重试配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("retry", self._defaults["forwarding"]["retry"])

    def get_proxy_config(self) -> Dict[str, Any]:
        """
        获取代理配置

        Returns:
            代理配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("proxy", self._defaults["forwarding"]["proxy"])

    def get_connection_pool_config(self) -> Dict[str, Any]:
        """
        获取连接池配置

        Returns:
            连接池配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("connection_pool", self._defaults["forwarding"]["connection_pool"])

    def get_streaming_config(self) -> Dict[str, Any]:
        """
        获取流式响应配置

        Returns:
            流式响应配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("streaming", self._defaults["forwarding"]["streaming"])

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """
        获取速率限制配置

        Returns:
            速率限制配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("rate_limit", self._defaults["forwarding"]["rate_limit"])

    def get_headers_config(self) -> Dict[str, Any]:
        """
        获取请求头配置

        Returns:
            请求头配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("headers", self._defaults["forwarding"]["headers"])

    def get_circuit_breaker_config(self) -> Dict[str, Any]:
        """
        获取熔断器配置

        Returns:
            熔断器配置字典
        """
        forwarding = self.get_forwarding_config()
        return forwarding.get("circuit_breaker", self._defaults["forwarding"]["circuit_breaker"])

    def get_logging_config(self) -> Dict[str, Any]:
        """
        获取日志配置

        Returns:
            日志配置字典
        """
        config = self.get_config()
        return config.get("logging", self._defaults["logging"])

    def get_cache_config(self) -> Dict[str, Any]:
        """
        获取缓存配置

        Returns:
            缓存配置字典
        """
        config = self.get_config()
        return config.get("cache", self._defaults["cache"])

    def invalidate_cache(self) -> None:
        """手动清除缓存"""
        with self._lock:
            self._cache = None
            logger.info("系统配置缓存已清除")

    def reload_config(self) -> Dict[str, Any]:
        """
        重新加载配置

        Returns:
            新的配置字典
        """
        self.invalidate_cache()
        return self.get_config()
