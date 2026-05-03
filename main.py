"""
AutoAPI - 主应用模块
FastAPI应用入口，提供API转发功能（简化版，密钥直接配置在rules.json中）
"""

import inspect
import logging
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config import DEFAULT_CONFIG, HealthResponse
from rules import RuleEngine
from forwarder import APIForwarder
from system_config import SystemConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_default_rules(base_dir: Path):
    """初始化默认规则"""
    logger.info("检查默认规则...")

    rules_file = base_dir / "rules.json"

    # 如果规则文件已存在，跳过
    if rules_file.exists() and rules_file.stat().st_size > 0:
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                existing_rules = json.load(f)
            if existing_rules.get("model") or existing_rules.get("auto"):
                logger.info(f"规则文件已存在，跳过初始化")
                return
        except:
            pass

    logger.info("创建默认规则...")

    # 默认规则配置（密钥直接配置在这里）
    default_rules = {
        "model": [
            {
                "name": "DeepSeek模型映射",
                "priority": 10,
                "actions": {
                    "url": "https://api.deepseek.com/v1",
                    "key": "your-deepseek-api-key-here",
                    "mappings": {
                        "deepseek-V3": "deepseek-chat",
                        "deepseek-V3.2": "deepseek-chat-20250611"
                    }
                },
                "exposure": "true"
            }
        ],
        "auto": [
            {
                "name": "DeepSeek-auto",
                "actions": {
                    "quotation": {
                        "deepseek-V3": 1,
                        "deepseek-V3.2": 2
                    },
                    "rules": "priority"
                },
                "enable": "true"
            }
        ]
    }

    try:
        with open(rules_file, 'w', encoding='utf-8') as f:
            json.dump(default_rules, f, ensure_ascii=False, indent=2)
        logger.info(f"默认规则已创建: {rules_file}")
        logger.info("请编辑 rules.json 配置文件，填入你的 API 密钥")
    except Exception as e:
        logger.error(f"创建默认规则失败: {e}")

