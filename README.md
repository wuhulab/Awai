# AutoAPI - AI-API转发工具

## 项目简介

AutoAPI 是一个基于 FastAPI 的 AI-API 转发工具，支持模型映射和自动路由功能。设计用于解决多渠道、多模型的API管理和转发需求。

**核心特点**：
- 🔄 支持多种AI提供商（OpenAI、Anthropic、DeepSeek等）
- 🗺️ 强大的模型映射功能
- ⚡ 自动路由选择（优先级、负载均衡、随机）
- 📝 规则配置简单，使用JSON格式

## 技术栈

- **FastAPI** - Web 框架
- **Uvicorn** - ASGI 服务器
- **httpx** - HTTP 客户端

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化并启动

```bash
# Windows
start.bat

# 或手动
python startup.py  # 初始化数据
python main.py     # 启动服务
```

### 3. 访问服务

- 服务地址：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 配置文件

### rules.json - 规则配置

规则文件位于 `rules.json`，包含两个主要部分：`model` 和 `auto`。

#### 完整配置示例

```json
{
  "model": [
    {
      "name": "DeepSeek模型映射",
      "priority": 10,
      "actions": {
        "url": "https://api.deepseek.com/v1",
        "key": "我的DeepSeek密钥",
        "mappings": {
          "deepseek-V3": "deepseek-chat",
          "deepseek-V3.2": "deepseek-chat-20250611",
          "deepseek-coder": "deepseek-coder"
        }
      },
      "exposure": "true"
    },
    {
      "name": "OpenAI模型映射",
      "priority": 5,
      "actions": {
        "url": "https://api.openai.com/v1",
        "key": "我的OpenAI密钥",
        "mappings": {
          "gpt-4": "gpt-4-0613",
          "gpt-3.5": "gpt-3.5-turbo"
        }
      },
      "exposure": "true"
    }
  ],
  "auto": [
    {
      "name": "默认自动选择",
      "actions": {
        "quotation": {
          "deepseek-V3": 1,
          "deepseek-V3.2": 2,
          "gpt-4": 3
        },
        "rules": "priority"
      },
      "enable": "true"
    }
  ]
}
```

#### model 规则配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 规则名称 |
| priority | int | 否 | 优先级，数字越大优先级越高，默认0 |
| exposure | bool | 否 | 是否暴露给外部转发，true=允许，false=不允许（但auto规则可引用），默认true |
| actions | object | 是 | 规则动作配置 |
| actions.url | string | 是 | 上游API基础URL |
| actions.key | string | 是 | 密钥名称（对应keys.json中的key_name） |
| actions.mappings | object | 是 | 模型映射关系，key为请求模型名，value为实际上游模型名 |

#### auto 规则配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 规则名称 |
| enable | bool | 否 | 是否启用，默认true |
| actions | object | 是 | 规则动作配置 |
| actions.quotation | object | 是 | 可用模型列表，key为模型名，value为权重/优先级 |
| actions.rules | string | 否 | 选择模式：priority（按优先级，默认）、load-balancing（负载均衡）、randomly（随机） |

#### exposure 字段说明

- `"exposure": "true"` 或 `"exposure": true` - 允许外部转发使用此规则
- `"exposure": "false"` 或 `"exposure": false` - 不允许外部转发，但auto规则可以引用

#### rules 选择模式说明

- `"priority"` - 按优先级选择模型（优先级高的优先使用）
- `"load-balancing"` - 负载均衡模式（选择使用次数最少的模型）
- `"randomly"` - 随机选择模型

### keys.json - 密钥配置

```json
{
  "keys": [
    {
      "provider": "deepseek",
      "api_key": "sk-xxxxxxxxxxxxxxxx",
      "key_name": "我的DeepSeek密钥",
      "display_name": "DeepSeek主密钥",
      "created_at": "2024-01-01T00:00:00",
      "last_used": "2024-01-01T00:00:00",
      "is_active": true
    }
  ]
}
```

**注意**：`api_key` 字段包含实际密钥，仅在创建时返回一次，请妥善保管。

## API 接口

### 密钥管理

