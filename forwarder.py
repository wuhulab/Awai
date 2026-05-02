"""
AutoAPI - API转发模块
负责将请求转发到上游API
"""

import httpx
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    熔断器
    防止持续请求失败的上游服务
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时时间（秒）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open
        self._lock = asyncio.Lock()

    async def record_success(self):
        """记录成功请求"""
        async with self._lock:
            self.failure_count = 0
            self.state = "closed"

    async def record_failure(self):
        """记录失败请求"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now().timestamp()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(f"熔断器打开，失败次数: {self.failure_count}")

    async def is_available(self) -> bool:
        """
        检查服务是否可用
        
        Returns:
            是否可用
        """
        async with self._lock:
            if self.state == "closed":
                return True
            
            if self.state == "open":
                # 检查是否可以进入半开状态
                if self.last_failure_time:
                    elapsed = datetime.now().timestamp() - self.last_failure_time
                    if elapsed >= self.recovery_timeout:
                        self.state = "half_open"
                        logger.info("熔断器进入半开状态")
                        return True
                return False
            
            # half_open 状态允许一次请求
            return True


class RetryHandler:
    """
    重试处理器
    处理请求重试逻辑
    """

    def __init__(self, max_attempts: int = 3, backoff_factor: int = 2, retry_on_status: list = None):
        """
        初始化重试处理器
        
        Args:
            max_attempts: 最大重试次数
            backoff_factor: 退避因子
            retry_on_status: 触发重试的状态码列表
        """
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.retry_on_status = retry_on_status or [429, 500, 502, 503, 504]

    def should_retry(self, status_code: int, attempt: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            status_code: HTTP 状态码
            attempt: 当前尝试次数
            
        Returns:
            是否应该重试
        """
        if attempt >= self.max_attempts:
            return False
        return status_code in self.retry_on_status

    def get_delay(self, attempt: int) -> float:
        """
        获取重试延迟时间
        
        Args:
            attempt: 当前尝试次数
            
        Returns:
            延迟时间（秒）
        """
        return self.backoff_factor ** attempt


