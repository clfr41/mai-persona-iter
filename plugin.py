"""
PersonaIter — 人设迭代插件

分析指定时间范围内的聊天记录，根据优化指令
让 LLM 分析交互模式并生成人设优化建议文件。

可定时自动执行（静默）或手动触发。
不会自动修改任何配置。
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, ClassVar

from maibot_sdk import MaiBotPlugin, Command, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .config import PersonaIterPluginSettings


# ---------------------------------------------------------------------------
# 插件主类
# ---------------------------------------------------------------------------

class PersonaIterPlugin(MaiBotPlugin):
    """分析聊天内容并生成人设优化建议。"""

    config_model: ClassVar = PersonaIterPluginSettings

    def __init__(self) -> None:
        super().__init__()
        self._plugin_dir: str = ""
        self._scheduler_task: asyncio.Task[None] | None = None
        self._running: bool = False

    async def on_load(self) -> None:
        """插件加载时初始化存储目录，启动定时器。"""
        self._plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._ensure_storage_dir()
        self._start_scheduler()
        self.ctx.logger.debug("PersonaIter 插件已加载")

    async def on_unload(self) -> None:
        """插件卸载时停止定时器。"""
        self._stop_scheduler()
        self.ctx.logger.debug("PersonaIter 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        """配置更新时重启定时器。"""
        if scope == "self":
            self._ensure_storage_dir()
            self._stop_scheduler()
            self._start_scheduler()
            self.ctx.logger.debug("PersonaIter 配置已更新")

    # ---- 定时调度 ----

    def _start_scheduler(self) -> None:
        """如果配置了定时时间，启动调度循环。"""
        time_str = (self.config.plugin.scheduled_time or "").strip()
        if not time_str:
            return
        if not re.match(r"^\d{1,2}:\d{2}$", time_str):
            self.ctx.logger.warning(f"定时时间格式无效: {time_str!r}，定时已禁用")
            return
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(time_str),
            name="persona_iter_scheduler",
        )
        self.ctx.logger.info(f"人设迭代定时器已启动: 每天 {time_str} 自动执行")

    def _stop_scheduler(self) -> None:
        """停止调度循环。"""
        task = self._scheduler_task
        if task is not None and not task.done():
            task.cancel()
        self._scheduler_task = None

    async def _scheduler_loop(self, time_str: str) -> None:
        """定时调度循环，每天在指定时间执行一次静默分析。"""
        try:
            target_h, target_m = [int(x) for x in time_str.split(":")]
        except (ValueError, TypeError):
            self.ctx.logger.error(f"无法解析定时时间: {time_str!r}")
            return

        while True:
            try:
                now = datetime.now()
                target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                wait_sec = (target - now).total_seconds()
                self.ctx.logger.debug(f"距下次人设分析还有 {wait_sec:.0f} 秒 ({time_str})")
                await asyncio.sleep(wait_sec)

                hours = self.config.plugin.default_hours
                self.ctx.logger.info(f"定时人设分析开始: {hours}h")
                try:
                    result = await self._run_analysis(hours)
                    if result:
                        filepath, summary = result
                        self.ctx.logger.info(f"定时人设分析完成: {filepath} ({summary})")
                    else:
                        self.ctx.logger.info("定时人设分析跳过: 无足够聊天记录")
                except Exception as exc:
                    self.ctx.logger.exception(f"定时人设分析失败: {exc}")

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                self.ctx.logger.debug("人设迭代定时器已取消")
                raise
            except Exception as exc:
                self.ctx.logger.exception(f"定时调度循环异常: {exc}")
                await asyncio.sleep(300)

    # ---- 内部辅助 ----

    def _ensure_storage_dir(self) -> None:
        """确保建议文件存储目录存在。"""
        storage = self._get_storage_dir()
        os.makedirs(storage, exist_ok=True)

    def _get_storage_dir(self) -> str:
        """返回建议文件存储目录的绝对路径。"""
        rel = (self.config.plugin.storage_dir or "suggestions").strip()
        return os.path.join(self._plugin_dir, rel)

    # ---- 命令 ----

    @Command(
        "persona_suggest",
        description="分析聊天记录并生成人设优化建议",
        pattern=r"^/persona_suggest\b",
        aliases=["/psuggest", "/人设建议"],
    )
    async def cmd_persona_suggest(self, **kwargs: Any) -> tuple[bool, str, int]:
        """手动触发人设分析。

        用法：/persona_suggest [--hours N]
        """
        stream_id = kwargs.get("stream_id", "")
        raw_text = kwargs.get("raw_message", "")

        hours = self.config.plugin.default_hours
        m = re.search(r"--hours\s+(\d+)", raw_text)
        if m:
            hours = int(m.group(1))

        await self.ctx.send.text(
            f"正在分析最近 {hours} 小时的聊天记录，请稍候...",
            stream_id,
        )

        try:
            result = await self._run_analysis(hours)
        except Exception as exc:
            self.ctx.logger.exception(f"人设分析失败: {exc}")
            await self.ctx.send.text(f"分析失败: {exc}", stream_id)
            return False, f"分析失败: {exc}", 1

        if result is None:
            await self.ctx.send.text(
                "未获取到足够的聊天记录，请扩大时间范围后重试。",
                stream_id,
            )
            return False, "无足够聊天记录", 1

        filepath, summary = result
        parts = [f"分析完成！建议文件: {filepath}", f"数据: {summary}"]
        if self.config.plugin.optimize_prompt.strip():
            parts.append("已参考优化指令进行分析")
        parts.append("请阅读建议文件后手动修改 bot_config，插件不会自动应用。")
        await self.ctx.send.text("\n".join(parts), stream_id)
        return True, f"建议已写入 {filepath}", 2

    # ---- 工具（LLM / Planner 调用）----

    @Tool(
        "persona_analyze",
        brief_description="分析聊天记录并生成人设优化建议文件",
        detailed_description=(
            "分析最近的聊天记录，根据配置的 optimize_prompt 方向，"
            "让 LLM 分析交互模式并生成人设优化建议 Markdown 文件。"
            "文件写入 suggestions/ 目录，不会自动修改任何配置。\n\n"
            "参数说明：\n"
            "- hours：integer，可选。分析的时间范围（小时）。"
            " 默认使用配置中的 default_hours。\n"
            "- force：boolean，可选。设为 true 可忽略当前是否已有分析中的状态检查。"
        ),
        parameters=[
            ToolParameterInfo(
                name="hours",
                param_type=ToolParamType.INTEGER,
                description="分析时间范围（小时），默认使用配置值",
                required=False,
            ),
            ToolParameterInfo(
                name="force",
                param_type=ToolParamType.BOOLEAN,
                description="设为 true 可强制重新分析，忽略正在运行中的状态",
                required=False,
                default=False,
            ),
        ],
    )
    async def tool_persona_analyze(self, hours: int | None = None, force: bool = False, **kwargs: Any) -> dict[str, Any]:
        """Planner 可调用的分析工具：分析聊天记录并写建议文件。"""
        if hours is None or hours <= 0:
            hours = self.config.plugin.default_hours

        if force and self._running:
            self._running = False

        try:
            result = await self._run_analysis(hours)
        except Exception as exc:
            self.ctx.logger.exception(f"Planner 调用分析失败: {exc}")
            return {"success": False, "error": str(exc)}

        if result is None:
            return {
                "success": False,
                "message": "未获取到足够的聊天记录，请扩大时间范围后重试",
            }

        filepath, summary = result
        return {
            "success": True,
            "message": "done",
            "filepath": filepath,
            "summary": summary,
        }

    # ---- 分析核心 ----

    async def _run_analysis(self, hours: int) -> tuple[str, str] | None:
        """执行完整的分析流程。"""
        if self._running:
            self.ctx.logger.debug("分析已在运行，跳过")
            return None
        self._running = True
        try:
            return await self._do_analysis(hours)
        finally:
            self._running = False

    async def _do_analysis(self, hours: int) -> tuple[str, str] | None:
        """实际分析逻辑。"""
        all_streams = await self._fetch_all_streams()
        if not all_streams:
            return None

        max_streams = self.config.plugin.max_streams
        if max_streams > 0:
            all_streams = all_streams[:max_streams]

        end_time = datetime.now(timezone.utc)
        start_ts = end_time.timestamp() - hours * 3600
        end_ts = end_time.timestamp()
        max_per_stream = self.config.plugin.max_messages_per_stream

        all_messages: list[dict[str, Any]] = []
        stream_summaries: list[str] = []

        for stream in all_streams:
            chat_id = stream.get("chat_id") or stream.get("stream_id") or ""
            if not chat_id:
                continue
            try:
                msgs = await self.ctx.message.get_by_time_in_chat(
                    chat_id=chat_id,
                    start_time=str(start_ts),
                    end_time=str(end_ts),
                )
            except Exception as exc:
                self.ctx.logger.debug(f"拉取 {chat_id} 失败: {exc}")
                continue
            if not msgs:
                continue
            msgs = msgs[-max_per_stream:]
            all_messages.extend(msgs)
            name = stream.get("stream_name") or stream.get("chat_id") or chat_id
            stream_summaries.append(f"- {name}: {len(msgs)} 条")

        if not all_messages:
            return None

        overview = "\n".join(stream_summaries)
        analysis = await self._llm_analyze(all_messages, overview, hours)

        date_str = end_time.strftime("%Y-%m-%d")
        filename = f"persona-suggest-{date_str}.md"
        filepath = os.path.join(self._get_storage_dir(), filename)

        content = self._build_suggestion_doc(date_str, hours, overview, analysis)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        self.ctx.logger.info(
            f"人设建议已写入 {filepath} "
            f"({len(all_messages)} 条 / {len(stream_summaries)} 个流)"
        )
        return filepath, f"分析 {len(all_messages)} 条消息，{len(stream_summaries)} 个聊天流"

    async def _fetch_all_streams(self) -> list[dict[str, Any]]:
        """获取所有可用的聊天流。"""
        streams: list[dict[str, Any]] = []
        for platform in ("", "xmpp", "qq", "discord"):
            try:
                r = await self.ctx.chat.get_all_streams(platform=platform)
                if r:
                    streams.extend(r)
            except Exception:
                continue
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for s in streams:
            sid = s.get("chat_id") or s.get("stream_id") or ""
            if sid and sid not in seen:
                seen.add(sid)
                unique.append(s)
        return unique

    async def _llm_analyze(
        self,
        messages: list[dict[str, Any]],
        overview: str,
        hours: int,
    ) -> str:
        """用 LLM 分析聊天内容。"""
        formatted = self._format_messages(messages, max_messages=100)
        optimize = (self.config.plugin.optimize_prompt or "").strip()

        model_kw = {}
        if self.config.plugin.model.strip():
            model_kw["model"] = self.config.plugin.model.strip()

        user_section = ""
        if optimize:
            user_section = f"""
