"""PersonaIter — 人设迭代器配置模型。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from maibot_sdk import Field, PluginConfigBase

SUPPORTED_CONFIG_VERSION = "0.1.0"


class PersonaIterPluginOptions(PluginConfigBase):
    """插件级配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=True,
        description="是否启用插件。",
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={
            "hidden": True,
            "disabled": True,
            "label": "配置版本",
            "order": 99,
        },
    )
    optimize_prompt: str = Field(
        default="",
        description="优化指令：告诉 LLM 从什么角度去优化人设。留空则使用默认分析框架。",
        json_schema_extra={
            "label": "优化指令",
            "hint": "例如：语气再活泼一点、减少颜文字、多加入专业感",
            "order": 1,
        },
    )
    scheduled_time: str = Field(
        default="",
        description="定时执行时间（24h 格式 HH:MM，如 03:00）。留空禁用定时。",
        json_schema_extra={
            "label": "定时执行时间",
            "hint": "留空则仅手动触发",
            "placeholder": "03:00",
            "order": 2,
        },
    )
    default_hours: int = Field(
        default=24,
        description="分析的默认时间范围（小时）。",
        json_schema_extra={
            "label": "默认时间范围",
            "hint": "不带 --hours 参数时的默认分析范围",
            "order": 3,
        },
    )
    max_messages_per_stream: int = Field(
        default=100,
        description="每个聊天流最多拉取的消息数。",
        json_schema_extra={
            "label": "单流消息数上限",
            "hint": "每个聊天流最多拉取的消息条数",
            "order": 4,
        },
    )
    max_streams: int = Field(
        default=0,
        description="最多分析的聊天流数（0 = 不限制）。",
        json_schema_extra={
            "label": "聊天流数上限",
            "hint": "0 表示不限制",
            "order": 5,
        },
    )
    model: str = Field(
        default="",
        description="LLM 模型名，留空使用默认模型。",
        json_schema_extra={
            "label": "LLM 模型",
            "hint": "留空使用 MaiBot 默认模型",
            "order": 6,
        },
    )
    storage_dir: str = Field(
        default="suggestions",
        description="建议文件输出目录（相对插件目录）。",
        json_schema_extra={
            "label": "输出目录",
            "hint": "相对插件目录的路径",
            "order": 7,
        },
    )

    @classmethod
    def from_mapping(cls, raw_config: Mapping[str, Any]) -> "PersonaIterPluginOptions":
        """从 Runner 注入的原始配置字典解析插件配置。"""
        return cls.model_validate(dict(raw_config))


class PersonaIterPluginSettings(PluginConfigBase):
    """PersonaIter 插件完整配置。"""

    plugin: PersonaIterPluginOptions = Field(default_factory=PersonaIterPluginOptions)

    @classmethod
    def from_mapping(cls, raw_config: Mapping[str, Any], logger: Any) -> "PersonaIterPluginSettings":
        """从 Runner 注入的原始配置字典解析插件完整配置。

        Args:
            raw_config: Runner 注入的原始配置内容。
            logger: 适配通用签名保留的日志对象。

        Returns:
            PersonaIterPluginSettings: 规范化后的插件配置模型。
        """
        del logger
        return cls.model_validate(dict(raw_config))

    def validate_runtime_config(self, logger: Any) -> bool:
        """校验当前配置是否满足运行前提条件。

        Args:
            logger: 插件日志对象。

        Returns:
            bool: 若配置有效则返回 ``True``。
        """
        config_version = self.plugin.config_version
        if not config_version:
            logger.error(
                f"PersonaIter 配置缺少 plugin.config_version，"
                f"当前插件要求版本 {SUPPORTED_CONFIG_VERSION}"
            )
            return False

        if config_version != SUPPORTED_CONFIG_VERSION:
            logger.error(
                f"PersonaIter 配置版本不兼容: 当前为 {config_version}，"
                f"当前插件要求 {SUPPORTED_CONFIG_VERSION}"
            )
            return False

        return True