class APIForwarder:
    """API请求转发器"""

    UPSTREAM_ENDPOINTS = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "azure": "https://{resource}.openai.azure.com",
        "google": "https://generativelanguage.googleapis.com/v1",
        "cohere": "https://api.cohere.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/api/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    }

    def __init__(self, timeout: int = 120, system_config=None):
        """
        初始化转发器
        
        Args:
            timeout: 默认超时时间
            system_config: 系统配置实例
        """
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self._client: Optional[httpx.AsyncClient] = None
        self.system_config = system_config
        
        # 从系统配置加载设置
        if system_config:
            self._load_config()
        else:
            self._init_defaults()

    def _init_defaults(self):
        """初始化默认配置"""
        self.connect_timeout = 10
        self.read_timeout = 60
        self.max_keepalive_connections = 20
        self.max_connections = 100
        self.keepalive_expiry = 30
        self.proxy_enabled = False
        self.proxy_http = None
        self.proxy_https = None
        self.retry_handler = RetryHandler()
        self.circuit_breaker_enabled = True
        self.circuit_breaker = CircuitBreaker()
        self.default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.custom_headers = {}

    def _load_config(self):
        """从系统配置加载设置"""
        # 超时配置
        timeout_config = self.system_config.get_timeout_config()
        self.connect_timeout = timeout_config.get("connect", 10)
        self.read_timeout = timeout_config.get("read", 60)
        
        # 连接池配置
        pool_config = self.system_config.get_connection_pool_config()
        self.max_keepalive_connections = pool_config.get("max_keepalive_connections", 20)
        self.max_connections = pool_config.get("max_connections", 100)
        self.keepalive_expiry = pool_config.get("keepalive_expiry", 30)
        
        # 代理配置
        proxy_config = self.system_config.get_proxy_config()
        self.proxy_enabled = proxy_config.get("enabled", False)
        self.proxy_http = proxy_config.get("http") if self.proxy_enabled else None
        self.proxy_https = proxy_config.get("https") if self.proxy_enabled else None
        
        # 重试配置
        retry_config = self.system_config.get_retry_config()
        self.retry_handler = RetryHandler(
            max_attempts=retry_config.get("max_attempts", 3),
            backoff_factor=retry_config.get("backoff_factor", 2),
            retry_on_status=retry_config.get("retry_on_status", [429, 500, 502, 503, 504])
        )
        
        # 熔断器配置
        cb_config = self.system_config.get_circuit_breaker_config()
        self.circuit_breaker_enabled = cb_config.get("enabled", True)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=cb_config.get("failure_threshold", 5),
            recovery_timeout=cb_config.get("recovery_timeout", 60)
        )
        
        # 请求头配置
        headers_config = self.system_config.get_headers_config()
        self.default_headers = headers_config.get("default", {
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self.custom_headers = headers_config.get("custom", {})
        
        self.logger.info("转发器配置加载完成")

    def _get_proxies(self) -> Optional[Dict[str, str]]:
        """
        获取代理配置
        
        Returns:
            代理配置字典或 None
        """
        if not self.proxy_enabled:
            return None
        
        proxies = {}
        if self.proxy_http:
            proxies["http://"] = self.proxy_http
        if self.proxy_https:
            proxies["https://"] = self.proxy_https
        
        return proxies if proxies else None

    def _get_client(self) -> httpx.AsyncClient:
        """
        获取 HTTP 客户端
        
        Returns:
            httpx.AsyncClient 实例
        """
        if self._client is None or self._client.is_closed:
            # 构建超时配置
            timeout = httpx.Timeout(
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=self.connect_timeout,
                pool=self.connect_timeout
            )
            
            # 构建连接池限制
            limits = httpx.Limits(
                max_keepalive_connections=self.max_keepalive_connections,
                max_connections=self.max_connections,
                keepalive_expiry=self.keepalive_expiry
            )
            
            # 构建默认请求头
            headers = {**self.default_headers, **self.custom_headers}
            
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                proxies=self._get_proxies(),
                headers=headers
            )
            
            self.logger.info(f"HTTP客户端已初始化: 连接池={self.max_connections}, 超时={self.timeout}s")
        
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self.logger.info("HTTP客户端已关闭")

    def get_endpoint(self, provider: str, **kwargs) -> str:
        """
        获取上游 API 端点
        
        Args:
            provider: 提供商名称
            **kwargs: 额外参数
            
        Returns:
            API 端点 URL
        """
        endpoint = self.UPSTREAM_ENDPOINTS.get(provider.lower())

        if not endpoint:
            raise ValueError(f"不支持的提供商: {provider}")

        # 处理占位符
        if "{resource}" in endpoint and kwargs.get("resource"):
            endpoint = endpoint.format(resource=kwargs["resource"])

        return endpoint.rstrip("/")

    def _merge_headers(self, base_headers: Dict[str, str], extra_headers: Dict[str, str] = None) -> Dict[str, str]:
        """
        合并请求头
        
        Args:
            base_headers: 基础请求头
            extra_headers: 额外请求头
            
        Returns:
            合并后的请求头
        """
        headers = {**base_headers}
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def forward_chat_completion(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: list,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 2048,
        timeout: Optional[int] = None,
        upstream_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        转发聊天补全请求到上游 API
        
        Args:
            provider: API 提供商
            api_key: API 密钥
            model: 模型名称
            messages: 消息列表
            stream: 是否流式响应
            temperature: 温度参数
            max_tokens: 最大令牌数
            timeout: 超时时间
            upstream_url: 可选，上游 API 完整 URL
            **kwargs: 其他参数
            
        Returns:
            API 响应数据
        """
        # 检查熔断器状态
        if self.circuit_breaker_enabled and not await self.circuit_breaker.is_available():
            raise Exception("服务暂时不可用（熔断器打开）")

        timeout = timeout or self.timeout
        attempt = 0

        while True:
            attempt += 1
            try:
                result = await self._do_forward_chat_completion(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    stream=stream,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    upstream_url=upstream_url,
                    **kwargs
                )
                
                # 记录成功
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_success()
                
                return result

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                
                # 检查是否需要重试
                if self.retry_handler.should_retry(status_code, attempt):
                    delay = self.retry_handler.get_delay(attempt)
                    self.logger.warning(f"请求失败 (状态码: {status_code})，{delay}s 后重试 (尝试 {attempt}/{self.retry_handler.max_attempts})")
                    await asyncio.sleep(delay)
                    continue
                
                # 记录失败
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_failure()
                
                raise

            except Exception as e:
                # 记录失败
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_failure()
                raise

    async def _do_forward_chat_completion(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: list,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 2048,
        timeout: Optional[int] = None,
        upstream_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行实际的转发请求
        """
        timeout = timeout or self.timeout

        # 构建URL和请求头
        if upstream_url:
            url = f"{upstream_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
        elif provider.lower() == "openai":
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

        elif provider.lower() == "anthropic":
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/messages"
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "anthropic-dangerous-direct-browser-access": "true"
            }
            payload = {
                "model": model,
                "max_tokens": max_tokens or 1024,
                "messages": messages,
                "stream": stream,
                **kwargs
            }

        elif provider.lower() == "deepseek":
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

        elif provider.lower() in ["groq", "qwen", "mistral", "cohere"]:
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

        else:
            raise ValueError(f"不支持的提供商: {provider}")

        # 发送请求
        try:
            client = self._get_client()
            if stream:
                async def stream_generator():
                    try:
                        self.logger.info(f"转发请求到 {url}")
                        async with client.stream('POST', url, json=payload, headers=headers, timeout=timeout) as response:
                            if response.status_code >= 400:
                                error_body = await response.aread()
                                error_text = error_body.decode('utf-8') if error_body else response.text
                                self.logger.error(f"上游API错误 {response.status_code}: {error_text[:200]}")
                                yield {
                                    "stream": True,
                                    "chunk": f'{{"error": "上游API错误 {response.status_code}: {error_text[:100]}..."}}',
                                    "content_type": "application/json"
                                }
                                return
                            content_type = response.headers.get("content-type", "text/plain")
                            async for chunk in response.aiter_text():
                                yield {
                                    "stream": True,
                                    "chunk": chunk,
                                    "content_type": content_type
                                }
                    except httpx.HTTPStatusError as e:
                        self.logger.error(f"HTTP错误: {e.response.status_code} - {str(e)}")
                        yield {
                            "stream": True,
                            "chunk": f'{{"error": "上游API错误: {e.response.status_code} {e.response.reason_phrase}"}}',
                            "content_type": "application/json"
                        }
                    except Exception as e:
                        self.logger.error(f"转发请求异常: {str(e)}")
                        yield {
                            "stream": True,
                            "chunk": f'{{"error": "转发失败: {str(e)[:50]}"}}',
                            "content_type": "application/json"
                        }

                return stream_generator()
            else:
                self.logger.info(f"转发请求到 {url}")
                response = await client.post(url, json=payload, headers=headers, timeout=timeout)

                if response.status_code >= 400:
                    error_text = response.text[:500] if response.text else ""
                    self.logger.error(f"上游API错误 {response.status_code}: {error_text}")
                    
                    # 检测 429 错误（速率限制）
                    if response.status_code == 429:
                        self.logger.warning(f"检测到 429 速率限制错误")
                        return {
                            "error": {
                                "message": f"上游API速率限制: {error_text[:100]}",
                                "type": "rate_limit_error",
                                "code": 429
                            }
                        }
                    
                    return {
                        "error": {
                            "message": f"上游API错误 {response.status_code}: {error_text[:100]}",
                            "type": "upstream_error",
                            "code": response.status_code
                        }
                    }

                try:
                    return response.json()
                except ValueError as e:
                    self.logger.error(f"JSON解析错误: {str(e)}, 响应内容: {response.text[:500]}")
                    raise Exception(f"上游API返回非JSON响应: {str(e)}")

        except httpx.TimeoutException:
            self.logger.error(f"请求超时: {url}")
            raise TimeoutError(f"请求超时 ({timeout}s)")

        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            raise Exception(f"API错误: {e.response.status_code}")

        except Exception as e:
            self.logger.error(f"转发请求失败: {str(e)}")
            raise

    async def forward_completion(
        self,
        provider: str,
        api_key: str,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 2048,
        timeout: Optional[int] = None,
        upstream_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        转发文本补全请求到上游 API
        """
        # 检查熔断器状态
        if self.circuit_breaker_enabled and not await self.circuit_breaker.is_available():
            raise Exception("服务暂时不可用（熔断器打开）")

        timeout = timeout or self.timeout
        attempt = 0

        while True:
            attempt += 1
            try:
                result = await self._do_forward_completion(
                    provider=provider,
                    api_key=api_key,
                    prompt=prompt,
                    model=model,
                    stream=stream,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    upstream_url=upstream_url,
                    **kwargs
                )
                
                # 记录成功
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_success()
                
                return result

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                
                # 检查是否需要重试
                if self.retry_handler.should_retry(status_code, attempt):
                    delay = self.retry_handler.get_delay(attempt)
                    self.logger.warning(f"请求失败 (状态码: {status_code})，{delay}s 后重试 (尝试 {attempt}/{self.retry_handler.max_attempts})")
                    await asyncio.sleep(delay)
                    continue
                
                # 记录失败
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_failure()
                
                raise

            except Exception as e:
                # 记录失败
                if self.circuit_breaker_enabled:
                    await self.circuit_breaker.record_failure()
                raise

    async def _do_forward_completion(
        self,
        provider: str,
        api_key: str,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 2048,
        timeout: Optional[int] = None,
        upstream_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行实际的文本补全转发请求
        """
        timeout = timeout or self.timeout

        if upstream_url:
            url = f"{upstream_url.rstrip('/')}/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
        elif provider.lower() == "openai":
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

        elif provider.lower() == "anthropic":
            raise NotImplementedError("Anthropic 不支持纯补全 API")

        else:
            endpoint = self.get_endpoint(provider)
            url = f"{endpoint}/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

        try:
            client = self._get_client()
            if stream:
                async def stream_generator():
                    try:
                        self.logger.info(f"转发补全请求到 {url}")
                        async with client.stream('POST', url, json=payload, headers=headers, timeout=timeout) as response:
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "text/plain")
                            async for chunk in response.aiter_text():
                                yield {
                                    "stream": True,
                                    "chunk": chunk,
                                    "content_type": content_type
                                }
                    except Exception as e:
                        self.logger.error(f"转发补全请求异常: {str(e)}")
                        yield {
                            "stream": True,
                            "chunk": f'{{"error": "转发失败: {str(e)[:50]}"}}',
                            "content_type": "application/json"
                        }

                return stream_generator()
            else:
                self.logger.info(f"转发补全请求到 {url}")
                response = await client.post(url, json=payload, headers=headers, timeout=timeout)
                response.raise_for_status()

                try:
                    return response.json()
                except ValueError as e:
                    self.logger.error(f"JSON解析错误: {str(e)}, 响应内容: {response.text[:500]}")
                    raise Exception(f"上游API返回非JSON响应: {str(e)}")

        except httpx.TimeoutException:
            self.logger.error(f"补全请求超时: {url}")
            raise TimeoutError(f"请求超时 ({timeout}s)")

        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            raise Exception(f"API错误: {e.response.status_code}")

        except Exception as e:
            self.logger.error(f"转发补全请求失败: {str(e)}")
            raise
