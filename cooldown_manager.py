"""
AutoAPI - API密钥冷却管理器
管理API密钥和模型的冷却状态。当上游API返回429(速率限制)错误时,
将对应的key+模型组合暂时冷却一段时间,并支持轮询选择可用key。
"""

import time
import threading
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class CooldownManager:
    """
    冷却管理器
    跟踪每个 key+模型组合的冷却状态，支持轮询机制
    """

    def __init__(self):
        self._cooldown_map: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._lock = threading.Lock()
        self._default_cooldown: int = 60
        self._key_model_cooldown_config: Dict[str, Dict[str, int]] = {}
        self._key_rotation_index: Dict[str, int] = {}

    def configure(self, settings: List[Dict[str, Any]]) -> None:
        """
        配置冷却管理器

        Args:
            settings: settings 配置列表
        """
        if not settings:
            return

        with self._lock:
            for setting in settings:
                self._default_cooldown = setting.get("cd", 60)
                self._key_model_cooldown_config = setting.get("key_model_cooldown", {})
                logger.info(f"冷却管理器配置完成: 默认冷却时长={self._default_cooldown}s")
                logger.info(f"特定 key+模型冷却配置: {len(self._key_model_cooldown_config)} 个 key")

    def get_cooldown_duration(self, api_key: str, model: str) -> int:
        """
        获取特定 key+模型组合的冷却时长

        Args:
            api_key: API 密钥
            model: 模型名称

        Returns:
            冷却时长（秒）
        """
        if api_key in self._key_model_cooldown_config:
            model_cd = self._key_model_cooldown_config[api_key].get(model)
            if model_cd:
                return model_cd

        return self._default_cooldown

    def trigger_cooldown(self, api_key: str, model: str, duration: Optional[int] = None) -> None:
        """
        触发冷却

        Args:
            api_key: API 密钥
            model: 模型名称
            duration: 冷却时长（秒），如果未指定则使用配置的时长
        """
        if duration is None:
            duration = self.get_cooldown_duration(api_key, model)

        cooldown_until = time.time() + duration

        with self._lock:
            self._cooldown_map[api_key][model] = cooldown_until

        logger.warning(
            f"触发冷却: key={api_key[:15]}..., model={model}, 冷却时长={duration}s, 直到={time.strftime('%H:%M:%S', time.localtime(cooldown_until))}"
        )

    def is_in_cooldown(self, api_key: str, model: str) -> bool:
        """
        检查 key+模型组合是否在冷却中

        Args:
            api_key: API 密钥
            model: 模型名称

        Returns:
            是否在冷却中
        """
        with self._lock:
            if api_key not in self._cooldown_map:
                return False

            if model not in self._cooldown_map[api_key]:
                return False

            cooldown_until = self._cooldown_map[api_key][model]
            current_time = time.time()

            if current_time < cooldown_until:
                remaining = int(cooldown_until - current_time)
                logger.debug(f"key={api_key[:15]}..., model={model} 仍在冷却中，剩余 {remaining}s")
                return True
            else:
                del self._cooldown_map[api_key][model]
                if not self._cooldown_map[api_key]:
                    del self._cooldown_map[api_key]
                logger.info(f"key={api_key[:15]}..., model={model} 冷却已结束")
                return False

    def get_available_key(self, api_keys: List[str], model: str) -> Optional[str]:
        """
        从 key 列表中选择一个可用的 key（支持轮询）

        Args:
            api_keys: API 密钥列表
            model: 模型名称

        Returns:
            可用的 API 密钥，如果都不可用则返回 None
        """
        if not api_keys:
            return None

        if isinstance(api_keys, str):
            api_keys = [api_keys]

        available_keys = [key for key in api_keys if not self.is_in_cooldown(key, model)]

        if not available_keys:
            logger.warning(f"所有 key 都在冷却中，model={model}")
            return None

        model_key = f"{model}_rotation"

        with self._lock:
            if model_key not in self._key_rotation_index:
                self._key_rotation_index[model_key] = 0

            index = self._key_rotation_index[model_key] % len(available_keys)
            selected_key = available_keys[index]

            self._key_rotation_index[model_key] = index + 1

        logger.info(f"轮询选择 key: {selected_key[:15]}... (索引={index}, 可用={len(available_keys)}/{len(api_keys)})")
        return selected_key

    def get_cooldown_status(self) -> Dict[str, Dict[str, float]]:
        """
        获取当前冷却状态

        Returns:
            冷却状态字典 {api_key: {model: remaining_seconds}}
        """
        current_time = time.time()
        status = {}

        with self._lock:
            for api_key, models in self._cooldown_map.items():
                key_status = {}
                for model, cooldown_until in models.items():
                    remaining = max(0, cooldown_until - current_time)
                    if remaining > 0:
                        key_status[model] = remaining

                if key_status:
                    status[api_key[:15] + "..."] = key_status

        return status

    def clear_cooldown(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """
        清除冷却状态

        Args:
            api_key: API 密钥，如果为 None 则清除所有
            model: 模型名称，如果为 None 则清除该 key 的所有模型
        """
        with self._lock:
            if api_key is None:
                self._cooldown_map.clear()
                logger.info("已清除所有冷却状态")
            elif model is None:
                if api_key in self._cooldown_map:
                    del self._cooldown_map[api_key]
                    logger.info(f"已清除 key={api_key[:15]}... 的所有冷却状态")
            else:
                if api_key in self._cooldown_map and model in self._cooldown_map[api_key]:
                    del self._cooldown_map[api_key][model]
                    if not self._cooldown_map[api_key]:
                        del self._cooldown_map[api_key]
                    logger.info(f"已清除 key={api_key[:15]}..., model={model} 的冷却状态")