# 初始化FastAPI应用
app = FastAPI(
    title="AutoAPI",
    description="AI-API转发工具 - 支持模型映射和自动路由（简化版）",
    version="2.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化组件
BASE_DIR = Path(__file__).parent

# 初始化系统配置
system_config = SystemConfig(BASE_DIR)

# 初始化规则引擎
rule_engine = RuleEngine(BASE_DIR)

# 初始化转发器（传入系统配置）
forwarder = APIForwarder(
    timeout=system_config.get_timeout_config().get("request", 120),
    system_config=system_config
)

# 初始化默认规则
init_default_rules(BASE_DIR)


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("AutoAPI 启动，HTTP客户端已初始化")
    
    # 应用日志配置
    log_config = system_config.get_logging_config()
    log_level = log_config.get("level", "INFO")
    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.info(f"日志级别设置为: {log_level}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("关闭HTTP客户端...")
    await forwarder.close()

# 应用启动时间
start_time = time.time()


# ==================== 根路由 ====================

@app.get("/", response_model=Dict)
async def root():
    """根路径"""
    return {
        "name": "AutoAPI",
        "version": "2.0.0",
        "description": "AI-API转发工具（简化版）",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        version="2.0.0",
        uptime=time.time() - start_time
    )


# ==================== 系统配置路由 ====================

@app.get("/api/system/config", tags=["系统配置"])
async def get_system_config():
    """
    获取系统配置
    
    Returns:
        系统配置信息
    """
    return system_config.get_config()


@app.post("/api/system/reload", tags=["系统配置"])
async def reload_system_config():
    """
    重新加载系统配置
    
    Returns:
        重新加载结果
    """
    config = system_config.reload_config()
    
    # 重新初始化转发器
    global forwarder
    await forwarder.close()
    forwarder = APIForwarder(
        timeout=system_config.get_timeout_config().get("request", 120),
        system_config=system_config
    )
    
    return {
        "message": "系统配置已重新加载",
        "config_keys": list(config.keys())
    }


@app.get("/api/system/forwarding", tags=["系统配置"])
async def get_forwarding_config():
    """
    获取转发配置
    
    Returns:
        转发配置信息
    """
    return system_config.get_forwarding_config()


# ==================== 规则管理路由 ====================

@app.get("/api/rules", tags=["规则管理"])
async def get_rules():
    """
    获取规则配置

    Returns:
        规则配置（model和auto列表）
    """
    rules = rule_engine._load_rules()
    return rules


@app.post("/api/rules/reload", tags=["规则管理"])
async def reload_rules():
    """
    重新加载规则配置

    Returns:
        重新加载结果
    """
    rule_engine.invalidate_cache()
    rules = rule_engine._load_rules(use_cache=False)
    return {
        "message": "规则已重新加载",
        "model_count": len(rules.get("model", [])),
        "auto_count": len(rules.get("auto", []))
    }


@app.get("/api/cooldown/status", tags=["冷却管理"])
async def get_cooldown_status():
    """
    获取当前冷却状态

    Returns:
        冷却状态信息
    """
    status = rule_engine.cooldown_manager.get_cooldown_status()
    return {
        "cooldown_status": status,
        "total_keys_in_cooldown": len(status)
    }


@app.post("/api/cooldown/clear", tags=["冷却管理"])
async def clear_cooldown(api_key: Optional[str] = None, model: Optional[str] = None):
    """
    清除冷却状态

    Args:
        api_key: API密钥（可选，不提供则清除所有）
        model: 模型名称（可选，不提供则清除该key的所有模型）

    Returns:
        操作结果
    """
    rule_engine.cooldown_manager.clear_cooldown(api_key, model)
    return {
        "message": "冷却状态已清除",
        "api_key": api_key,
        "model": model
    }


# ==================== 代理转发路由 ====================

@app.get("/v1/models", tags=["API代理"])
async def list_models():
    """
    获取可用模型列表

    返回 OpenAI 兼容格式的模型列表
    包括：
    - model 规则中 mappings 的模型
    - auto 规则的名称（作为虚拟模型）
    """
    rules = rule_engine._load_rules()
    model_rules = rules.get("model", [])
    auto_rules = rules.get("auto", [])

    models = []

    # 1. 添加 model 规则的映射模型
    for rule in model_rules:
        mappings = rule.get("actions", {}).get("mappings", {})
        for request_model, actual_model in mappings.items():
            models.append({
                "id": request_model,
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": rule.get("name", "unknown"),
                "permission": [],
                "root": actual_model,
                "parent": None
            })

    # 2. 添加 auto 规则作为虚拟模型
    for auto_rule in auto_rules:
        if auto_rule.get("enable", True):
            models.append({
                "id": auto_rule.get("name", "unknown"),
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": auto_rule.get("name", "unknown") + " (auto)",
                "permission": [],
                "root": "[auto]",
                "parent": None
            })

    return {
        "object": "list",
        "data": models
    }


@app.api_route("/v1/chat/completions", methods=["POST", "GET"], tags=["API代理"])
async def chat_completions(
    request: Request,
    model: Optional[str] = None
):
    """
    聊天补全代理接口

    统一入口，根据规则转发到不同的上游API
    """
    try:
        # 解析请求
        if request.method == "GET":
            # GET请求，参数在query string
            if not model:
                raise HTTPException(status_code=400, detail="缺少model参数")

            body = {"model": model}
        else:
            # POST请求
            body = await request.json()

        model = body.get("model", model)
        if not model:
            raise HTTPException(status_code=400, detail="缺少model参数")

        # 使用规则引擎解析模型
        actual_model, upstream_url, key_info = rule_engine.resolve_model(model)

        if not upstream_url or not key_info:
            raise HTTPException(
                status_code=400,
                detail=f"无法解析模型: {model}，请检查规则配置"
            )

        # 准备转发参数
        stream = body.get("stream", False)
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 2048)
        timeout = body.get("timeout", system_config.get_timeout_config().get("request", 120))
        messages = body.get("messages", [])

        # 调用转发器
        response = await forwarder.forward_chat_completion(
            provider=key_info["provider"],
            api_key=key_info["api_key"],
            model=actual_model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            upstream_url=upstream_url
        )

        # 处理流式响应
        if inspect.isasyncgen(response):
            # 流式响应，response是异步生成器
            async def generate():
                async for chunk_data in response:
                    yield chunk_data["chunk"]

            content_type = "text/plain"
            return StreamingResponse(generate(), media_type=content_type)
        elif isinstance(response, dict) and response.get("stream"):
            # 兼容旧格式
            stream_response = response["response"]
            content_type = response.get("content_type", "text/plain")

            async def generate():
                async for chunk in stream_response.aiter_text():
                    yield chunk

            return StreamingResponse(generate(), media_type=content_type)
        else:
            # 返回JSON响应
            if isinstance(response, dict) and response.get("error"):
                err = response["error"]
                
                # 处理 429 速率限制错误
                if err.get("code") == 429:
                    api_key = key_info.get("api_key")
                    model = key_info.get("model", actual_model)
                    
                    # 触发冷却
                    rule_engine.cooldown_manager.trigger_cooldown(api_key, model)
                    
                    logger.warning(f"触发冷却: key={api_key[:15]}..., model={model}")
                    
                    # 使用系统配置中的错误消息
                    error_msg = system_config.get_error_message(429)
                    
                    # 返回错误信息
                    raise HTTPException(
                        status_code=429,
                        detail=f"{error_msg}: {err.get('message', '速率限制')}"
                    )
                
                # 使用系统配置中的错误消息
                status_code = err.get("code", 502)
                error_msg = system_config.get_error_message(status_code) if status_code in [429, 500] else err.get("message", "上游API错误")
                
                raise HTTPException(
                    status_code=status_code,
                    detail=error_msg
                )
            return JSONResponse(content=response)

    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"上游API错误: {e.response.status_code} - {str(e)}")
        
        # 使用系统配置中的错误消息
        status_code = e.response.status_code
        error_msg = system_config.get_error_message(status_code) if status_code in [429, 500] else f"上游API错误: {status_code}"
        
        raise HTTPException(
            status_code=502,
            detail=error_msg
        )
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        logger.error(f"代理请求失败: {str(e)}")
        
        # 使用系统配置中的错误消息
        error_msg = system_config.get_error_message(500)
        
        raise HTTPException(status_code=500, detail=f"{error_msg}: {str(e)}")


