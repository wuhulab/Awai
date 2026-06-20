"""
AutoAPI - 规则引擎
根据 rules.json 配置,动态匹配模型名称到上游API和密钥。
支持模型映射、自动规则选择(优先级/负载均衡/随机)、key轮询和冷却机制。
"""

import json
import random
import logging
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from cooldown_manager import CooldownManager

logger = logging.getLogger(__name__)


class RuleEngine:
    """规则引擎，密钥直接从rules.json获取"""

    def __init__(self, base_dir: Path, cache_ttl: int = 60) -> None:
        self.base_dir = base_dir
        self.rules_file = base_dir / "rules.json"
        self.logger = logging.getLogger(__name__)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0
        self._cache_ttl: int = cache_ttl
        self._lock = threading.Lock()
        self.cooldown_manager = CooldownManager()

    def _load_rules(self, use_cache: bool = True) -> Dict[str, Any]:
        """加载规则配置（带缓存）"""
        if use_cache and self._cache is not None:
            if time.time() - self._cache_time < self._cache_ttl:
                return self._cache

        try:
            if self.rules_file.exists():
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    with self._lock:
                        self._cache = rules
                        self._cache_time = time.time()

                    self.cooldown_manager.configure(rules.get("settings", []))

                    return rules
            return {"model": [], "auto": [], "settings": []}
        except Exception as e:
            self.logger.error(f"加载规则失败: {e}")
            return {"model": [], "auto": [], "settings": []}

    def invalidate_cache(self) -> None:
        """手动清除缓存"""
        with self._lock:
            self._cache = None

    def get_exposed_model_rules(self) -> List[Dict[str, Any]]:
        """获取所有暴露的模型规则（用于外部转发）"""
        rules = self._load_rules(use_cache=True)
        model_rules = rules.get("model", [])

        # 过滤出 exposure=true 的规则
        exposed_rules = []
        for rule in model_rules:
            exposure = rule.get("exposure", True)
            if exposure:
                exposed_rules.append(rule)

        # 按优先级排序
        exposed_rules.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return exposed_rules

    def match_model_rule(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        根据模型名称匹配模型规则

        Args:
            model_name: 模型名称

        Returns:
            匹配的规则或 None
        """
        rules = self._load_rules(use_cache=True)
        model_rules = rules.get("model", [])

        # 按优先级排序
        model_rules.sort(key=lambda x: x.get("priority", 0), reverse=True)

        # 查找匹配的规则
        for rule in model_rules:
            mappings = rule.get("actions", {}).get("mappings", {})

            # 检查模型名称是否在映射中
            if model_name in mappings:
                self.logger.info(f"模型 {model_name} 匹配规则: {rule.get('name')}")
                return rule

        return None

    def get_auto_rule(self) -> Optional[Dict[str, Any]]:
        """
        获取启用的自动规则

        Returns:
            启用的自动规则或 None
        """
        rules = self._load_rules(use_cache=True)
        auto_rules = rules.get("auto", [])

        # 查找启用的规则
        for rule in auto_rules:
            enable = rule.get("enable", True)
            if enable:
                self.logger.info(f"找到启用的自动规则: {rule.get('name')}")
                return rule

        return None

    def select_by_priority(self, available_models: List[str]) -> Optional[str]:
        """
        按优先级选择模型（从高到低）

        根据 auto 规则中 quotation 的值作为优先级（值越大优先级越高）

        Args:
            available_models: 可用的模型列表

        Returns:
            选择的模型名称或 None
        """
        if not available_models:
            return None

        # 获取 auto 规则中的 quotation 优先级
        auto_rule = self.get_auto_rule()
        if not auto_rule:
            return None

        quotation = auto_rule.get("actions", {}).get("quotation", {})

        # 按 quotation 的值（优先级）从高到低排序
        prioritized_models = sorted(available_models, key=lambda x: quotation.get(x, 0), reverse=True)

        if prioritized_models:
            selected = prioritized_models[0]
            self.logger.info(f"按优先级选择模型: {selected} (优先级: {quotation.get(selected, 0)})")
            return selected

        return None

    def select_by_load_balancing(self, available_models: List[str]) -> Optional[str]:
        """
        按负载均衡选择模型（选择最少使用的）

        Args:
            available_models: 可用的模型列表

        Returns:
            选择的模型名称或 None
        """
        # 简化处理，随机选择
        if available_models:
            selected = random.choice(available_models)
            self.logger.info(f"按负载均衡选择模型: {selected}")
            return selected

        return None

    def select_by_randomly(self, available_models: List[str]) -> Optional[str]:
        """
        随机选择模型

        Args:
            available_models: 可用的模型列表

        Returns:
            选择的模型名称或 None
        """
        if available_models:
            selected = random.choice(available_models)
            self.logger.info(f"随机选择模型: {selected}")
            return selected

        return None

    def auto_select_model(self) -> Optional[str]:
        """
        根据自动规则选择模型

        Returns:
            选择的模型名称或 None
        """
        auto_rule = self.get_auto_rule()
        if not auto_rule:
            self.logger.warning("没有找到启用的自动规则")
            return None

        actions = auto_rule.get("actions", {})
        quotation = actions.get("quotation", {})
        rules_mode = actions.get("rules", "priority")

        # 获取可用的模型列表
        available_models = list(quotation.keys())
        if not available_models:
            self.logger.warning("自动规则中没有配置可用模型")
            return None

        # 根据模式选择
        if rules_mode == "priority":
            return self.select_by_priority(available_models)
        elif rules_mode == "load-balancing":
            return self.select_by_load_balancing(available_models)
        elif rules_mode == "randomly":
            return self.select_by_randomly(available_models)
        else:
            self.logger.warning(f"未知的自动选择模式: {rules_mode}，使用 priority")
            return self.select_by_priority(available_models)

    def resolve_model(self, model_name: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        解析模型名称，返回实际模型名、上游URL和密钥信息

        支持两种调用方式：
        1. 直接调用模型名（如 deepseek-V3）- 查找 model 规则映射
        2. 调用 auto 规则名（如 DeepSeek-auto）- 使用 auto 规则选择模型

        支持 key 轮询和冷却机制：
        - 当 key 是列表时，自动轮询选择可用的 key
        - 当某个 key 的某个模型触发 429 时，会进入冷却状态

        Args:
            model_name: 请求的模型名称

        Returns:
            (实际模型名, 上游URL, 密钥信息dict) 或 (None, None, None)
        """
        # 1. 先尝试匹配模型规则
        model_rule = self.match_model_rule(model_name)

        if model_rule:
            actions = model_rule.get("actions", {})
            mappings = actions.get("mappings", {})
            url = actions.get("url")
            api_keys = actions.get("key")  # 可能是字符串或列表

            # 映射实际模型名
            actual_model = mappings.get(model_name, model_name)

            # 选择可用的 key（支持轮询和冷却）
            selected_key = self.cooldown_manager.get_available_key(
                api_keys if isinstance(api_keys, list) else [api_keys], actual_model
            )

            if not selected_key:
                self.logger.error(f"所有 key 都在冷却中，无法处理请求: model={actual_model}")
                return None, None, None

            # 构建密钥信息
            key_info = {
                "provider": "deepseek",  # 从规则中可扩展
                "api_key": selected_key,
                "model": actual_model,  # 添加模型信息，用于冷却管理
            }

            self.logger.info(f"模型 {model_name} -> {actual_model}, URL: {url}, Key: {selected_key[:10]}...")
            return actual_model, url, key_info

        # 2. 如果没有匹配，检查是否是 auto 规则名称
        rules = self._load_rules(use_cache=True)
        auto_rules = rules.get("auto", [])

        for auto_rule in auto_rules:
            if auto_rule.get("enable", True) and auto_rule.get("name") == model_name:
                # 使用 auto 规则选择模型
                self.logger.info(f"匹配到 auto 规则: {model_name}")
                auto_model = self.auto_select_model()
                if auto_model:
                    model_rule = self.match_model_rule(auto_model)
                    if model_rule:
                        actions = model_rule.get("actions", {})
                        mappings = actions.get("mappings", {})
                        url = actions.get("url")
                        api_keys = actions.get("key")

                        actual_model = mappings.get(auto_model, auto_model)

                        # 选择可用的 key
                        selected_key = self.cooldown_manager.get_available_key(
                            api_keys if isinstance(api_keys, list) else [api_keys], actual_model
                        )

                        if not selected_key:
                            self.logger.error(f"所有 key 都在冷却中，无法处理请求: model={actual_model}")
                            return None, None, None

                        key_info = {"provider": "deepseek", "api_key": selected_key, "model": actual_model}

                        self.logger.info(
                            f"Auto选择模型 {auto_model} -> {actual_model}, URL: {url}, Key: {selected_key[:10]}..."
                        )
                        return actual_model, url, key_info

        # 3. 如果都没有匹配，尝试自动选择
        auto_model = self.auto_select_model()
        if auto_model:
            model_rule = self.match_model_rule(auto_model)
            if model_rule:
                actions = model_rule.get("actions", {})
                mappings = actions.get("mappings", {})
                url = actions.get("url")
                api_keys = actions.get("key")

                actual_model = mappings.get(auto_model, auto_model)

                # 选择可用的 key
                selected_key = self.cooldown_manager.get_available_key(
                    api_keys if isinstance(api_keys, list) else [api_keys], actual_model
                )

                if not selected_key:
                    self.logger.error(f"所有 key 都在冷却中，无法处理请求: model={actual_model}")
                    return None, None, None

                key_info = {"provider": "deepseek", "api_key": selected_key, "model": actual_model}

                self.logger.info(
                    f"自动选择模型 {auto_model} -> {actual_model}, URL: {url}, Key: {selected_key[:10]}..."
                )
                return actual_model, url, key_info

        self.logger.warning(f"无法解析模型: {model_name}")
        return None, None, None
