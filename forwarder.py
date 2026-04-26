"""
AutoAPI - API转发模块
负责将请求转发到上游API
"""

import httpx
import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


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

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=30
                )
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def get_endpoint(self, provider: str, **kwargs) -> str:
        """获取上游API端点"""
        endpoint = self.UPSTREAM_ENDPOINTS.get(provider.lower())

        if not endpoint:
            raise ValueError(f"不支持的提供商: {provider}")

        # 处理占位符
        if "{resource}" in endpoint and kwargs.get("resource"):
            endpoint = endpoint.format(resource=kwargs["resource"])

        return endpoint.rstrip("/")

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
        转发聊天补全请求到上游API

        Args:
            provider: API提供商
            api_key: API密钥
            model: 模型名称
            messages: 消息列表
            stream: 是否流式响应
            temperature: 温度参数
            max_tokens: 最大令牌数
            timeout: 超时时间
            upstream_url: 可选，上游API完整URL（如果提供，优先使用此URL）
            **kwargs: 其他参数

        Returns:
            API响应数据
        """
        timeout = timeout or self.timeout

        # 构建URL和请求头
        if upstream_url:
            # 使用自定义URL
            url = f"{upstream_url.rstrip('/')}/chat/completions"
            # 通用请求头
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
            # OpenAI
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
            # Anthropic
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
            # DeepSeek - 与 OpenAI 兼容
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
            # 其他兼容 OpenAI 格式的提供商
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
                    self.logger.error(f"上游API错误 {response.status_code}: {response.text[:200]}")
                    return {
                        "error": {
                            "message": f"上游API错误 {response.status_code}: {response.text[:100]}",
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
        转发文本补全请求到上游API
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