#### 生成新密钥
```bash
POST /api/keys/generate?provider=deepseek&key_name=我的密钥
```

#### 列出所有密钥
```bash
GET /api/keys
```

#### 重置密钥
```bash
POST /api/keys/reset/{key_id}
```

#### 删除密钥
```bash
DELETE /api/keys/{key_id}
```

### 规则管理

#### 获取规则配置
```bash
GET /api/rules
```

#### 重新加载规则
```bash
POST /api/rules/reload
```

### 代理接口

#### 聊天补全
```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "deepseek-V3",
  "messages": [
    {"role": "user", "content": "你好"}
  ]
}
```

#### 文本补全
```bash
POST /v1/completions
Content-Type: application/json

{
  "model": "deepseek-V3",
  "prompt": "从前有座山，"
}
```

#### 直接代理
```bash
POST /proxy/chat/completions
X-Upstream-URL: https://api.deepseek.com/v1
X-API-Key: your_api_key_here

{
  "model": "deepseek-chat",
  "messages": [...]
}
```

## 使用场景

### 场景1：简单的模型映射

将用户友好的模型名称映射到实际上游模型：

```json
{
  "model": [
    {
      "name": "我的模型映射",
      "priority": 10,
      "actions": {
        "url": "https://api.deepseek.com/v1",
        "key": "我的密钥",
        "mappings": {
          "V3": "deepseek-chat",
          "V3.2": "deepseek-chat-20250611"
        }
      },
      "exposure": "true"
    }
  ]
}
```

当请求 `model: "V3"` 时，自动映射为 `deepseek-chat`。

### 场景2：自动路由选择

配置自动选择规则：

```json
{
  "model": [
    {
      "name": "DeepSeek渠道",
      "priority": 10,
      "actions": {
        "url": "https://api.deepseek.com/v1",
        "key": "DeepSeek密钥",
        "mappings": {
          "V3": "deepseek-chat",
          "V3.2": "deepseek-chat-20250611"
        }
      },
      "exposure": "false"
    },
    {
      "name": "OpenAI渠道",
      "priority": 5,
      "actions": {
        "url": "https://api.openai.com/v1",
        "key": "OpenAI密钥",
        "mappings": {
          "GPT4": "gpt-4-0613"
        }
      },
      "exposure": "false"
    }
  ],
  "auto": [
    {
      "name": "智能路由",
      "actions": {
        "quotation": {
          "V3": 1,
          "V3.2": 2,
          "GPT4": 3
        },
        "rules": "priority"
      },
      "enable": "true"
    }
  ]
}
```

请求任意模型时，会根据 `quotation` 的优先级自动选择渠道。

### 场景3：禁用曝光但允许自动引用

```json
{
  "model": [
    {
      "name": "内部渠道",
      "priority": 10,
      "actions": {
        "url": "https://api.internal.com/v1",
        "key": "内部密钥",
        "mappings": {
          "internal-model": "internal-v1"
        }
      },
      "exposure": "false"
    }
  ],
  "auto": [
    {
      "name": "包含内部渠道",
      "actions": {
        "quotation": {
          "internal-model": 1
        },
        "rules": "priority"
      },
      "enable": "true"
    }
  ]
}
```

## 注意事项

1. **密钥安全**：`api_key` 字段仅在创建/重置时返回一次，请妥善保管
2. **规则优先级**：数字越大优先级越高，高优先级规则优先匹配
3. **exposure控制**：设为false的规则不能直接通过外部API调用，但可以被auto规则引用
4. **热更新**：修改 `rules.json` 后调用 `POST /api/rules/reload` 即可生效，无需重启服务

## 项目结构

```
autoapi/
├── main.py          # 主应用入口
├── config.py        # 配置模块
├── models.py        # 数据模型
├── storage.py       # 数据持久化
├── rules.py         # 规则引擎
├── forwarder.py     # API转发器
├── startup.py       # 初始化脚本
├── start.bat        # Windows启动脚本
├── requirements.txt # Python依赖
└── rules.json       # 规则配置（手动编辑）
```

## License

MIT License