@app.api_route("/v1/completions", methods=["POST", "GET"], tags=["API代理"])
async def completions(
    request: Request,
    model: Optional[str] = None,
    prompt: Optional[str] = None
):
    """
    文本补全代理接口
    """
    try:
        if request.method == "POST":
            body = await request.json()
        else:
            body = {
                "model": model,
                "prompt": prompt
            }

        model = body.get("model", model)
        if not model:
            raise HTTPException(status_code=400, detail="缺少model参数")

        # 使用规则引擎解析模型
        actual_model, upstream_url, key_info = rule_engine.resolve_model(model)

        if not upstream_url or not key_info:
            raise HTTPException(
                status_code=400,
                detail=f"无法解析模型: {model}"
            )

        # 调用转发器
        response = await forwarder.forward_completion(
            provider=key_info["provider"],
            api_key=key_info["api_key"],
            model=actual_model,
            prompt=body.get("prompt", prompt),
            stream=body.get("stream", False),
            temperature=body.get("temperature", 0.7),
            max_tokens=body.get("max_tokens", 2048),
            timeout=body.get("timeout", system_config.get_timeout_config().get("request", 120))
        )

        # 处理流式响应
        if inspect.isasyncgen(response):
            # 流式响应，response是异步生成器
            async def generate():
                async for chunk_data in response:
                    yield chunk_data["chunk"]

            content_type = "text/plain"
            return StreamingResponse(generate(), media_type=content_type)
        elif isinstance(response, dict) and response.get("stream"):
            # 兼容旧格式
            stream_response = response["response"]
            content_type = response.get("content_type", "text/plain")

            async def generate():
                async for chunk in stream_response.aiter_text():
                    yield chunk

            return StreamingResponse(generate(), media_type=content_type)
        else:
            # 返回JSON响应
            return JSONResponse(content=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"补全请求失败: {str(e)}")
        
        # 使用系统配置中的错误消息
        error_msg = system_config.get_error_message(500)
        
        raise HTTPException(status_code=500, detail=f"{error_msg}: {str(e)}")