## 用户自定义优化指令
{optimize}

> ⚠️ 以上是用户手动填写的优化方向。如果和默认提示词有冲突，**请优先以用户的指令为准**。用户更清楚自己想要什么。
"""

        prompt = f"""你是一个人设一致性分析师。请分析以下聊天记录，追踪 Bot 的人设是否在一天对话中保持稳定。

分析目标：**不随用户喜好改变人设，而是评估人设自身的执行情况。**
人设提示词是 Bot 的"性格剧本"，你要看 Bot 有没有按剧本演，在哪里偏离了。

默认提示词：
分析原则和方法：
- 将一天中的对话按时间顺序分段，观察人设在每个阶段的表现
- 识别 Bot 对话中情感/语气/态度发生明显变化的节点
- 判断变化是合理的上下文适应，还是人设执行不一致
- 指出具体是**哪一段对话**导致或体现了偏离
- 给出优化方向：强化人设定力、调整人设中对特定场景的描述、或补充缺失的设定
- **不要为了迎合用户而建议改变人设本身**，除非人设存在内部矛盾

{user_section}
分析范围：最近 {hours} 小时
涉及聊天流：
{overview}

聊天记录（按时间顺序）：
{formatted}

请按以下结构输出分析结果：

## 人设演变追踪
按时间顺序，列出 Bot 在各阶段的情感/语气状态：
- 阶段一（起始状态）：情感基调、语气、活跃程度
- 阶段二（中间状态）：是否发生了变化？发生了什么？
- 阶段三（最终状态）：与起始状态是否一致？有多大偏差？
- （如有更多阶段请补充）

