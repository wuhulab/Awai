"""
Awai - 图形化管理界面
基于 CustomTkinter 构建，支持：
- 仪表盘：服务状态监控、启动/停止控制
- 供应商配置：管理 API 提供商、密钥、模型映射
- 系统配置：编辑转发、超时、重试、代理等设置
- 自动规则：管理自动路由规则
- 冷却管理：查看和清除冷却状态
"""

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import customtkinter as ctk

try:
    import httpx
except ImportError:
    httpx = None

# 设置主题
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BASE_DIR = Path(__file__).parent
RULES_FILE = BASE_DIR / "rules.json"
SYSTEM_CONFIG_FILE = BASE_DIR / "System.json"

PROVIDER_PRESETS = [
    {
        "label": "🔥 fai.shunx.top (推荐)",
        "name": "fai.shunx 转发",
        "url": "https://fai.shunx.top/v1",
        "key": "sk-your-key-here",
        "mappings": {"gpt-4o": "gpt-4o"},
    },
    {
        "label": "✨ ai.shunx.top",
        "name": "ai.shunx 转发",
        "url": "https://ai.shunx.top/v1",
        "key": "sk-your-key-here",
        "mappings": {"gpt-4o": "gpt-4o"},
    },
    {
        "label": "OpenAI",
        "name": "OpenAI",
        "url": "https://api.openai.com/v1",
        "key": "sk-your-key-here",
        "mappings": {"gpt-4o": "gpt-4o", "gpt-4o-mini": "gpt-4o-mini", "o1": "o1", "o3-mini": "o3-mini"},
    },
    {
        "label": "Anthropic",
        "name": "Anthropic",
        "url": "https://api.anthropic.com/v1",
        "key": "sk-ant-your-key-here",
        "mappings": {"claude-sonnet-4": "claude-sonnet-4-20250514", "claude-haiku-3": "claude-3-haiku-20240307"},
    },
    {
        "label": "Google",
        "name": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1",
        "key": "AIza-your-key-here",
        "mappings": {"gemini-2.0-flash": "gemini-2.0-flash", "gemini-2.0-flash-lite": "gemini-2.0-flash-lite"},
    },
    {
        "label": "DeepSeek",
        "name": "DeepSeek",
        "url": "https://api.deepseek.com/v1",
        "key": "sk-your-deepseek-key",
        "mappings": {"deepseek-chat": "deepseek-chat", "deepseek-reasoner": "deepseek-reasoner"},
    },
    {
        "label": "GLM (智谱)",
        "name": "GLM 智谱",
        "url": "https://open.bigmodel.cn/api/paas/v4",
        "key": "your-zhipu-key",
        "mappings": {"glm-4": "glm-4", "glm-4-flash": "glm-4-flash"},
    },
    {
        "label": "Kimi (月之暗面)",
        "name": "Kimi 月之暗面",
        "url": "https://api.moonshot.cn/v1",
        "key": "sk-your-kimi-key",
        "mappings": {"kimi-k2": "kimi-k2", "moonshot-v1": "moonshot-v1-auto"},
    },
    {
        "label": "Qwen (通义千问)",
        "name": "Qwen 通义千问",
        "url": "https://dashscope.aliyuncs.com/api/v1",
        "key": "sk-your-qwen-key",
        "mappings": {"qwen-max": "qwen-max", "qwen-plus": "qwen-plus", "qwen-turbo": "qwen-turbo"},
    },
    {
        "label": "Groq",
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1",
        "key": "gsk-your-groq-key",
        "mappings": {"llama-3.3-70b": "llama-3.3-70b-versatile", "mixtral-8x7b": "mixtral-8x7b-32768"},
    },
    {
        "label": "Cohere",
        "name": "Cohere",
        "url": "https://api.cohere.ai/v1",
        "key": "your-cohere-key",
        "mappings": {"command-r": "command-r", "command-r-plus": "command-r-plus"},
    },
    {
        "label": "Mistral",
        "name": "Mistral",
        "url": "https://api.mistral.ai/v1",
        "key": "your-mistral-key",
        "mappings": {"mistral-large": "mistral-large-latest", "mistral-small": "mistral-small-latest"},
    },
    {
        "label": "OpenRouter",
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api/v1",
        "key": "sk-or-your-key-here",
        "mappings": {"model-name": "provider/model-name:free"},
    },
    {
        "label": "自定义 (空模板)",
        "name": "自定义供应商",
        "url": "https://api.example.com/v1",
        "key": "your-api-key",
        "mappings": {"model-name": "actual-model"},
    },
]


class AwaiUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Awai 管理控制台")
        self.geometry("768x480")
        self.minsize(640, 420)

        # 服务进程引用
        self.server_process: Optional[subprocess.Popen] = None
        self.server_start_time: float = 0
        self._monitor_active = True

        # 加载配置数据
        self.rules_data: Dict[str, Any] = self._load_json(RULES_FILE)
        self.system_data: Dict[str, Any] = self._load_json(SYSTEM_CONFIG_FILE)

        # 网格布局
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # 顶部标题栏
        self._build_header()

        # 主标签页
        self.tab_view = ctk.CTkTabview(self, corner_radius=6)
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.tab_view.grid_columnconfigure(0, weight=1)
        self.tab_view.grid_rowconfigure(0, weight=1)

        # 创建各个标签页
        self.tab_dashboard = self.tab_view.add("仪表盘")
        self.tab_providers = self.tab_view.add("供应商配置")
        self.tab_system = self.tab_view.add("系统配置")
        self.tab_auto_rules = self.tab_view.add("自动规则")
        self.tab_cooldown = self.tab_view.add("冷却管理")

        for tab in [self.tab_dashboard, self.tab_providers, self.tab_system, self.tab_auto_rules, self.tab_cooldown]:
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)

        # 构建各标签内容
        self._build_dashboard()
        self._build_providers()
        self._build_system_config()
        self._build_auto_rules()
        self._build_cooldown()

        # API 基础地址
        self.api_base = "http://localhost:8001"

        # 启动监控定时器
        self._start_monitors()

        # 关闭事件
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================== 工具方法 ====================

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载 {path.name} 失败: {e}")
        return {}

    @staticmethod
    def _save_json(path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _safe_get(self, d: dict, *keys, default=None):
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k, {})
            else:
                return default
        return d if d != {} else default

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray95", "gray10"))
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header, text="⚡ Awai 管理控制台", font=ctk.CTkFont(size=18, weight="bold"))
        title.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        self.status_label = ctk.CTkLabel(header, text="● 停止", font=ctk.CTkFont(size=12), text_color="gray")
        self.status_label.grid(row=0, column=1, padx=8, pady=10, sticky="e")

        self.uptime_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.uptime_label.grid(row=0, column=2, padx=(0, 16), pady=10, sticky="e")

    # ==================== 仪表盘 ====================

    def _build_dashboard(self):
        container = ctk.CTkScrollableFrame(self.tab_dashboard, corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure((0, 1), weight=1)

        # 状态卡片
        status_frame = ctk.CTkFrame(container, corner_radius=8)
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        status_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_status = self._make_stat_card(status_frame, "服务状态", "已停止", 0)
        self.card_models = self._make_stat_card(status_frame, "模型数量", "0", 1)
        self.card_providers = self._make_stat_card(status_frame, "供应商", "0", 2)
        self.card_auto_rules_count = self._make_stat_card(status_frame, "自动规则", "0", 3)

        # 控制按钮区域
        ctrl_frame = ctk.CTkFrame(container, corner_radius=8)
        ctrl_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ctrl_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(ctrl_frame, text="服务控制", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=12, pady=(8, 6), sticky="w"
        )

        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="▶ 启动服务",
            command=self._start_server,
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(size=12),
            height=30,
        )
        self.btn_start.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        self.btn_stop = ctk.CTkButton(
            ctrl_frame,
            text="■ 停止服务",
            command=self._stop_server,
            fg_color="#c62828",
            hover_color="#b71c1c",
            state="disabled",
            font=ctk.CTkFont(size=12),
            height=30,
        )
        self.btn_stop.grid(row=1, column=1, padx=12, pady=(0, 8), sticky="ew")

        self.btn_restart = ctk.CTkButton(
            ctrl_frame,
            text="↻ 重启服务",
            command=self._restart_server,
            fg_color="#f57c00",
            hover_color="#e65100",
            state="disabled",
            font=ctk.CTkFont(size=12),
            height=30,
        )
        self.btn_restart.grid(row=1, column=2, padx=12, pady=(0, 8), sticky="ew")

        # 快捷操作
        quick_frame = ctk.CTkFrame(container, corner_radius=8)
        quick_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8), padx=(0, 4))
        quick_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(quick_frame, text="快捷操作", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(8, 6), sticky="w"
        )

        quick_actions = [
            ("🔄 重新加载配置", self._reload_configs),
            ("📂 打开配置目录", self._open_config_dir),
            ("🌐 打开 Swagger 文档", self._open_swagger),
            ("📋 复制 API 地址", self._copy_api_url),
        ]
        for i, (text, cmd) in enumerate(quick_actions):
            btn = ctk.CTkButton(
                quick_frame,
                text=text,
                command=cmd,
                fg_color="transparent",
                border_width=1,
                anchor="w",
                font=ctk.CTkFont(size=11),
                height=26,
            )
            btn.grid(row=i + 1, column=0, padx=12, pady=2, sticky="ew")

        # 最近日志
        log_frame = ctk.CTkFrame(container, corner_radius=8)
        log_frame.grid(row=2, column=1, sticky="nsew", pady=(0, 8), padx=(4, 0))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="运行日志", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(8, 6), sticky="w"
        )

        self.log_textbox = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(size=10, family="Consolas"), wrap="word")
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.log_textbox.insert("0.0", "就绪 - 等待服务启动...\n")
        self.log_textbox.configure(state="disabled")

    def _make_stat_card(self, parent, title, value, col):
        card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("gray90", "gray20"))
        card.grid(row=0, column=col, padx=8, pady=14, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12), text_color="gray").grid(
            row=0, column=0, padx=12, pady=(10, 0)
        )
        lbl = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=26, weight="bold"))
        lbl.grid(row=1, column=0, padx=12, pady=(2, 10))
        return lbl

    def _log(self, msg: str):
        self.log_textbox.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_textbox.insert("end", f"[{ts}] {msg}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    # ==================== 供应商配置 ====================

    def _build_providers(self):
        container = ctk.CTkFrame(self.tab_providers, corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # 左侧列表
        left = ctk.CTkFrame(container, corner_radius=8, width=240)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="供应商列表", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        self.provider_listbox = ctk.CTkScrollableFrame(left, corner_radius=6)
        self.provider_listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_frame, text="＋ 新增", command=self._add_provider, font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, padx=2, sticky="ew"
        )
        ctk.CTkButton(
            btn_frame,
            text="✕ 删除",
            command=self._delete_provider,
            fg_color="#c62828",
            hover_color="#b71c1c",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, padx=2, sticky="ew")

        # 右侧详情
        right = ctk.CTkScrollableFrame(container, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        self.provider_detail_frame = right
        self._selected_provider: Optional[int] = None

        # 当前编辑的 provider 索引
        self._provider_widgets: Dict[str, Any] = {}

        self._refresh_provider_list()

    def _refresh_provider_list(self):
        for w in self.provider_listbox.winfo_children():
            w.destroy()

        models = self.rules_data.get("model", [])
        if not models:
            lbl = ctk.CTkLabel(
                self.provider_listbox, text="暂无供应商配置", font=ctk.CTkFont(size=12), text_color="gray"
            )
            lbl.pack(pady=20)
            self._show_provider_detail(None)
            return

        for i, provider in enumerate(models):
            name = provider.get("name", f"供应商 {i + 1}")
            url = provider.get("actions", {}).get("url", "")
            short_url = url.replace("https://", "").replace("http://", "")[:25]

            btn = ctk.CTkButton(
                self.provider_listbox,
                text=f"{name}\n{short_url}",
                command=lambda idx=i: self._select_provider(idx),
                fg_color="transparent" if i != self._selected_provider else ("gray60", "gray30"),
                border_width=1,
                anchor="w",
                height=50,
                font=ctk.CTkFont(size=12),
            )
            btn.pack(fill="x", padx=2, pady=2)

        if self._selected_provider is not None and self._selected_provider < len(models):
            self._show_provider_detail(self._selected_provider)
        else:
            self._selected_provider = 0 if models else None
            self._show_provider_detail(self._selected_provider)

    def _select_provider(self, idx: int):
        self._selected_provider = idx
        self._refresh_provider_list()

    def _show_provider_detail(self, idx: Optional[int]):
        for w in self.provider_detail_frame.winfo_children():
            w.destroy()

        if idx is None:
            ctk.CTkLabel(
                self.provider_detail_frame, text="请选择或新增一个供应商", font=ctk.CTkFont(size=14), text_color="gray"
            ).pack(pady=40)
            return

        models = self.rules_data.get("model", [])
        if idx >= len(models):
            return

        provider = models[idx]
        actions = provider.setdefault("actions", {})
        mappings = actions.setdefault("mappings", {})
        keys_raw = actions.get("key", "")
        if isinstance(keys_raw, str):
            keys = [keys_raw]
        else:
            keys = list(keys_raw) if keys_raw else [""]

        self._provider_widgets.clear()

        # 名称
        ctk.CTkLabel(self.provider_detail_frame, text="供应商名称", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        name_entry = ctk.CTkEntry(self.provider_detail_frame, font=ctk.CTkFont(size=13))
        name_entry.insert(0, provider.get("name", ""))
        name_entry.pack(fill="x", padx=12, pady=(0, 8))
        self._provider_widgets["name"] = name_entry

        # URL
        ctk.CTkLabel(self.provider_detail_frame, text="API 地址", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(4, 2)
        )
        url_entry = ctk.CTkEntry(self.provider_detail_frame, font=ctk.CTkFont(size=13))
        url_entry.insert(0, actions.get("url", ""))
        url_entry.pack(fill="x", padx=12, pady=(0, 8))
        self._provider_widgets["url"] = url_entry

        # 优先级
        ctk.CTkLabel(
            self.provider_detail_frame, text="优先级（数字越大优先级越高）", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=12, pady=(4, 2))
        priority_entry = ctk.CTkEntry(self.provider_detail_frame, font=ctk.CTkFont(size=13))
        priority_entry.insert(0, str(provider.get("priority", 0)))
        priority_entry.pack(fill="x", padx=12, pady=(0, 8))
        self._provider_widgets["priority"] = priority_entry

        # 暴露开关
        exp_frame = ctk.CTkFrame(self.provider_detail_frame, fg_color="transparent")
        exp_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(exp_frame, text="对外暴露", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        exp_var = ctk.BooleanVar(value=str(provider.get("exposure", "true")).lower() == "true")
        exp_switch = ctk.CTkSwitch(exp_frame, text="", variable=exp_var)
        exp_switch.pack(side="right")
        self._provider_widgets["exposure"] = exp_var

        # API 密钥
        ctk.CTkLabel(
            self.provider_detail_frame,
            text="API 密钥（每行一个，支持多密钥轮询）",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 2))
        keys_text = ctk.CTkTextbox(self.provider_detail_frame, height=80, font=ctk.CTkFont(size=12, family="Consolas"))
        keys_text.insert("0.0", "\n".join(keys))
        keys_text.pack(fill="x", padx=12, pady=(0, 8))
        self._provider_widgets["keys"] = keys_text

        # 模型映射
        ctk.CTkLabel(
            self.provider_detail_frame,
            text="模型映射（每行一个: 请求模型 = 上游模型）",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(8, 2))
        mappings_text = ctk.CTkTextbox(
            self.provider_detail_frame, height=150, font=ctk.CTkFont(size=12, family="Consolas")
        )
        mapping_lines = [f"{k} = {v}" for k, v in mappings.items()]
        mappings_text.insert("0.0", "\n".join(mapping_lines))
        mappings_text.pack(fill="x", padx=12, pady=(0, 8))
        self._provider_widgets["mappings"] = mappings_text

        # 保存按钮
        ctk.CTkButton(
            self.provider_detail_frame,
            text="💾 保存更改",
            command=lambda: self._save_provider(idx),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
        ).pack(padx=12, pady=(8, 20), fill="x")

    def _save_provider(self, idx: int):
        models = self.rules_data.setdefault("model", [])
        if idx >= len(models):
            return

        provider = models[idx]
        actions = provider.setdefault("actions", {})

        provider["name"] = self._provider_widgets["name"].get()
        actions["url"] = self._provider_widgets["url"].get()
        provider["priority"] = int(self._provider_widgets["priority"].get() or 0)
        provider["exposure"] = "true" if self._provider_widgets["exposure"].get() else "false"

        # 解析密钥
        keys_raw = self._provider_widgets["keys"].get("0.0", "end").strip()
        keys_list = [k.strip() for k in keys_raw.split("\n") if k.strip()]
        actions["key"] = keys_list if len(keys_list) > 1 else (keys_list[0] if keys_list else "")

        # 解析映射
        mappings_raw = self._provider_widgets["mappings"].get("0.0", "end").strip()
        mappings = {}
        for line in mappings_raw.split("\n"):
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                mappings[k.strip()] = v.strip()
            elif line:
                mappings[line] = line
        actions["mappings"] = mappings

        self._save_json(RULES_FILE, self.rules_data)
        self._log(f"供应商 '{provider['name']}' 配置已保存")
        self._refresh_provider_list()
        self._update_stats()

    def _add_provider(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("选择供应商模板")
        dialog.geometry("480x420")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="选择一个供应商模板快速添加，或使用自定义模板", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=16, pady=(14, 8), anchor="w")

        scroll = ctk.CTkScrollableFrame(dialog, corner_radius=6)
        scroll.pack(fill="both", expand=True, padx=12, pady=4)

        for preset in PROVIDER_PRESETS:
            frame = ctk.CTkFrame(scroll, corner_radius=6)
            frame.pack(fill="x", padx=4, pady=3)
            frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(frame, text=preset["label"], font=ctk.CTkFont(size=13, weight="bold")).grid(
                row=0, column=0, padx=10, pady=(6, 0), sticky="w"
            )
            ctk.CTkLabel(frame, text=preset["url"], font=ctk.CTkFont(size=11), text_color="gray").grid(
                row=1, column=0, padx=10, pady=(0, 4), sticky="w"
            )

            def choose(p=preset):
                models = self.rules_data.setdefault("model", [])
                new_provider = {
                    "name": p["name"],
                    "priority": 0,
                    "actions": {
                        "url": p["url"],
                        "key": p["key"],
                        "mappings": dict(p["mappings"]),
                    },
                    "exposure": "true",
                }
                models.append(new_provider)
                self._save_json(RULES_FILE, self.rules_data)
                self._selected_provider = len(models) - 1
                self._refresh_provider_list()
                self._log(f"已添加供应商 '{p['name']}'")
                self._update_stats()
                dialog.destroy()

            ctk.CTkButton(frame, text="选用", width=60, command=choose, font=ctk.CTkFont(size=11)).grid(
                row=0, column=1, rowspan=2, padx=8, pady=4
            )

    def _delete_provider(self):
        if self._selected_provider is None:
            return
        models = self.rules_data.get("model", [])
        if 0 <= self._selected_provider < len(models):
            name = models[self._selected_provider].get("name", "")
            del models[self._selected_provider]
            self._save_json(RULES_FILE, self.rules_data)
            self._selected_provider = min(self._selected_provider, len(models) - 1) if models else None
            self._refresh_provider_list()
            self._log(f"已删除供应商 '{name}'")
            self._update_stats()

    # ==================== 系统配置 ====================

    def _build_system_config(self):
        container = ctk.CTkScrollableFrame(self.tab_system, corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        self._sys_widgets: Dict[str, Any] = {}

        config = self.system_data

        # ---- 转发设置 ----
        self._build_section_header(container, "转发设置")
        forwarding = config.get("forwarding", {})

        timeout = forwarding.get("timeout", {})
        retry = forwarding.get("retry", {})
        proxy = forwarding.get("proxy", {})
        pool = forwarding.get("connection_pool", {})
        streaming = forwarding.get("streaming", {})
        cb = forwarding.get("circuit_breaker", {})
        rate_limit = forwarding.get("rate_limit", {})

        # 超时
        sf = ctk.CTkFrame(container, corner_radius=8)
        sf.pack(fill="x", padx=12, pady=4)
        sf.grid_columnconfigure((1, 3, 5), weight=1)
        ctk.CTkLabel(sf, text="连接超时 (s)").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["timeout_connect"] = ctk.CTkEntry(sf, width=80)
        self._sys_widgets["timeout_connect"].insert(0, str(timeout.get("connect", 10)))
        self._sys_widgets["timeout_connect"].grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf, text="请求超时 (s)").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["timeout_request"] = ctk.CTkEntry(sf, width=80)
        self._sys_widgets["timeout_request"].insert(0, str(timeout.get("request", 120)))
        self._sys_widgets["timeout_request"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf, text="读取超时 (s)").grid(row=0, column=4, padx=8, pady=8, sticky="w")
        self._sys_widgets["timeout_read"] = ctk.CTkEntry(sf, width=80)
        self._sys_widgets["timeout_read"].insert(0, str(timeout.get("read", 60)))
        self._sys_widgets["timeout_read"].grid(row=0, column=5, padx=4, pady=8, sticky="w")

        # 重试
        sf2 = ctk.CTkFrame(container, corner_radius=8)
        sf2.pack(fill="x", padx=12, pady=4)
        sf2.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(sf2, text="最大重试次数").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["retry_max"] = ctk.CTkEntry(sf2, width=80)
        self._sys_widgets["retry_max"].insert(0, str(retry.get("max_attempts", 3)))
        self._sys_widgets["retry_max"].grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf2, text="退避因子").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["retry_backoff"] = ctk.CTkEntry(sf2, width=80)
        self._sys_widgets["retry_backoff"].insert(0, str(retry.get("backoff_factor", 2)))
        self._sys_widgets["retry_backoff"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        # 代理
        sf3 = ctk.CTkFrame(container, corner_radius=8)
        sf3.pack(fill="x", padx=12, pady=4)
        sf3.grid_columnconfigure((1, 3), weight=1)

        self._sys_proxy_var = ctk.BooleanVar(value=proxy.get("enabled", False))
        ctk.CTkLabel(sf3, text="启用代理").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkSwitch(sf3, text="", variable=self._sys_proxy_var).grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf3, text="HTTP 代理").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._sys_widgets["proxy_http"] = ctk.CTkEntry(sf3)
        self._sys_widgets["proxy_http"].insert(0, proxy.get("http", ""))
        self._sys_widgets["proxy_http"].grid(row=1, column=1, columnspan=3, padx=4, pady=4, sticky="ew")

        ctk.CTkLabel(sf3, text="HTTPS 代理").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        self._sys_widgets["proxy_https"] = ctk.CTkEntry(sf3)
        self._sys_widgets["proxy_https"].insert(0, proxy.get("https", ""))
        self._sys_widgets["proxy_https"].grid(row=2, column=1, columnspan=3, padx=4, pady=4, sticky="ew")

        # 连接池
        sf4 = ctk.CTkFrame(container, corner_radius=8)
        sf4.pack(fill="x", padx=12, pady=4)
        sf4.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(sf4, text="最大连接数").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["pool_max_conn"] = ctk.CTkEntry(sf4, width=80)
        self._sys_widgets["pool_max_conn"].insert(0, str(pool.get("max_connections", 100)))
        self._sys_widgets["pool_max_conn"].grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf4, text="保活连接数").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["pool_keepalive"] = ctk.CTkEntry(sf4, width=80)
        self._sys_widgets["pool_keepalive"].insert(0, str(pool.get("max_keepalive_connections", 20)))
        self._sys_widgets["pool_keepalive"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf4, text="保活过期 (s)").grid(row=0, column=4, padx=8, pady=8, sticky="w")
        self._sys_widgets["pool_keepalive_expiry"] = ctk.CTkEntry(sf4, width=80)
        self._sys_widgets["pool_keepalive_expiry"].insert(0, str(pool.get("keepalive_expiry", 30)))
        self._sys_widgets["pool_keepalive_expiry"].grid(row=0, column=5, padx=4, pady=8, sticky="w")

        # 流式
        sf5 = ctk.CTkFrame(container, corner_radius=8)
        sf5.pack(fill="x", padx=12, pady=4)
        sf5.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(sf5, text="数据块大小 (bytes)").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["stream_chunk"] = ctk.CTkEntry(sf5, width=80)
        self._sys_widgets["stream_chunk"].insert(0, str(streaming.get("chunk_size", 1024)))
        self._sys_widgets["stream_chunk"].grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf5, text="缓冲区大小 (bytes)").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["stream_buffer"] = ctk.CTkEntry(sf5, width=80)
        self._sys_widgets["stream_buffer"].insert(0, str(streaming.get("buffer_size", 8192)))
        self._sys_widgets["stream_buffer"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        # ---- 熔断器 ----
        self._build_section_header(container, "熔断器设置")
        sf6 = ctk.CTkFrame(container, corner_radius=8)
        sf6.pack(fill="x", padx=12, pady=4)
        sf6.grid_columnconfigure((1, 3), weight=1)

        self._sys_cb_var = ctk.BooleanVar(value=cb.get("enabled", True))
        ctk.CTkLabel(sf6, text="启用熔断器").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkSwitch(sf6, text="", variable=self._sys_cb_var).grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf6, text="失败阈值").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._sys_widgets["cb_threshold"] = ctk.CTkEntry(sf6, width=80)
        self._sys_widgets["cb_threshold"].insert(0, str(cb.get("failure_threshold", 5)))
        self._sys_widgets["cb_threshold"].grid(row=1, column=1, padx=4, pady=4, sticky="w")

        ctk.CTkLabel(sf6, text="恢复超时 (s)").grid(row=1, column=2, padx=8, pady=4, sticky="w")
        self._sys_widgets["cb_recovery"] = ctk.CTkEntry(sf6, width=80)
        self._sys_widgets["cb_recovery"].insert(0, str(cb.get("recovery_timeout", 60)))
        self._sys_widgets["cb_recovery"].grid(row=1, column=3, padx=4, pady=4, sticky="w")

        # ---- 日志 ----
        self._build_section_header(container, "日志设置")
        logging_cfg = config.get("logging", {})

        sf7 = ctk.CTkFrame(container, corner_radius=8)
        sf7.pack(fill="x", padx=12, pady=4)
        sf7.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(sf7, text="日志级别").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["log_level"] = ctk.CTkComboBox(sf7, values=["DEBUG", "INFO", "WARNING", "ERROR"], width=120)
        self._sys_widgets["log_level"].set(logging_cfg.get("level", "INFO"))
        self._sys_widgets["log_level"].grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf7, text="日志文件").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["log_file"] = ctk.CTkEntry(sf7, width=150)
        self._sys_widgets["log_file"].insert(0, logging_cfg.get("file", "autoapi.log"))
        self._sys_widgets["log_file"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf7, text="最大文件 (MB)").grid(row=0, column=4, padx=8, pady=8, sticky="w")
        self._sys_widgets["log_max_size"] = ctk.CTkEntry(sf7, width=80)
        self._sys_widgets["log_max_size"].insert(0, str(logging_cfg.get("max_size_mb", 10)))
        self._sys_widgets["log_max_size"].grid(row=0, column=5, padx=4, pady=8, sticky="w")

        # ---- 缓存 ----
        self._build_section_header(container, "缓存设置")
        cache_cfg = config.get("cache", {})

        sf8 = ctk.CTkFrame(container, corner_radius=8)
        sf8.pack(fill="x", padx=12, pady=4)
        sf8.grid_columnconfigure((1, 3), weight=1)

        self._sys_cache_var = ctk.BooleanVar(value=cache_cfg.get("enabled", True))
        ctk.CTkLabel(sf8, text="启用缓存").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkSwitch(sf8, text="", variable=self._sys_cache_var).grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(sf8, text="缓存 TTL (s)").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self._sys_widgets["cache_ttl"] = ctk.CTkEntry(sf8, width=80)
        self._sys_widgets["cache_ttl"].insert(0, str(cache_cfg.get("ttl", 60)))
        self._sys_widgets["cache_ttl"].grid(row=0, column=3, padx=4, pady=8, sticky="w")

        # 错误消息
        self._build_section_header(container, "错误消息")
        err_cfg = config.get("error_messages", {})

        sf9 = ctk.CTkFrame(container, corner_radius=8)
        sf9.pack(fill="x", padx=12, pady=4)
        sf9.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(sf9, text="429 错误消息").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._sys_widgets["err_429"] = ctk.CTkEntry(sf9)
        self._sys_widgets["err_429"].insert(0, err_cfg.get("429", ""))
        self._sys_widgets["err_429"].grid(row=0, column=1, padx=4, pady=8, sticky="ew")

        ctk.CTkLabel(sf9, text="500 错误消息").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._sys_widgets["err_500"] = ctk.CTkEntry(sf9)
        self._sys_widgets["err_500"].insert(0, err_cfg.get("500", ""))
        self._sys_widgets["err_500"].grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        # 保存按钮
        ctk.CTkButton(
            container,
            text="💾 保存系统配置",
            command=self._save_system_config,
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
        ).pack(padx=12, pady=(16, 30), fill="x")

    def _build_section_header(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=8, pady=(16, 4))
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=17, weight="bold"), text_color=("navy", "cyan")).pack(
            anchor="w", padx=4
        )
        ctk.CTkFrame(frame, height=2, fg_color=("gray70", "gray30")).pack(fill="x", padx=4, pady=(4, 0))

    def _save_system_config(self):
        fwd = self.system_data.setdefault("forwarding", {})

        fwd["timeout"] = {
            "connect": int(self._sys_widgets["timeout_connect"].get() or 10),
            "request": int(self._sys_widgets["timeout_request"].get() or 120),
            "read": int(self._sys_widgets["timeout_read"].get() or 60),
        }
        fwd["retry"] = {
            "max_attempts": int(self._sys_widgets["retry_max"].get() or 3),
            "backoff_factor": int(self._sys_widgets["retry_backoff"].get() or 2),
            "retry_on_status": [429, 500, 502, 503, 504],
        }
        fwd["proxy"] = {
            "enabled": self._sys_proxy_var.get(),
            "http": self._sys_widgets["proxy_http"].get(),
            "https": self._sys_widgets["proxy_https"].get(),
        }
        fwd["connection_pool"] = {
            "max_connections": int(self._sys_widgets["pool_max_conn"].get() or 100),
            "max_keepalive_connections": int(self._sys_widgets["pool_keepalive"].get() or 20),
            "keepalive_expiry": int(self._sys_widgets["pool_keepalive_expiry"].get() or 30),
        }
        fwd["streaming"] = {
            "chunk_size": int(self._sys_widgets["stream_chunk"].get() or 1024),
            "buffer_size": int(self._sys_widgets["stream_buffer"].get() or 8192),
        }
        fwd["circuit_breaker"] = {
            "enabled": self._sys_cb_var.get(),
            "failure_threshold": int(self._sys_widgets["cb_threshold"].get() or 5),
            "recovery_timeout": int(self._sys_widgets["cb_recovery"].get() or 60),
        }

        self.system_data["logging"] = {
            "level": self._sys_widgets["log_level"].get(),
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": self._sys_widgets["log_file"].get(),
            "max_size_mb": int(self._sys_widgets["log_max_size"].get() or 10),
            "backup_count": 5,
        }

        self.system_data["cache"] = {
            "enabled": self._sys_cache_var.get(),
            "ttl": int(self._sys_widgets["cache_ttl"].get() or 60),
            "max_size": 1000,
        }

        self.system_data["error_messages"] = {
            "429": self._sys_widgets["err_429"].get(),
            "500": self._sys_widgets["err_500"].get(),
        }

        self._save_json(SYSTEM_CONFIG_FILE, self.system_data)
        self._log("系统配置已保存")

    # ==================== 自动规则 ====================

    def _build_auto_rules(self):
        container = ctk.CTkFrame(self.tab_auto_rules, corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # 顶部操作栏
        top = ctk.CTkFrame(container, corner_radius=8)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="自动路由规则", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=16, pady=12, sticky="w"
        )

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=16, pady=8)
        ctk.CTkButton(btn_frame, text="＋ 新增规则", command=self._add_auto_rule, font=ctk.CTkFont(size=12)).pack(
            side="left", padx=2
        )

        # 规则列表
        scroll = ctk.CTkScrollableFrame(container, corner_radius=8)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self._auto_rules_frame = scroll

        self._refresh_auto_rules()

    def _refresh_auto_rules(self):
        for w in self._auto_rules_frame.winfo_children():
            w.destroy()

        auto_rules = self.rules_data.get("auto", [])
        if not auto_rules:
            ctk.CTkLabel(
                self._auto_rules_frame, text="暂无自动规则", font=ctk.CTkFont(size=13), text_color="gray"
            ).pack(pady=30)
            return

        for i, rule in enumerate(auto_rules):
            self._build_auto_rule_card(i, rule)

    def _build_auto_rule_card(self, idx: int, rule: dict):
        card = ctk.CTkFrame(self._auto_rules_frame, corner_radius=8)
        card.pack(fill="x", padx=8, pady=5)
        card.grid_columnconfigure(1, weight=1)

        actions = rule.setdefault("actions", {})
        quotation = actions.setdefault("quotation", {})

        # 名称
        ctk.CTkLabel(card, text=f"规则名称", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(10, 2), sticky="w"
        )

        name_entry = ctk.CTkEntry(card, font=ctk.CTkFont(size=13))
        name_entry.insert(0, rule.get("name", ""))
        name_entry.grid(row=0, column=1, padx=10, pady=(10, 2), sticky="ew")
        name_entry.bind("<FocusOut>", lambda e, i=idx, w=name_entry: self._update_auto_rule_name(i, w.get()))

        # 启用开关
        enable_frame = ctk.CTkFrame(card, fg_color="transparent")
        enable_frame.grid(row=0, column=2, padx=10, pady=(10, 2), sticky="e")
        ctk.CTkLabel(enable_frame, text="启用", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        en_var = ctk.BooleanVar(value=str(rule.get("enable", "true")).lower() == "true")

        def toggle_enable(v, i=idx):
            rules = self.rules_data.setdefault("auto", [])
            if i < len(rules):
                rules[i]["enable"] = "true" if v else "false"
                self._save_json(RULES_FILE, self.rules_data)

        en_sw = ctk.CTkSwitch(
            enable_frame, text="", variable=en_var, command=lambda v=en_var, i=idx: toggle_enable(v.get(), i)
        )
        en_sw.pack(side="right")

        # 选择模式
        ctk.CTkLabel(card, text="选择模式", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=1, column=0, padx=10, pady=4, sticky="w"
        )
        mode_var = ctk.StringVar(value=actions.get("rules", "priority"))
        mode_menu = ctk.CTkComboBox(
            card, values=["priority", "load-balancing", "randomly"], variable=mode_var, width=140
        )

        def save_mode(choice, i=idx):
            rules = self.rules_data.setdefault("auto", [])
            if i < len(rules):
                rules[i].setdefault("actions", {})["rules"] = choice
                self._save_json(RULES_FILE, self.rules_data)

        mode_menu.configure(command=lambda c: save_mode(c))
        mode_menu.grid(row=1, column=1, padx=10, pady=4, sticky="w")

        # 模型优先级
        ctk.CTkLabel(
            card, text="模型优先级（每行一个: 模型名 = 优先级）", font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=2, column=0, padx=10, pady=(8, 2), sticky="nw")

        q_text = ctk.CTkTextbox(card, height=80, font=ctk.CTkFont(size=12, family="Consolas"))
        q_lines = [f"{k} = {v}" for k, v in quotation.items()]
        q_text.insert("0.0", "\n".join(q_lines))
        q_text.grid(row=2, column=1, columnspan=2, padx=10, pady=(8, 2), sticky="ew")

        # 保存和删除按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=3, padx=10, pady=(6, 10), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row,
            text="💾 保存",
            command=lambda i=idx, q=q_text: self._save_auto_rule(i, q),
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=2, fill="x", expand=True)
        ctk.CTkButton(
            btn_row,
            text="✕ 删除",
            command=lambda i=idx: self._delete_auto_rule(i),
            fg_color="#c62828",
            hover_color="#b71c1c",
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=2, fill="x", expand=True)

    def _update_auto_rule_name(self, idx: int, name: str):
        rules = self.rules_data.setdefault("auto", [])
        if idx < len(rules):
            rules[idx]["name"] = name
            self._save_json(RULES_FILE, self.rules_data)

    def _save_auto_rule(self, idx: int, q_textbox):
        rules = self.rules_data.setdefault("auto", [])
        if idx >= len(rules):
            return

        raw = q_textbox.get("0.0", "end").strip()
        quotation = {}
        for line in raw.split("\n"):
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                quotation[k.strip()] = int(v.strip())
            elif line:
                quotation[line] = 1

        rules[idx].setdefault("actions", {})["quotation"] = quotation
        self._save_json(RULES_FILE, self.rules_data)
        self._log(f"自动规则 '{rules[idx].get('name')}' 已保存")
        self._refresh_auto_rules()

    def _add_auto_rule(self):
        rules = self.rules_data.setdefault("auto", [])
        rules.append(
            {
                "name": "新自动规则",
                "actions": {
                    "quotation": {"model-name": 1},
                    "rules": "priority",
                },
                "enable": "true",
            }
        )
        self._save_json(RULES_FILE, self.rules_data)
        self._refresh_auto_rules()
        self._log("已添加自动规则")
        self._update_stats()

    def _delete_auto_rule(self, idx: int):
        rules = self.rules_data.get("auto", [])
        if 0 <= idx < len(rules):
            name = rules[idx].get("name", "")
            del rules[idx]
            self._save_json(RULES_FILE, self.rules_data)
            self._refresh_auto_rules()
            self._log(f"已删除自动规则 '{name}'")
            self._update_stats()

    # ==================== 冷却管理 ====================

    def _build_cooldown(self):
        container = ctk.CTkFrame(self.tab_cooldown, corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # 顶部
        top = ctk.CTkFrame(container, corner_radius=8)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="冷却状态管理", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=16, pady=12, sticky="w"
        )

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=16, pady=8)

        self.cooldown_auto_refresh = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            btn_frame, text="自动刷新", variable=self.cooldown_auto_refresh, font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="↻ 刷新", command=self._refresh_cooldown, font=ctk.CTkFont(size=12)).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btn_frame,
            text="✕ 全部清除",
            command=self._clear_all_cooldown,
            fg_color="#c62828",
            hover_color="#b71c1c",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=4)

        # 列表
        scroll = ctk.CTkScrollableFrame(container, corner_radius=8)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self._cooldown_frame = scroll

        self._refresh_cooldown()

    def _refresh_cooldown(self):
        for w in self._cooldown_frame.winfo_children():
            w.destroy()

        header = ctk.CTkFrame(self._cooldown_frame, corner_radius=6, fg_color=("gray85", "gray15"))
        header.pack(fill="x", padx=8, pady=2)
        header.grid_columnconfigure((0, 1, 2), weight=1)
        for i, t in enumerate(["API 密钥", "模型", "剩余时间"]):
            ctk.CTkLabel(header, text=t, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, padx=8, pady=6)

        status = {}

        if self._is_server_running():
            result = self._api_get("/api/cooldown/status")
            if result:
                status = result.get("cooldown_status", {})

        if not status:
            try:
                from cooldown_manager import CooldownManager

                cm = CooldownManager()
                cm.configure(self.rules_data.get("settings", []))
                status = cm.get_cooldown_status()
            except Exception:
                pass

        if not status:
            ctk.CTkLabel(
                self._cooldown_frame, text="✨ 当前没有冷却中的密钥", font=ctk.CTkFont(size=13), text_color="gray"
            ).pack(pady=30)
            return

        for api_key, models in status.items():
            for model, remaining in models.items():
                row = ctk.CTkFrame(self._cooldown_frame, corner_radius=4)
                row.pack(fill="x", padx=8, pady=1)
                row.grid_columnconfigure((0, 1, 2), weight=1)

                ctk.CTkLabel(row, text=api_key, font=ctk.CTkFont(size=11, family="Consolas")).grid(
                    row=0, column=0, padx=8, pady=4, sticky="w"
                )
                ctk.CTkLabel(row, text=model, font=ctk.CTkFont(size=11)).grid(
                    row=0, column=1, padx=8, pady=4, sticky="w"
                )

                remaining_str = f"{int(remaining)}s" if remaining > 0 else "已过期"
                ctk.CTkLabel(
                    row,
                    text=remaining_str,
                    font=ctk.CTkFont(size=11),
                    text_color="orange" if remaining > 0 else "gray",
                ).grid(row=0, column=2, padx=8, pady=4, sticky="w")

                ctk.CTkButton(
                    row,
                    text="清除",
                    width=60,
                    command=lambda k=api_key, m=model: self._clear_cooldown_item(k, m),
                    font=ctk.CTkFont(size=10),
                ).grid(row=0, column=3, padx=8, pady=2)

    def _clear_cooldown_item(self, api_key: str, model: str):
        if self._is_server_running():
            self._api_post("/api/cooldown/clear", {"api_key": api_key.replace("...", ""), "model": model})
        try:
            from cooldown_manager import CooldownManager

            cm = CooldownManager()
            cm.clear_cooldown(api_key.replace("...", ""), model)
        except Exception:
            pass
        self._log(f"已清除冷却: {api_key} / {model}")
        self._refresh_cooldown()

    def _clear_all_cooldown(self):
        if self._is_server_running():
            self._api_post("/api/cooldown/clear")
        try:
            from cooldown_manager import CooldownManager

            cm = CooldownManager()
            cm.clear_cooldown()
        except Exception:
            pass
        self._log("已清除所有冷却状态")
        self._refresh_cooldown()

        # 自动刷新冷却状态
        def auto_refresh_cooldown():
            while self._monitor_active:
                if hasattr(self, "cooldown_auto_refresh") and self.cooldown_auto_refresh.get():
                    self.after(0, self._refresh_cooldown)
                time.sleep(5)

        threading.Thread(target=auto_refresh_cooldown, daemon=True).start()

    # ==================== 服务控制 ====================

    def _start_server(self):
        if self.server_process and self.server_process.poll() is None:
            self._log("服务已运行中")
            return

        def run():
            try:
                self.server_start_time = time.time()
                self.server_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8001",
                        "--log-level",
                        "info",
                    ],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

                self.after(0, lambda: self._update_server_ui(True))

                for line in iter(self.server_process.stdout.readline, ""):
                    if line:
                        self.after(0, lambda l=line.rstrip(): self._log(l))
                    if self.server_process.poll() is not None:
                        break

                self.server_process.stdout.close()
                self.after(0, lambda: self._update_server_ui(False))
                if self.server_process:
                    self.server_process.wait()
            except Exception as e:
                self.after(0, lambda: self._log(f"启动失败: {e}"))
                self.after(0, lambda: self._update_server_ui(False))

        threading.Thread(target=run, daemon=True).start()

    def _stop_server(self):
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
            self._update_server_ui(False)
            self._log("服务已停止")

    def _restart_server(self):
        self._log("正在重启服务...")
        self._stop_server()
        time.sleep(0.5)
        self._start_server()

    def _update_server_ui(self, running: bool):
        if running:
            self.status_label.configure(text="● 运行中", text_color="#4caf50")
            self.card_status.configure(text="运行中", text_color="#4caf50")
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.btn_restart.configure(state="normal")
        else:
            self.status_label.configure(text="● 已停止", text_color="gray")
            self.card_status.configure(text="已停止", text_color="gray")
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.btn_restart.configure(state="disabled")
            self.uptime_label.configure(text="")

    def _update_stats(self):
        models = self.rules_data.get("model", [])
        auto_rules = self.rules_data.get("auto", [])

        total_mappings = sum(len(m.get("actions", {}).get("mappings", {})) for m in models)

        self.card_models.configure(text=str(total_mappings))
        self.card_providers.configure(text=str(len(models)))
        self.card_auto_rules_count.configure(text=str(len(auto_rules)))

    # ==================== 监控 ====================

    def _start_monitors(self):
        self._update_stats()

        def update_uptime():
            while self._monitor_active:
                if self.server_process and self.server_process.poll() is None:
                    elapsed = time.time() - self.server_start_time
                    hours, remainder = divmod(int(elapsed), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    uptime_str = f"运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}"
                    self.after(0, lambda s=uptime_str: self.uptime_label.configure(text=s))

                    health = self._api_get("/health")
                    if health:
                        self.after(0, lambda: self.card_status.configure(text="运行中", text_color="#4caf50"))
                time.sleep(2)

        threading.Thread(target=update_uptime, daemon=True).start()

    # ==================== API 交互 ====================

    def _is_server_running(self) -> bool:
        return self.server_process is not None and self.server_process.poll() is None

    def _api_get(self, path: str, timeout: int = 3):
        if httpx is None:
            return None
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{self.api_base}{path}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            return None
        return None

    def _api_post(self, path: str, params: dict = None, timeout: int = 3):
        if httpx is None:
            return None
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{self.api_base}{path}", params=params or {})
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            return None
        return None

    # ==================== 快捷操作 ====================

    def _reload_configs(self):
        self.rules_data = self._load_json(RULES_FILE)
        self.system_data = self._load_json(SYSTEM_CONFIG_FILE)
        self._refresh_provider_list()
        self._refresh_auto_rules()
        self._update_stats()
        self._log("配置已重新加载")

    def _open_config_dir(self):
        os.startfile(str(BASE_DIR))

    def _open_swagger(self):
        import webbrowser

        webbrowser.open("http://localhost:8001/docs")

    def _copy_api_url(self):
        self.clipboard_clear()
        self.clipboard_append("http://localhost:8001")
        self._log("API 地址已复制到剪贴板")

    # ==================== 关闭 ====================

    def _on_close(self):
        self._monitor_active = False
        self._stop_server()
        self.destroy()


if __name__ == "__main__":
    app = AutoAPIUI()
    app.mainloop()