# ==================== 直接转发路由 ====================

@app.api_route("/proxy/{path:path}", methods=["GET", "POST"], tags=["直接代理"])
async def direct_proxy(
    path: str,
    request: Request
):
    """
    直接代理接口

    直接指定完整URL和密钥进行转发，适用于特殊场景

    Headers:
        X-Upstream-URL: 上游API完整URL
        X-API-Key: API密钥
    """
    try:
        # 获取上游配置
        upstream_url = request.headers.get("X-Upstream-URL")
        api_key = request.headers.get("X-API-Key")

        if not upstream_url or not api_key:
            raise HTTPException(status_code=400, detail="缺少 X-Upstream-URL 或 X-API-Key header")

        # 解析请求体
        if request.method == "POST":
            body = await request.json()
        else:
            body = {}

        # 构建URL
        url = f"{upstream_url.rstrip('/')}/{path}"

        # 根据路径判断提供商（简化处理）
        provider = "openai"  # 默认
        if "anthropic" in upstream_url:
            provider = "anthropic"
        elif "deepseek" in upstream_url:
            provider = "deepseek"

        # 构建请求头
        headers = {}
        if provider == "openai" or provider == "deepseek":
            headers["Authorization"] = f"Bearer {api_key}"
            headers["Content-Type"] = "application/json"
        elif provider == "anthropic":
            headers["x-api-key"] = api_key
            headers["Content-Type"] = "application/json"
            headers["anthropic-version"] = "2023-06-01"

        # 处理流式响应
        stream = body.get("stream", False)
        timeout = body.get("timeout", system_config.get_timeout_config().get("request", 120))
        client = forwarder._get_client()

        if stream:
            async def generate():
                try:
                    async with client.stream('POST', url, json=body, headers=headers, timeout=timeout) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "text/plain")
                        async for chunk in response.aiter_text():
                            yield chunk
                except Exception as e:
                    logger.error(f"直接代理流式请求异常: {str(e)}")
                    yield f'{{"error": "转发失败: {str(e)[:50]}"}}'

            return StreamingResponse(generate(), media_type="text/plain")
        else:
            logger.info(f"直接代理请求到 {url}")
            response = await client.post(url, json=body, headers=headers, timeout=timeout)
            response.raise_for_status()

            try:
                result = response.json()
            except ValueError as e:
                logger.error(f"JSON解析错误: {str(e)}, 响应内容: {response.text[:500]}")
                raise Exception(f"上游API返回非JSON响应: {str(e)}")

            return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"直接代理请求失败: {str(e)}")
        
        # 使用系统配置中的错误消息
        error_msg = system_config.get_error_message(500)
        
        raise HTTPException(status_code=500, detail=f"{error_msg}: {str(e)}")


# ==================== 启动应用 ====================

if __name__ == "__main__":
    import uvicorn

    logger.info("启动 AutoAPI 服务（简化版）...")
    logger.info(f"API文档: http://{DEFAULT_CONFIG.get('host', '0.0.0.0')}:{DEFAULT_CONFIG.get('port', 8000)}/docs")

    uvicorn.run(
        app,
        host=DEFAULT_CONFIG.get("host", "0.0.0.0"),
        port=DEFAULT_CONFIG.get("port", 8000),
        log_level=system_config.get_logging_config().get("level", "info").lower()
    )