## 关键偏差节点
列出人设执行中偏离原始设定的具体对话片段，格式：
- **对话片段**：（引用原文，标明是哪一段）
- **表现**：实际回复与原本人设的差异
- **可能原因**：人设提示词不够明确 / 场景未覆盖 / LLM 自由发挥

## 优化方向
3-5 条建议，每条包含：
- 问题描述
- 优化方向（强化、补充、明确化）
- 建议调整的人设描述片段

## 建议的人设调整（直接可用）
用一段话描述优化后的人设，仅包含需要调整的部分。

注意：
- 基于实际对话观察，不要臆想
- 输出中文
- 不要建议"变得更迎合用户"——人设是第一位的"""

        result = await self.ctx.llm.generate(prompt, **model_kw)
        if not result.get("success"):
            raise RuntimeError(f"LLM 分析失败: {result.get('response', '未知')}")

        return result["response"].strip()

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]], max_messages: int = 100) -> str:
        """格式化消息列表供 LLM 使用。"""
        lines: list[str] = []
        for msg in messages[-max_messages:]:
            info = msg.get("message_info", {}) or {}
            user = info.get("user_info", {}) or {}
            sender = user.get("user_nickname") or user.get("user_id") or "未知"
            raw = msg.get("raw_message") or msg.get("processed_plain_text") or ""
            if isinstance(raw, list):
                parts = []
                for seg in raw:
                    if isinstance(seg, dict) and seg.get("type") == "text":
                        parts.append(str(seg.get("data", "")))
                text = "".join(parts)
            else:
                text = str(raw)
            if text:
                lines.append(f"[{sender}]: {text[:200]}")
        return "\n".join(lines)

    @staticmethod
    def _build_suggestion_doc(date_str: str, hours: int, overview: str, analysis: str) -> str:
        """组装建议文件的 Markdown 内容。"""
        return f"""# 人设优化建议 - {date_str}

> 自动生成 by PersonaIter · 分析范围：最近 {hours} 小时

---

## 分析来源

{overview}

---

{analysis}

---

## 重要提示

- 本文件由插件自动生成，仅供参考
- 上方「建议的人设描述」可直接复制到 bot_config 中
- 应用前请审阅并确认符合预期
- 插件不会自动修改任何配置

---
*生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""


def create_plugin() -> PersonaIterPlugin:
    return PersonaIterPlugin()
