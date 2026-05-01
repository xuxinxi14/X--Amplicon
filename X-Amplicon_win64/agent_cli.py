"""CLI entry point for the X-Amplicon AI Agent - rich-enhanced UI.

Usage:
    python agent_cli.py
    python agent_cli.py --resume
    python agent_cli.py --model gpt-4o
    python agent_cli.py --api-base https://your-proxy.com/v1
    python agent_cli.py --list-models
    python agent_cli.py --state path/to/state.json
    python agent_cli.py --reset
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
import threading
import time
import uuid
from typing import Any

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from src.core.cli_only_workflow import build_cli_only_workflow, format_cli_only_workflow

console = Console()

COLOR_INFO = "cyan"
COLOR_SUCCESS = "green"
COLOR_WARNING = "yellow"
COLOR_ERROR = "red"
COLOR_MUTED = "bright_black"
COLOR_USER = "green"
COLOR_AGENT = "cyan"
COLOR_TOOL = "yellow"

HISTORY_PREVIEW_CHARS = 320
HISTORY_PREVIEW_LINES = 8
MAX_VISIBLE_TIMELINE_ROWS = 6

LANGUAGE_ENGLISH = "English"
LANGUAGE_CHINESE = "Chinese"
LANGUAGE_PREFERENCE_KEY = "language"
_CURRENT_LANGUAGE = LANGUAGE_ENGLISH

_LANGUAGE_ALIASES = {
    "english": LANGUAGE_ENGLISH,
    "en": LANGUAGE_ENGLISH,
    "eng": LANGUAGE_ENGLISH,
    "英文": LANGUAGE_ENGLISH,
    "英语": LANGUAGE_ENGLISH,
    "chinese": LANGUAGE_CHINESE,
    "zh": LANGUAGE_CHINESE,
    "cn": LANGUAGE_CHINESE,
    "中文": LANGUAGE_CHINESE,
    "汉语": LANGUAGE_CHINESE,
    "中国话": LANGUAGE_CHINESE,
}

_UI_TEXT: dict[str, dict[str, str]] = {
    LANGUAGE_ENGLISH: {
        "activity": "Activity",
        "advice": "Advice",
        "agent": "Agent",
        "agent_cli_pkg": "Agent CLI",
        "all": "all",
        "api_base": "API Base",
        "api_key": "API Key",
        "artifacts": "Artifacts",
        "available_tools": "Available Analysis Tools",
        "beta_metrics": "Beta Metrics",
        "blocking_issues": "Blocking issues detected:",
        "bytes": "Bytes",
        "commands": "Commands",
        "completed": "completed",
        "completed_steps": "Completed Steps",
        "configuration": "Configuration",
        "configuration_error": "Configuration error",
        "confirmed": "Confirmed",
        "confirmed_params_remain_active": " Confirmed params remain active.",
        "content": "Content",
        "conversation_history": "Conversation History",
        "current_language": "Current language",
        "current_value": "current value",
        "current_step": "Current Step",
        "description": "Description",
        "diversity": "Diversity",
        "elapsed": "Elapsed",
        "empty_input_ignored": "Empty input ignored.",
        "endpoint": "Endpoint",
        "error": "Error",
        "feature_method": "Feature Method",
        "filter_route": "Filter Route",
        "fresh": "FRESH",
        "generated_beta": "Generated Beta",
        "goodbye": "Goodbye.",
        "help": "Help",
        "highlights": "Highlights",
        "history": "History",
        "history_count": "{messages} messages / {tools} tool runs",
        "key_outputs": "Key Outputs",
        "language": "Language",
        "language_cancelled": "Language unchanged.",
        "language_invalid": "Unknown language. Use Chinese or English.",
        "language_prompt": "Language [Chinese/English]: ",
        "language_switched": "Language switched to {language}.",
        "language_title": "Language",
        "limit": "Limit",
        "lines": "Lines",
        "messages": "Messages",
        "mode": "Mode",
        "model": "Model",
        "new_value": "New value",
        "next_steps": "Next Steps",
        "new_conversation_started": "Started a new conversation.",
        "no_history": "No conversation history yet.",
        "no_history_match": "No history entries matched the current filter.",
        "no_confirmed_session_defaults": "No confirmed session defaults.",
        "not_confirmed": "Not confirmed",
        "not_generated": "not generated yet",
        "note": "Note",
        "optional_clear_hint": " Use 'none' or 'null' to clear it.",
        "optional_skips": "Optional Skips",
        "output": "Output",
        "output_root": "Output Root",
        "outputs": "Outputs",
        "overview": "Overview",
        "param_digest": "Param Digest",
        "parameter": "Parameter",
        "params": "Params",
        "params_action_prompt": "Params [Enter=confirm, e=edit, r=reload, s=skip]: ",
        "params_blocking_issue": "Current params still have blocking issues. Edit them first or skip applying session defaults.",
        "params_edit_prompt": "Parameter number/name (blank to stop editing): ",
        "params_file": "Params File",
        "params_file_load_failed": "Failed to load pipeline params, skipping param dialog:",
        "params_file_not_found": "Pipeline params file not found, skipping param dialog:",
        "params_reload_failed": "Failed to reload params:",
        "params_reloaded": "Reloaded params from file.",
        "params_source": "Params Source",
        "params_unknown_option": "Unrecognized option. Use Enter, e, r, or s.",
        "phase": "Phase",
        "pipeline_param_update_cancelled": "Pipeline parameter update cancelled.",
        "pipeline_params": "Pipeline Parameters",
        "pipeline_params_confirmed": "Pipeline params confirmed for this session.",
        "pipeline_progress": "Pipeline Progress",
        "pipeline_steps": "Pipeline Steps",
        "preview": "Preview",
        "prompt_ideas": "Prompt Ideas",
        "provider_default": "provider default",
        "recent": "Recent",
        "recent_tool_runs": "Recent Tool Runs",
        "report": "Report",
        "report_overview": "Report Overview",
        "report_outline": "Report Outline",
        "report_preview": "Report Preview",
        "report_updated": "Report Updated",
        "required": "Required",
        "resumed": "RESUMED",
        "role": "Role",
        "run_overview": "Run Overview",
        "run_summary": "Run Summary",
        "sample_count": "Samples",
        "sections": "Sections",
        "seq_dir": "Seq Dir",
        "session": "Session",
        "session_coverage": "Session Coverage",
        "session_pipeline_params_unchanged": "Session pipeline params unchanged.",
        "session_pipeline_params_updated": "Session pipeline params updated.",
        "showing": "Showing",
        "skipped_beta": "Skipped Beta",
        "skipped_checks": "Skipped Checks",
        "skipped_optional": "Skipped Optional",
        "state": "State",
        "state_file": "State File",
        "state_reset": "State reset.",
        "startup_fresh_note": "Fresh session with no existing state file.",
        "startup_history_exists_note": "Saved history exists on disk but was not loaded.",
        "startup_history_exists_print": "Starting a fresh session. Use --resume to load saved history.",
        "startup_reset_note": "Saved state was cleared before startup.",
        "startup_resume_empty_note": "Resume requested, but no saved history was found.",
        "startup_resume_note": "Resumed saved state with {messages} messages and {tools} tool runs.",
        "startup_resume_print": "Resumed saved session:",
        "startup_param_confirmation_skipped": "Startup param confirmation skipped.",
        "startup_params_pending": "Pending confirmation",
        "startup_params_skipped": "Confirmation skipped",
        "state_updated": "State Updated",
        "status": "Status",
        "step": "Step",
        "summary": "Summary",
        "summary_updated": "Summary Updated",
        "time": "Time",
        "tool": "Tool",
        "tool_calls": "Tool Calls",
        "tool_timeline": "Tool Timeline",
        "tool_name": "Tool Name",
        "tool_runs": "Tool Runs",
        "total": "Total",
        "tree_output": "Tree Output",
        "unknown": "unknown",
        "unknown_parameter": "Unknown parameter. Use the row number or exact name.",
        "updated": "Updated",
        "validation": "Validation",
        "validation_summary": "Validation Summary",
        "value": "Value",
        "value_state": "Value State",
        "value_state_hint": "Value State shows whether a value is set/edited/unset. Validation shows whether that value has actually passed checks.",
        "what_it_does": "What It Does",
        "you": "You",
    },
    LANGUAGE_CHINESE: {
        "activity": "活动",
        "advice": "建议",
        "agent": "助手",
        "agent_cli_pkg": "Agent CLI",
        "all": "全部",
        "api_base": "API Base",
        "api_key": "API Key",
        "artifacts": "产物",
        "available_tools": "可用分析工具",
        "beta_metrics": "Beta 指标",
        "blocking_issues": "发现阻塞问题：",
        "bytes": "字节",
        "commands": "命令",
        "completed": "已完成",
        "completed_steps": "已完成步骤",
        "configuration": "配置",
        "configuration_error": "配置错误",
        "confirmed": "已确认",
        "confirmed_params_remain_active": " 已确认参数仍然有效。",
        "content": "内容",
        "conversation_history": "对话历史",
        "current_language": "当前语言",
        "current_value": "当前值",
        "current_step": "当前步骤",
        "description": "说明",
        "diversity": "多样性",
        "elapsed": "耗时",
        "empty_input_ignored": "空输入已忽略。",
        "endpoint": "端点",
        "error": "错误",
        "feature_method": "Feature Method",
        "filter_route": "Filter Route",
        "fresh": "新会话",
        "generated_beta": "已生成 Beta",
        "goodbye": "已退出。",
        "help": "帮助",
        "highlights": "摘要",
        "history": "历史",
        "history_count": "{messages} 条消息 / {tools} 次工具运行",
        "key_outputs": "关键输出",
        "language": "语言",
        "language_cancelled": "语言设置未改变。",
        "language_invalid": "无法识别语言。请输入 Chinese 或 English。",
        "language_prompt": "语言 [Chinese/English]：",
        "language_switched": "界面语言已切换为 {language}。",
        "language_title": "语言设置",
        "limit": "限制",
        "lines": "行数",
        "messages": "消息",
        "mode": "模式",
        "model": "模型",
        "new_value": "新值",
        "next_steps": "下一步",
        "new_conversation_started": "已开始新对话。",
        "no_history": "暂无对话历史。",
        "no_history_match": "没有匹配当前筛选条件的历史记录。",
        "no_confirmed_session_defaults": "没有已确认的会话默认参数。",
        "not_confirmed": "未确认",
        "not_generated": "尚未生成",
        "note": "备注",
        "optional_clear_hint": " 输入 'none' 或 'null' 可清空。",
        "optional_skips": "可选跳过项",
        "output": "输出",
        "output_root": "输出根目录",
        "outputs": "输出",
        "overview": "概览",
        "param_digest": "参数摘要",
        "parameter": "参数",
        "params": "参数",
        "params_action_prompt": "参数 [Enter=确认, e=编辑, r=重载, s=跳过]：",
        "params_blocking_issue": "当前参数仍有阻塞问题。请先编辑，或跳过本次会话默认参数设置。",
        "params_edit_prompt": "参数行号/名称（留空结束编辑）：",
        "params_file": "参数文件",
        "params_file_load_failed": "加载 pipeline 参数失败，跳过参数对话：",
        "params_file_not_found": "未找到 pipeline 参数文件，跳过参数对话：",
        "params_reload_failed": "重载参数失败：",
        "params_reloaded": "已从文件重载参数。",
        "params_source": "参数来源",
        "params_unknown_option": "无法识别该选项。请使用 Enter、e、r 或 s。",
        "phase": "阶段",
        "pipeline_param_update_cancelled": "pipeline 参数更新已取消。",
        "pipeline_params": "Pipeline 参数",
        "pipeline_params_confirmed": "本会话 pipeline 参数已确认。",
        "pipeline_progress": "流程进度",
        "pipeline_steps": "流程步骤",
        "preview": "预览",
        "prompt_ideas": "提示示例",
        "provider_default": "provider default",
        "recent": "最近完成",
        "recent_tool_runs": "最近工具运行",
        "report": "报告",
        "report_overview": "报告概览",
        "report_outline": "报告大纲",
        "report_preview": "报告预览",
        "report_updated": "报告更新时间",
        "required": "必填",
        "resumed": "已恢复",
        "role": "角色",
        "run_overview": "运行概览",
        "run_summary": "运行摘要",
        "sample_count": "样本数",
        "sections": "章节",
        "seq_dir": "序列目录",
        "session": "会话",
        "session_coverage": "会话覆盖",
        "session_pipeline_params_unchanged": "会话 pipeline 参数未改变。",
        "session_pipeline_params_updated": "会话 pipeline 参数已更新。",
        "showing": "显示",
        "skipped_beta": "跳过的 Beta",
        "skipped_checks": "跳过检查",
        "skipped_optional": "跳过的可选步骤",
        "state": "状态",
        "state_file": "状态文件",
        "state_reset": "状态已重置。",
        "startup_fresh_note": "新会话，当前没有已有状态文件。",
        "startup_history_exists_note": "磁盘上存在历史记录，但本次未加载。",
        "startup_history_exists_print": "正在启动新会话。可使用 --resume 加载已保存历史。",
        "startup_reset_note": "启动前已清空保存的状态。",
        "startup_resume_empty_note": "已请求恢复会话，但没有找到已保存历史。",
        "startup_resume_note": "已恢复保存状态：{messages} 条消息，{tools} 次工具运行。",
        "startup_resume_print": "已恢复保存会话：",
        "startup_param_confirmation_skipped": "已跳过启动参数确认。",
        "startup_params_pending": "等待确认",
        "startup_params_skipped": "已跳过确认",
        "state_updated": "状态更新时间",
        "status": "状态",
        "step": "步骤",
        "summary": "摘要",
        "summary_updated": "摘要更新时间",
        "time": "时间",
        "tool": "工具",
        "tool_calls": "工具调用",
        "tool_timeline": "工具时间线",
        "tool_name": "工具名称",
        "tool_runs": "工具运行",
        "total": "总数",
        "tree_output": "Tree Output",
        "unknown": "未知",
        "unknown_parameter": "未知参数。请使用行号或完整参数名。",
        "updated": "已更新",
        "validation": "验证",
        "validation_summary": "验证摘要",
        "value": "值",
        "value_state": "值状态",
        "value_state_hint": "值状态表示该值是否已设置/已编辑/未设置；验证表示该值是否真的通过检查。",
        "what_it_does": "说明",
        "you": "你",
    },
}

_STATUS_TEXT = {
    LANGUAGE_CHINESE: {
        "confirmed": "已确认",
        "not confirmed": "未确认",
        "ok": "成功",
        "passed": "通过",
        "success": "成功",
        "completed": "已完成",
        "ready": "就绪",
        "set": "已设置",
        "validated": "已验证",
        "configured": "已配置",
        "active": "启用",
        "warning": "警告",
        "skipped": "已跳过",
        "pending": "待处理",
        "running": "运行中",
        "edited": "已编辑",
        "unset": "未设置",
        "optional": "可选",
        "required": "必填",
        "error": "错误",
        "failed": "失败",
        "issue": "问题",
        "invalid": "无效",
        "missing": "缺失",
        "fresh": "新会话",
        "reset": "已重置",
        "resumed": "已恢复",
        "confirmation skipped": "已跳过确认",
        "pending confirmation": "等待确认",
    }
}

_COMMAND_DESCRIPTIONS = {
    LANGUAGE_ENGLISH: [
        ("/status", "show session status, artifacts, and recent tool runs"),
        ("/tools", "list all analysis tools"),
        ("/params", "review or update pipeline params"),
        ("/language", "switch CLI language between Chinese and English"),
        ("/help", "show command help and example prompts"),
        ("/clear", "clear the terminal and redraw the dashboard"),
        ("/config", "show API configuration"),
        ("/history", "show history, e.g. /history tool 8"),
        ("/report", "write or preview report, e.g. /report preview"),
        ("/new", "start a new conversation"),
        ("/reset", "clear history and start fresh"),
        ("/quit", "exit"),
    ],
    LANGUAGE_CHINESE: [
        ("/status", "查看会话状态、产物和最近工具运行"),
        ("/tools", "列出所有分析工具"),
        ("/params", "查看或更新 pipeline 参数"),
        ("/language", "在中文和英文界面之间切换"),
        ("/help", "显示命令帮助和提示示例"),
        ("/clear", "清空终端并重绘面板"),
        ("/config", "显示 API 配置"),
        ("/history", "查看历史，例如 /history tool 8"),
        ("/report", "写入或预览 Markdown 报告"),
        ("/new", "开始新对话"),
        ("/reset", "清空历史并重新开始"),
        ("/quit", "退出"),
    ],
}


def _normalize_language(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in {LANGUAGE_ENGLISH, LANGUAGE_CHINESE}:
        return text
    return _LANGUAGE_ALIASES.get(text.lower())


def _set_ui_language(language: Any) -> str:
    global _CURRENT_LANGUAGE
    normalized = _normalize_language(language) or LANGUAGE_ENGLISH
    _CURRENT_LANGUAGE = normalized
    return normalized


def _get_ui_language() -> str:
    return _CURRENT_LANGUAGE


def _tr(key: str, **kwargs: Any) -> str:
    text = _UI_TEXT.get(_CURRENT_LANGUAGE, _UI_TEXT[LANGUAGE_ENGLISH]).get(
        key,
        _UI_TEXT[LANGUAGE_ENGLISH].get(key, key),
    )
    return text.format(**kwargs) if kwargs else text


def _is_chinese_ui() -> bool:
    return _CURRENT_LANGUAGE == LANGUAGE_CHINESE


def _display_status(value: Any) -> str:
    text = str(value)
    if not _is_chinese_ui():
        return text
    return _STATUS_TEXT[LANGUAGE_CHINESE].get(text.strip().lower(), text)


def _display_language_name(language: str | None = None) -> str:
    current = language or _CURRENT_LANGUAGE
    if _is_chinese_ui():
        return "中文" if current == LANGUAGE_CHINESE else "English"
    return current


# ---------------------------------------------------------------------------
# ASCII art banner
# ---------------------------------------------------------------------------

# Two independently-aligned figlet blocks stacked vertically.
# "X-" uses figlet "big" font; "Amplicon" uses figlet "standard" font.
# Each block is self-contained so neither can skew the other.
_ASCII_LINE1 = r"""
 __  __
 \ \/ /
  \  /
  /  \
 /_/\_\
"""

_ASCII_LINE2 = r"""
    _                    _ _
   / \   _ __ ___  _ __ | (_) ___ ___  _ __
  / _ \ | '_ ` _ \| '_ \| | |/ __/ _ \| '_ \
 / ___ \| | | | | | |_) | | | (_| (_) | | | |
/_/   \_\_| |_| |_| .__/|_|_|\___\___/|_| |_|
                  |_|
"""

def _compact_text(value: Any, *, max_chars: int = HISTORY_PREVIEW_CHARS) -> str:
    text = str(value).strip()
    if not text:
        return "(empty)"

    lines = text.splitlines()
    preview = "\n".join(lines[:HISTORY_PREVIEW_LINES]).strip()
    if len(lines) > HISTORY_PREVIEW_LINES:
        preview += "\n..."
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3].rstrip() + "..."
    return preview


def _style_for_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {
        "ok",
        "passed",
        "success",
        "completed",
        "confirmed",
        "ready",
        "set",
        "validated",
        "configured",
        "active",
    }:
        return COLOR_SUCCESS
    if normalized in {"warning", "skipped", "pending", "running", "edited", "unset"}:
        return COLOR_WARNING
    if normalized in {"error", "failed", "issue", "invalid", "missing"}:
        return COLOR_ERROR
    return COLOR_INFO


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.0f}s"


def _format_timestamp(timestamp: float | int | None) -> str:
    if timestamp is None:
        return "--"
    try:
        return datetime.datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "--"


def _extract_existing_file_paths(value: Any, *, limit: int = 8) -> list[str]:
    paths: list[str] = []

    def _walk(obj: Any) -> None:
        if len(paths) >= limit:
            return
        if isinstance(obj, str):
            if os.path.isfile(obj):
                paths.append(os.path.abspath(obj))
            return
        if isinstance(obj, dict):
            for item in obj.values():
                _walk(item)
                if len(paths) >= limit:
                    return
            return
        if isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
                if len(paths) >= limit:
                    return

    _walk(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def _load_json_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_config_summary(config_summary: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for chunk in config_summary.split("  "):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()
    return parts


def _current_params_status(agent: Any) -> str:
    return "Confirmed" if getattr(agent, "session_pipeline_params", None) else "Not confirmed"


def _state_startup_note(state: Any) -> str:
    if state is None:
        return ""

    note_key = getattr(state, "startup_note_key", None)
    if isinstance(note_key, str) and note_key:
        note_args = getattr(state, "startup_note_args", {})
        if not isinstance(note_args, dict):
            note_args = {}
        return _tr(note_key, **note_args)

    return str(getattr(state, "startup_note", ""))


def _build_session_snapshot(
    agent: Any,
    *,
    params_status: str,
) -> dict[str, Any]:
    params = getattr(agent, "session_pipeline_params", None) or {}
    state = getattr(agent, "state", None)
    messages = [] if state is None or not hasattr(state, "get_messages") else state.get_messages()
    tool_results = [] if state is None or not hasattr(state, "get_tool_results") else state.get_tool_results()
    return {
        "mode": getattr(state, "startup_mode", "fresh"),
        "note": _state_startup_note(state),
        "params_status": params_status,
        "params_path": getattr(agent, "session_pipeline_params_path", None),
        "message_count": len(messages),
        "tool_count": len(tool_results),
        "output_root": params.get("output_root"),
        "seq_dir": params.get("seq_dir"),
        "state_path": getattr(state, "state_path", "(unknown)"),
        "language": _get_ui_language(),
    }


def _render_command_hints_panel() -> Panel:
    hints = Table.grid(padding=(0, 2))
    hints.add_column(style=f"bold {COLOR_INFO}", min_width=10)
    hints.add_column(style=COLOR_MUTED)
    for cmd, desc in _COMMAND_DESCRIPTIONS[_get_ui_language()]:
        hints.add_row(cmd, desc)

    return Panel(
        hints,
        title=f"[dim]{_tr('commands')}[/dim]",
        border_style=COLOR_MUTED,
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _render_example_prompts_panel(snapshot: dict[str, Any]) -> Panel:
    params_confirmed = str(snapshot.get("params_status", "")).lower().startswith("confirmed")
    seq_dir = snapshot.get("seq_dir")

    prompts: list[str] = []
    if params_confirmed:
        if _is_chinese_ui():
            prompts.append("使用已确认的 pipeline 默认参数快速分析我的数据。")
            prompts.append("立即运行完整 raw FASTQ 流程，并总结关键结果。")
            prompts.append("解读上一次运行的 alpha、beta 和 taxonomy 输出。")
        else:
            prompts.append("Quickly analyze my data with the confirmed pipeline defaults.")
            prompts.append("Run the full raw FASTQ pipeline now and summarize the key results.")
            prompts.append("Interpret the alpha, beta, and taxonomy outputs from the last run.")
        if seq_dir:
            prompts[0] = (
                f"使用已确认的默认参数快速分析 {seq_dir} 下的数据。"
                if _is_chinese_ui()
                else f"Quickly analyze the data under {seq_dir} with the confirmed defaults."
            )
    else:
        if _is_chinese_ui():
            prompts.append("分析前帮我检查或确认 pipeline 默认参数。")
            prompts.append("显示当前会话可用的分析工具。")
            prompts.append("说明运行 raw pipeline 前还缺哪些输入。")
        else:
            prompts.append("Help me review or confirm the pipeline defaults before analysis.")
            prompts.append("Show me the available analysis tools for this session.")
            prompts.append("Explain what inputs I still need before running the raw pipeline.")

    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"bold {COLOR_INFO}", width=3)
    table.add_column(style="white", overflow="fold")
    for index, prompt in enumerate(prompts, start=1):
        table.add_row(str(index), prompt)

    return Panel(
        table,
        title=f"[bold cyan]{_tr('prompt_ideas')}[/bold cyan]",
        border_style=COLOR_MUTED,
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _render_session_status_panel(snapshot: dict[str, Any]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    table.add_column(style="dim", min_width=14)
    table.add_column(style=COLOR_INFO, overflow="fold")

    mode_style = COLOR_SUCCESS if snapshot["mode"] in {"fresh", "reset"} else COLOR_INFO
    params_style = _style_for_status(snapshot["params_status"])
    table.add_row(_tr("session"), f"[{mode_style}]{_display_status(snapshot['mode']).upper()}[/{mode_style}]")
    table.add_row(_tr("params"), f"[{params_style}]{_display_status(snapshot['params_status'])}[/{params_style}]")
    table.add_row(
        _tr("history"),
        _tr("history_count", messages=snapshot["message_count"], tools=snapshot["tool_count"]),
    )
    table.add_row(_tr("language"), _display_language_name(str(snapshot.get("language") or _get_ui_language())))
    if snapshot.get("seq_dir"):
        table.add_row(_tr("seq_dir"), str(snapshot["seq_dir"]))
    if snapshot.get("output_root"):
        table.add_row(_tr("output"), str(snapshot["output_root"]))
    if snapshot.get("params_path"):
        table.add_row(_tr("params_file"), os.path.abspath(str(snapshot["params_path"])))
    table.add_row(_tr("state_file"), os.path.abspath(str(snapshot["state_path"])))
    if snapshot.get("note"):
        table.add_row(_tr("note"), _compact_text(snapshot["note"], max_chars=120))

    return Panel(
        table,
        title=f"[bold cyan]{_tr('session')}[/bold cyan]",
        border_style=COLOR_INFO,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _print_dashboard_panels(snapshot: dict[str, Any]) -> None:
    console.print(
        Columns(
            [
                _render_session_status_panel(snapshot),
                _render_command_hints_panel(),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print(_render_example_prompts_panel(snapshot))
    console.print()


def _print_banner(config_summary: str, snapshot: dict[str, Any]) -> None:
    # "X-" block left-aligned, "Amplicon" block indented to sit beside it
    part1 = Text(_ASCII_LINE1.rstrip("\n"), style="bold bright_blue", no_wrap=False)
    part2 = Text(_ASCII_LINE2.rstrip("\n"), style="bold bright_blue", no_wrap=False)

    summary_parts = _parse_config_summary(config_summary)
    subtitle_text = "扩增子分析助手" if _is_chinese_ui() else "Amplicon Analysis Assistant"
    subtitle = Align.center(Text(subtitle_text, style="cyan"))
    divider  = Text("  " + "-" * 60, style="bright_black")

    status_line = Text.assemble(
        Text(f"  {_tr('model')}  : ", style="dim"),
        Text(summary_parts.get("model", "(unknown)"), style="bold cyan"),
        Text("   |   ", style="bright_black"),
        Text(f"{_tr('endpoint')} : ", style="dim"),
        Text(summary_parts.get("base", _tr("provider_default")), style="cyan"),
    )

    banner_group = Group(
        part1,
        part2,
        Text(""),
        subtitle,
        Text(""),
        divider,
        status_line,
        Text(""),
    )

    console.print(
        Panel(
            banner_group,
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(0, 2),
            expand=False,
        )
    )
    _print_dashboard_panels(snapshot)


# ---------------------------------------------------------------------------
# Rich /tools display
# ---------------------------------------------------------------------------

def _print_tools() -> None:
    from agent.tools import get_tool_schemas
    schemas = get_tool_schemas()

    table = Table(
        title=f"{_tr('available_tools')}  ({len(schemas)})",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold cyan",
        show_lines=True,
        expand=False,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column(_tr("tool_name"), style="bold white", min_width=30)
    table.add_column(_tr("description"), style="white", min_width=55)

    for i, schema in enumerate(schemas, 1):
        fn = schema["function"]
        name = fn["name"]
        desc = fn["description"]
        # First sentence only for the table
        short_desc = desc.split(".")[0].strip() + "."
        table.add_row(str(i), name, short_desc)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Rich /config display
# ---------------------------------------------------------------------------

def _print_config(agent: Any) -> None:
    cfg = agent.config
    key_hint = f"{cfg.api_key[:8]}..." if cfg.api_key else f"[red]({_tr('not_confirmed')})[/red]"
    base_hint = cfg.api_base or f"[dim]({_tr('provider_default')})[/dim]"

    table = Table(box=box.SIMPLE, border_style="bright_blue", show_header=False, padding=(0, 2))
    table.add_column(style="dim", min_width=12)
    table.add_column(style="cyan")
    table.add_row(_tr("model"), cfg.model)
    table.add_row(_tr("api_key"), key_hint)
    table.add_row(_tr("api_base"), base_hint)
    table.add_row(_tr("state"), agent.state.state_path)

    snapshot = _build_session_snapshot(
        agent,
        params_status=_current_params_status(agent),
    )
    console.print(
        Columns(
            [
                Panel(table, title=f"[bold cyan]{_tr('configuration')}[/bold cyan]", border_style=COLOR_INFO),
                _render_session_status_panel(snapshot),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Rich /history display
# ---------------------------------------------------------------------------

def _print_history(agent: Any) -> None:
    messages = agent.state.get_messages()
    if not messages:
        console.print(f"[yellow]{_tr('no_history')}[/yellow]\n")
        return

    table = Table(
        title=f"{_tr('conversation_history')}  ({len(messages)} {_tr('messages')})",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold cyan",
        show_lines=True,
        expand=False,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column(_tr("role"), width=10)
    table.add_column(_tr("content"), min_width=60)

    role_styles = {"user": "bold green", "assistant": "bold cyan", "tool": "dim yellow"}
    for i, msg in enumerate(messages, 1):
        role = msg["role"]
        content = msg["content"]
        preview = content[:200] + "…" if len(content) > 200 else content
        style = role_styles.get(role, "white")
        table.add_row(str(i), Text(role.upper(), style=style), preview)

    console.print(table)
    console.print()


def _resolve_history_options(command: str) -> tuple[str | None, int | None]:
    tokens = command.strip().split()[1:]
    role_filter: str | None = None
    limit: int | None = None

    for token in tokens:
        lowered = token.lower()
        if lowered in {"user", "assistant", "tool", "all"}:
            role_filter = None if lowered == "all" else lowered
            continue
        if lowered.isdigit():
            limit = max(1, int(lowered))

    return role_filter, limit


def _print_history_view(
    agent: Any,
    *,
    role_filter: str | None = None,
    limit: int | None = None,
) -> None:
    messages = agent.state.get_messages()
    if not messages:
        console.print(f"[{COLOR_WARNING}]{_tr('no_history')}[/{COLOR_WARNING}]\n")
        return

    filtered_indices = [
        index
        for index, message in enumerate(messages, start=1)
        if role_filter is None or message["role"] == role_filter
    ]
    if limit is not None:
        filtered_indices = filtered_indices[-limit:]
    if not filtered_indices:
        console.print(
            f"[{COLOR_WARNING}]{_tr('no_history_match')}[/{COLOR_WARNING}]\n"
        )
        return

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary.add_column(style="dim", min_width=12)
    summary.add_column(style="white", overflow="fold")
    summary.add_row(_tr("showing"), str(len(filtered_indices)))
    summary.add_row(_tr("total"), str(len(messages)))
    summary.add_row(_tr("role"), role_filter or _tr("all"))
    summary.add_row(_tr("limit"), str(limit) if limit is not None else _tr("all"))
    console.print(
        Panel(
            summary,
            title=f"[bold cyan]{_tr('conversation_history')}[/bold cyan]",
            border_style=COLOR_INFO,
            padding=(0, 2),
        )
    )

    tool_records = iter(agent.state.get_tool_results())
    tool_summaries: list[tuple[int, str]] = []
    for index, message in enumerate(messages, start=1):
        if message["role"] == "tool":
            tool_record = next(tool_records, None)
            if tool_record is None:
                tool_summaries.append((index, _compact_text(message["content"])))
            else:
                tool_name = str(tool_record.get("tool", "tool"))
                result = tool_record.get("result", {})
                tool_summaries.append(
                    (
                        index,
                        _compact_text(
                            _summarize_tool_result_for_display(tool_name, result),
                            max_chars=240,
                        ),
                    )
                )

    tool_summary_by_index = dict(tool_summaries)
    for index, message in enumerate(messages, start=1):
        if index not in filtered_indices:
            continue
        role = message["role"]
        if role == "user":
            title = f"USER {index:02d}"
            border_style = COLOR_USER
            body = _compact_text(message["content"])
        elif role == "assistant":
            title = f"AGENT {index:02d}"
            border_style = COLOR_AGENT
            body = _compact_text(message["content"])
        else:
            border_style = COLOR_TOOL
            title = f"TOOL {index:02d}"
            body = tool_summary_by_index.get(index, _compact_text(message["content"]))

        console.print(
            Panel(
                body,
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )
    console.print()


# ---------------------------------------------------------------------------
# TSV / TXT result preview
# ---------------------------------------------------------------------------

def _try_preview_result(result: dict[str, Any]) -> None:
    """If the tool result contains a file path to a TSV/TXT, preview first 5 rows."""
    if result.get("status") != "ok":
        return

    payload = result.get("result")
    if not isinstance(payload, dict):
        return

    # Collect candidate file paths from the result dict values
    import os
    candidates: list[str] = []
    for v in payload.values():
        if isinstance(v, str) and v.endswith((".txt", ".tsv", ".csv")) and os.path.isfile(v):
            candidates.append(v)

    for path in candidates[:1]:  # preview the first matching file only
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                sample = list(csv.reader(fh, delimiter="\t"))

            if len(sample) < 2:
                continue

            headers = sample[0]
            rows = sample[1:6]  # first 5 data rows

            table = Table(
                title=f"[dim]{_tr('preview')}: {os.path.basename(path)}  ({'前' if _is_chinese_ui() else 'first'} {len(rows)} {'行' if _is_chinese_ui() else 'rows'})[/dim]",
                box=box.SIMPLE_HEAD,
                border_style="bright_black",
                header_style="bold dim",
                show_lines=False,
                expand=False,
            )
            for col in headers[:10]:  # cap at 10 columns
                table.add_column(col, style="white", max_width=20, overflow="fold")
            for row in rows:
                table.add_row(*row[:10])

            console.print(table)
            if len(headers) > 10:
                suffix = "more columns not shown" if not _is_chinese_ui() else "列未显示"
                console.print(f"[dim]  ... {len(headers) - 10} {suffix}[/dim]")
            console.print()
        except Exception:
            pass  # silently skip unreadable files


# ---------------------------------------------------------------------------
# /report - Markdown report generation
# ---------------------------------------------------------------------------

_REPORT_PATH = os.path.join("work", "06_final", "report", "analysis_report.md")

# Tool names that belong to each report section
_ALPHA_TOOLS  = {"calculate_alpha_diversity", "calculate_rarefaction_curve",
                 "calculate_richness_rarefaction_curve", "rarefy_otutab", "run_otutab_rare"}
_BETA_TOOLS   = {"calculate_beta_distance"}
_TAXON_TOOLS  = {"summarize_taxa_abundance", "parse_sintax_to_dataframe"}
_FILTER_TOOLS = {"calculate_group_abundance", "run_otutab_filter"}
_PIPELINE_TOOLS = {
    "run_raw_amplicon_pipeline", "run_otutab_generation",
    "run_vsearch_sintax", "run_vsearch_otu_clustering",
    "run_vsearch_uchime_ref", "run_usearch_unoise3_denoising",
    "run_usearch_otu_clustering",
}


def _df_to_markdown(obj: Any, max_rows: int = 10) -> str:
    """Convert a pandas DataFrame or dict to a Markdown table string.

    Args:
        obj: A pandas DataFrame, list of dicts, or plain dict.
        max_rows: Maximum data rows to include.

    Returns:
        Markdown table string, or a fenced code block for plain dicts.
    """
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            truncated = obj.head(max_rows)
            lines: list[str] = []
            headers = [str(truncated.index.name or "index")] + [str(c) for c in truncated.columns]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for idx, row in truncated.iterrows():
                cells = [str(idx)] + [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
                lines.append("| " + " | ".join(cells) + " |")
            if len(obj) > max_rows:
                lines.append(f"\n_… {len(obj) - max_rows} more rows not shown_")
            return "\n".join(lines)
    except ImportError:
        pass

    if isinstance(obj, dict):
        return "```json\n" + json.dumps(obj, indent=2, default=str) + "\n```"
    return f"```\n{obj}\n```"


def _collect_output_files(tool_results: list[dict]) -> list[str]:
    """Scan all tool results for file path values that exist on disk.

    Args:
        tool_results: List of tool result records from AgentState.

    Returns:
        Deduplicated list of absolute file paths.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for record in tool_results:
        result = record.get("result", {})
        if result.get("status") != "ok":
            continue
        payload = result.get("result")
        if not isinstance(payload, dict):
            continue
        for path in _extract_existing_file_paths(payload, limit=5000):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def _generate_report(agent: Any) -> str:
    """Build a complete Markdown analysis report from agent state.

    Walks all recorded tool results, groups them by analysis category,
    renders DataFrames as Markdown tables, and collects output file links.

    Args:
        agent: AmpliconAgent instance with populated state.

    Returns:
        Full Markdown report as a string.
    """
    tool_results = agent.state.get_tool_results()
    completed    = agent.state.get_completed_steps()
    messages     = agent.state.get_messages()
    now          = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Bucket results by category
    alpha_records:    list[dict] = []
    beta_records:     list[dict] = []
    taxon_records:    list[dict] = []
    filter_records:   list[dict] = []
    pipeline_records: list[dict] = []
    other_records:    list[dict] = []

    for rec in tool_results:
        name = rec.get("tool", "")
        if name in _ALPHA_TOOLS:
            alpha_records.append(rec)
        elif name in _BETA_TOOLS:
            beta_records.append(rec)
        elif name in _TAXON_TOOLS:
            taxon_records.append(rec)
        elif name in _FILTER_TOOLS:
            filter_records.append(rec)
        elif name in _PIPELINE_TOOLS:
            pipeline_records.append(rec)
        else:
            other_records.append(rec)

    output_files = _collect_output_files(tool_results)

    # ------------------------------------------------------------------ #
    lines: list[str] = []

    lines += [
        "# X-Amplicon Analysis Report",
        "",
        f"_Generated: {now}_",
        "",
        "---",
        "",
    ]

    # 1. Overview
    lines += ["## 1. Analysis Overview", ""]
    if completed:
        lines.append(f"**{len(completed)} analysis step(s) completed successfully.**")
        lines.append("")
        lines.append("| # | Step |")
        lines.append("| --- | --- |")
        for i, step in enumerate(completed, 1):
            lines.append(f"| {i} | `{step}` |")
    else:
        lines.append("_No analysis steps have been completed yet._")
    lines.append("")

    # Conversation summary
    user_turns = [m for m in messages if m["role"] == "user"]
    if user_turns:
        lines += ["### Conversation Summary", ""]
        for i, msg in enumerate(user_turns, 1):
            lines.append(f"{i}. {msg['content']}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 2. Alpha diversity
    lines += ["## 2. Alpha Diversity", ""]
    if alpha_records:
        for rec in alpha_records:
            tool  = rec["tool"]
            args  = rec.get("arguments", {})
            result = rec.get("result", {})
            lines.append(f"### `{tool}`")
            lines.append("")
            if result.get("status") == "ok":
                payload = result.get("result")
                lines.append(_df_to_markdown(payload))
                lines.append("")
                # Key observations for alpha diversity table
                try:
                    import pandas as pd
                    if isinstance(payload, pd.DataFrame) and "Shannon" in payload.columns:
                        shannon = payload["Shannon"]
                        lines.append("**Key observations:**")
                        lines.append("")
                        lines.append(f"- Highest Shannon diversity: **{shannon.idxmax()}** ({shannon.max():.3f})")
                        lines.append(f"- Lowest Shannon diversity: **{shannon.idxmin()}** ({shannon.min():.3f})")
                        lines.append(f"- Mean Shannon across samples: **{shannon.mean():.3f}**")
                        lines.append("")
                except Exception:
                    pass
            else:
                lines.append(f"> **Error:** {result.get('error', 'unknown')}")
                lines.append("")
    else:
        lines.append("_Alpha diversity analysis was not run in this session._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 3. Beta diversity
    lines += ["## 3. Beta Diversity", ""]
    if beta_records:
        for rec in beta_records:
            tool   = rec["tool"]
            args   = rec.get("arguments", {})
            result = rec.get("result", {})
            metric = args.get("metric", "unknown metric")
            lines.append(f"### `{tool}` - {metric}")
            lines.append("")
            if result.get("status") == "ok":
                payload = result.get("result")
                lines.append(_df_to_markdown(payload))
                lines.append("")
                try:
                    import pandas as pd
                    import numpy as np
                    if isinstance(payload, pd.DataFrame):
                        mat = payload.values
                        upper = mat[np.triu_indices_from(mat, k=1)]
                        if len(upper):
                            lines.append("**Key observations:**")
                            lines.append("")
                            lines.append(f"- Mean pairwise distance: **{upper.mean():.4f}**")
                            lines.append(f"- Min pairwise distance: **{upper.min():.4f}**")
                            lines.append(f"- Max pairwise distance: **{upper.max():.4f}**")
                            lines.append("")
                except Exception:
                    pass
            else:
                lines.append(f"> **Error:** {result.get('error', 'unknown')}")
                lines.append("")
    else:
        lines.append("_Beta diversity analysis was not run in this session._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 4. Taxonomy summary
    lines += ["## 4. Taxonomy Summary", ""]
    if taxon_records:
        # Group by rank argument for labelling
        for rec in taxon_records:
            tool   = rec["tool"]
            args   = rec.get("arguments", {})
            result = rec.get("result", {})
            rank   = args.get("rank", "")
            label  = f"{tool}" + (f" - {rank}" if rank else "")
            lines.append(f"### `{label}`")
            lines.append("")
            if result.get("status") == "ok":
                payload = result.get("result")
                lines.append(_df_to_markdown(payload, max_rows=15))
                lines.append("")
            else:
                lines.append(f"> **Error:** {result.get('error', 'unknown')}")
                lines.append("")
    else:
        lines.append("_Taxonomy summary was not run in this session._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 5. Output files
    lines += ["## 5. Output Files", ""]
    if output_files:
        lines.append("| File | Path |")
        lines.append("| --- | --- |")
        for path in output_files:
            name = os.path.basename(path)
            lines.append(f"| `{name}` | `{path}` |")
    else:
        lines.append("_No output files were recorded in this session._")
    lines.append("")

    # Append any pipeline / filter / other results as appendix
    appendix_records = pipeline_records + filter_records + other_records
    if appendix_records:
        lines += ["---", "", "## Appendix: Additional Tool Results", ""]
        for rec in appendix_records:
            tool   = rec["tool"]
            result = rec.get("result", {})
            lines.append(f"### `{tool}`")
            lines.append("")
            if result.get("status") == "ok":
                payload = result.get("result")
                if isinstance(payload, dict):
                    lines.append("```json")
                    lines.append(json.dumps(
                        {k: v for k, v in payload.items() if not isinstance(v, (list,)) or len(v) < 20},
                        indent=2, default=str,
                    ))
                    lines.append("```")
            else:
                lines.append(f"> **Error:** {result.get('error', 'unknown')}")
            lines.append("")

    return "\n".join(lines)


def _cmd_report(agent: Any, *, mode: str = "write") -> None:
    """Handle the /report slash command: generate and save the Markdown report.

    Args:
        agent: AmpliconAgent instance.
    """
    report_mode = mode.strip().lower()
    report_dir = _default_report_output_dir(agent)
    report_path = os.path.abspath(os.path.join(report_dir, "analysis_report.md"))

    if report_mode in {"preview", "show"} and os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as fh:
            report_md = fh.read()
    else:
        status_text = "正在生成报告..." if _is_chinese_ui() else "Generating report..."
        with console.status(f"[bold blue]{status_text}[/bold blue]", spinner="dots"):
            try:
                from src.core.report_generator import generate_analysis_report

                summary_path = _find_latest_pipeline_summary_path(agent)
                final_dir = (
                    os.path.dirname(summary_path)
                    if summary_path and os.path.isfile(summary_path)
                    else os.path.join("work", "06_final")
                )
                report_result = generate_analysis_report(
                    final_dir=final_dir,
                    summary_path=summary_path if summary_path and os.path.isfile(summary_path) else None,
                    output_dir=report_dir,
                    include_html=True,
                    include_figures=True,
                )
                report_path = os.path.abspath(str(report_result["markdown"]))
                with open(report_path, encoding="utf-8") as fh:
                    report_md = fh.read()
            except Exception:
                report_md = _generate_report(agent)
                os.makedirs(os.path.dirname(report_path), exist_ok=True)
                with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(report_md)

    lines = report_md.splitlines()
    headings = [line for line in lines if line.startswith("#")]

    overview = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    overview.add_column(style="dim", min_width=14)
    overview.add_column(style="white", overflow="fold")
    overview.add_row(_tr("mode"), report_mode)
    overview.add_row("Path", report_path)
    overview.add_row(_tr("lines"), str(len(lines)))
    overview.add_row(_tr("bytes"), f"{len(report_md):,}")
    overview.add_row(_tr("sections"), str(len(headings)))

    session = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    session.add_column(style="dim", min_width=14)
    session.add_column(style="white", overflow="fold")
    session.add_row(_tr("messages"), str(len(agent.state.get_messages())))
    session.add_row(_tr("tool_runs"), str(len(agent.state.get_tool_results())))
    session.add_row(_tr("completed"), str(len(agent.state.get_completed_steps())))
    session.add_row(_tr("params"), _tr("confirmed") if agent.session_pipeline_params else _tr("not_confirmed"))

    outline = Table(
        title=_tr("report_outline"),
        box=box.ROUNDED,
        border_style=COLOR_INFO,
        header_style="bold cyan",
        expand=False,
    )
    outline.add_column(_tr("sections"), style="bold white", min_width=50)
    for heading in headings:
        depth = len(heading) - len(heading.lstrip("#"))
        indent = "  " * (depth - 1)
        outline.add_row(indent + heading.lstrip("# ").strip())

    preview_lines = "\n".join(lines[: min(24, len(lines))])
    preview = Syntax(preview_lines or "# Empty report", "markdown", theme="ansi_dark", word_wrap=True)

    console.print(
        Columns(
            [
                Panel(overview, title=f"[bold cyan]{_tr('report_overview')}[/bold cyan]", border_style=COLOR_SUCCESS),
                Panel(session, title=f"[bold cyan]{_tr('session_coverage')}[/bold cyan]", border_style=COLOR_INFO),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print(outline)
    console.print(
        Panel(
            preview,
            title=f"[bold cyan]{_tr('report_preview')}[/bold cyan]",
            border_style=COLOR_MUTED,
            padding=(0, 1),
        )
    )
    console.print()


def _find_latest_pipeline_summary_path(agent: Any) -> str | None:
    tool_results = []
    state = getattr(agent, "state", None)
    if state is not None and hasattr(state, "get_tool_results"):
        tool_results = state.get_tool_results()

    for record in reversed(tool_results):
        if record.get("tool") != "run_raw_amplicon_pipeline":
            continue
        payload = record.get("result", {}).get("result", {})
        if not isinstance(payload, dict):
            continue
        summary_path = payload.get("summary_path")
        if isinstance(summary_path, str) and summary_path.strip():
            return os.path.abspath(summary_path)

    session_params = getattr(agent, "session_pipeline_params", None) or {}
    output_root = session_params.get("output_root")
    if isinstance(output_root, str) and output_root.strip():
        return os.path.abspath(os.path.join(output_root, "06_final", "run_summary.json"))
    return None


def _default_report_output_dir(agent: Any) -> str:
    summary_path = _find_latest_pipeline_summary_path(agent)
    if summary_path:
        return os.path.abspath(os.path.join(os.path.dirname(summary_path), "report"))

    session_params = getattr(agent, "session_pipeline_params", None) or {}
    output_root = session_params.get("output_root")
    if isinstance(output_root, str) and output_root.strip():
        return os.path.abspath(os.path.join(output_root, "06_final", "report"))

    return os.path.abspath(os.path.join("work", "06_final", "report"))


def _render_params_digest_panel(agent: Any) -> Panel:
    params = getattr(agent, "session_pipeline_params", None) or {}
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    table.add_column(style="dim", min_width=15)
    table.add_column(style="white", overflow="fold")

    if not params:
        table.add_row(_tr("status"), _tr("no_confirmed_session_defaults"))
        table.add_row("Action" if not _is_chinese_ui() else "操作", "Use /params to confirm or edit pipeline settings." if not _is_chinese_ui() else "使用 /params 确认或编辑 pipeline 设置。")
    else:
        table.add_row(_tr("params_source"), str(getattr(agent, "session_pipeline_params_path", "(unknown)")))
        table.add_row(_tr("feature_method"), str(params.get("feature_method", "(unset)")))
        table.add_row(_tr("filter_route"), str(params.get("filter_route", "(unset)")))
        table.add_row("Threads", str(params.get("threads", "(unset)")))
        table.add_row(_tr("seq_dir"), str(params.get("seq_dir", "(unset)")))
        table.add_row(_tr("output_root"), str(params.get("output_root", "(unset)")))
        output_root = str(params.get("output_root") or "work")
        table.add_row(_tr("tree_output"), os.path.join(output_root, "06_final", "otus.tree"))

    return Panel(
        table,
        title=f"[bold cyan]{_tr('param_digest')}[/bold cyan]",
        border_style=COLOR_INFO,
        padding=(0, 1),
    )


def _render_artifacts_panel(agent: Any) -> Panel:
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    table.add_column(style="dim", min_width=15)
    table.add_column(style="white", overflow="fold")

    state_path = getattr(getattr(agent, "state", None), "state_path", None)
    if state_path:
        table.add_row(_tr("state_file"), os.path.abspath(str(state_path)))
        if os.path.isfile(state_path):
            table.add_row(_tr("state_updated"), _format_timestamp(os.path.getmtime(state_path)))

    report_path = os.path.abspath(os.path.join(_default_report_output_dir(agent), "analysis_report.md"))
    table.add_row(_tr("report"), report_path if os.path.isfile(report_path) else _tr("not_generated"))
    if os.path.isfile(report_path):
        table.add_row(_tr("report_updated"), _format_timestamp(os.path.getmtime(report_path)))

    summary_path = _find_latest_pipeline_summary_path(agent)
    if summary_path and os.path.isfile(summary_path):
        table.add_row(_tr("run_summary"), summary_path)
        table.add_row(_tr("summary_updated"), _format_timestamp(os.path.getmtime(summary_path)))
    elif summary_path:
        table.add_row(_tr("run_summary"), f"expected at {summary_path}" if not _is_chinese_ui() else f"预计位于 {summary_path}")

    return Panel(
        table,
        title=f"[bold cyan]{_tr('artifacts')}[/bold cyan]",
        border_style=COLOR_INFO,
        padding=(0, 1),
    )


def _render_recent_tool_runs_panel(agent: Any, *, limit: int = 5) -> Panel | None:
    state = getattr(agent, "state", None)
    if state is None or not hasattr(state, "get_tool_results"):
        return None

    tool_results = state.get_tool_results()
    if not tool_results:
        return None

    table = Table(
        box=box.ROUNDED,
        border_style=COLOR_INFO,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column(_tr("time"), style="dim", min_width=19)
    table.add_column(_tr("tool"), style="bold white", min_width=24)
    table.add_column(_tr("status"), min_width=10)
    table.add_column(_tr("summary"), overflow="fold")

    for record in tool_results[-limit:]:
        result = record.get("result", {})
        status = str(result.get("status", "unknown"))
        table.add_row(
            _format_timestamp(record.get("timestamp")),
            str(record.get("tool", "tool")),
            f"[{_style_for_status(status)}]{_display_status(status).upper()}[/{_style_for_status(status)}]",
            _summarize_tool_result_for_display(str(record.get("tool", "tool")), result),
        )

    return Panel(
        table,
        title=f"[bold cyan]{_tr('recent_tool_runs')}[/bold cyan]",
        border_style=COLOR_INFO,
        padding=(0, 1),
    )


def _cmd_help(agent: Any) -> None:
    snapshot = _build_session_snapshot(agent, params_status=_current_params_status(agent))
    _print_dashboard_panels(snapshot)


def _cmd_status(agent: Any) -> None:
    snapshot = _build_session_snapshot(agent, params_status=_current_params_status(agent))
    console.print(
        Columns(
            [
                _render_session_status_panel(snapshot),
                _render_params_digest_panel(agent),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print(
        Columns(
            [
                _render_artifacts_panel(agent),
                _render_command_hints_panel(),
            ],
            equal=True,
            expand=True,
        )
    )
    recent_panel = _render_recent_tool_runs_panel(agent)
    if recent_panel is not None:
        console.print(recent_panel)
    console.print(_render_example_prompts_panel(snapshot))
    console.print()


# ---------------------------------------------------------------------------
# Pipeline params startup flow
# ---------------------------------------------------------------------------

def _get_pipeline_param_specs() -> tuple[tuple[str, ...], dict[str, dict[str, Any]]]:
    from process import (
        FEATURE_METHOD_ASV,
        FEATURE_METHOD_USEARCH_OTU,
        FEATURE_METHOD_VSEARCH_OTU,
        PIPELINE_PARAM_ORDER,
        ROUTE_16S,
        ROUTE_ITS,
        ROUTE_NONE,
        VALID_CHIMERA_MODES,
        VALID_OTUTAB_METHODS,
    )

    specs: dict[str, dict[str, Any]] = {
        "metadata_path": {"kind": "string"},
        "seq_dir": {"kind": "string"},
        "output_root": {"kind": "string"},
        "read1_suffix": {"kind": "string"},
        "read2_suffix": {"kind": "string"},
        "fastq_stripleft": {"kind": "int"},
        "fastq_stripright": {"kind": "int"},
        "fastq_maxee_rate": {"kind": "float"},
        "feature_method": {
            "kind": "enum",
            "choices": (
                FEATURE_METHOD_ASV,
                FEATURE_METHOD_USEARCH_OTU,
                FEATURE_METHOD_VSEARCH_OTU,
            ),
        },
        "feature_minsize": {"kind": "int"},
        "feature_identity": {"kind": "float"},
        "chimera_mode": {"kind": "enum", "choices": VALID_CHIMERA_MODES},
        "reference_db": {"kind": "string"},
        "otutab_method": {"kind": "enum", "choices": VALID_OTUTAB_METHODS},
        "otutab_identity": {"kind": "float"},
        "annotation_database": {
            "kind": "enum",
            "choices": ("rdp_16s_v18", "silva_16s_v123"),
        },
        "sintax_cutoff": {"kind": "float"},
        "filter_route": {
            "kind": "enum",
            "choices": (ROUTE_16S, ROUTE_ITS, ROUTE_NONE),
        },
        "rarefaction_depth": {"kind": "int"},
        "rarefaction_seed": {"kind": "int"},
        "threads": {"kind": "int"},
        "usearch_path": {"kind": "string", "optional": True},
        "vsearch_path": {"kind": "string", "optional": True},
        "command_timeout": {"kind": "float", "optional": True},
    }
    return PIPELINE_PARAM_ORDER, specs


def _format_pipeline_param_value(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def _describe_optional_pipeline_param(param_name: str, value: Any) -> str:
    if value is not None:
        return ""
    if param_name in {"usearch_path", "vsearch_path"}:
        return "Executable will be resolved from PATH/default locations."
    if param_name == "command_timeout":
        return "External commands will use the tool default timeout."
    return "Optional parameter is unset."


def _merge_pipeline_param_notes(*notes: str) -> str:
    parts = [note.strip() for note in notes if note and note.strip()]
    return " ".join(parts)


def _get_pipeline_param_check_names(param_name: str) -> tuple[str, ...]:
    return {
        "metadata_path": ("metadata",),
        "seq_dir": ("sequence_directory", "sample_fastq_pairs"),
        "read1_suffix": ("sample_fastq_pairs",),
        "read2_suffix": ("sample_fastq_pairs",),
        "fastq_stripleft": ("pipeline_parameters",),
        "fastq_stripright": ("pipeline_parameters",),
        "fastq_maxee_rate": ("pipeline_parameters",),
        "feature_method": ("pipeline_parameters",),
        "feature_minsize": ("pipeline_parameters",),
        "feature_identity": ("pipeline_parameters",),
        "chimera_mode": ("pipeline_parameters",),
        "reference_db": ("reference_database",),
        "otutab_method": ("pipeline_parameters",),
        "otutab_identity": ("pipeline_parameters",),
        "annotation_database": ("annotation_database",),
        "sintax_cutoff": ("pipeline_parameters",),
        "filter_route": ("pipeline_parameters",),
        "rarefaction_depth": ("pipeline_parameters",),
        "rarefaction_seed": ("pipeline_parameters",),
        "threads": ("pipeline_parameters",),
        "usearch_path": ("usearch_executable",),
        "vsearch_path": ("vsearch_executable",),
    }.get(param_name, ())


def _summarize_pipeline_param_validation(
    param_name: str,
    value: Any,
    report: dict[str, Any] | None,
) -> tuple[str, str]:
    if report is None:
        if value is None:
            return "Skipped", _describe_optional_pipeline_param(param_name, value)
        return "Pending", "Run validation to verify this setting."

    checks = [
        check
        for check in report.get("checks", [])
        if isinstance(check, dict)
        and check.get("name") in _get_pipeline_param_check_names(param_name)
    ]
    if not checks:
        if value is None:
            return "Skipped", _describe_optional_pipeline_param(param_name, value)
        return "Pending", "No dedicated validation check for this field."

    failed_check = next((check for check in checks if check.get("status") == "failed"), None)
    if failed_check is not None:
        return "Issue", str(failed_check.get("message", "Validation failed."))

    passed_checks = [check for check in checks if check.get("status") == "passed"]
    skipped_checks = [check for check in checks if check.get("status") == "skipped"]
    if passed_checks and not skipped_checks:
        return "Validated", ""
    if skipped_checks and not passed_checks:
        return "Skipped", str(skipped_checks[0].get("message", "Validation skipped."))
    if passed_checks and skipped_checks:
        return "Validated", str(skipped_checks[0].get("message", "Some optional checks were skipped."))

    return "Pending", "Validation has not completed for this field."


def _build_pipeline_param_rows(
    params: dict[str, Any],
    *,
    baseline_params: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    order, specs = _get_pipeline_param_specs()
    rows: list[dict[str, str]] = []

    for index, key in enumerate(order, start=1):
        value = params.get(key)
        baseline_value = None if baseline_params is None else baseline_params.get(key)
        is_optional = bool(specs[key].get("optional"))
        changed = baseline_params is not None and value != baseline_value

        if changed:
            state = "Edited"
            note = f"YAML: {_format_pipeline_param_value(baseline_value)}"
        elif is_optional and value is None:
            state = "Unset"
            note = _describe_optional_pipeline_param(key, value)
        else:
            state = "Set"
            note = ""

        validation, validation_note = _summarize_pipeline_param_validation(
            key,
            value,
            validation_report,
        )

        rows.append(
            {
                "index": str(index),
                "name": key,
                "required": "Optional" if is_optional else "Required",
                "value": _format_pipeline_param_value(value),
                "state": state,
                "validation": validation,
                "note": _merge_pipeline_param_notes(note, validation_note),
            }
        )

    return rows


def _render_pipeline_params_table(
    params_path: str,
    params: dict[str, Any],
    *,
    baseline_params: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
) -> None:
    rows = _build_pipeline_param_rows(
        params,
        baseline_params=baseline_params,
        validation_report=validation_report,
    )
    table = Table(
        title=f"{_tr('pipeline_params')}  ({os.path.abspath(params_path)})",
        box=box.ROUNDED,
        border_style=COLOR_INFO,
        header_style="bold cyan",
        expand=False,
    )
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column(_tr("parameter"), style="bold white", min_width=22)
    table.add_column(_tr("required"), style="white", min_width=10)
    table.add_column(_tr("value"), style="white", min_width=24, overflow="fold")
    table.add_column(_tr("value_state"), style="white", min_width=12)
    table.add_column(_tr("validation"), style="white", min_width=12)
    table.add_column(_tr("note"), style="white", min_width=36, overflow="fold")

    for row in rows:
        state_style = _style_for_status(row["state"])
        validation_style = _style_for_status(row["validation"])
        table.add_row(
            row["index"],
            row["name"],
            _display_status(row["required"]),
            row["value"],
            f"[{state_style}]{_display_status(row['state'])}[/{state_style}]",
            f"[{validation_style}]{_display_status(row['validation'])}[/{validation_style}]",
            row["note"],
        )

    console.print(table)
    console.print(
        "[dim]"
        + _tr("value_state_hint")
        + "[/dim]"
    )


def _resolve_pipeline_param_key(selection: str, params: dict[str, Any]) -> str | None:
    order, _ = _get_pipeline_param_specs()
    token = selection.strip()
    if not token:
        return None
    editable_keys = set(order)
    if token in editable_keys:
        return token
    normalized = token.lower()
    for key in order:
        if key.lower() == normalized:
            return key
    if token.isdigit():
        index = int(token)
        if 1 <= index <= len(order):
            return order[index - 1]
    return None


def _parse_pipeline_param_value(param_name: str, raw_value: str) -> Any:
    _, specs = _get_pipeline_param_specs()
    spec = specs[param_name]
    text = raw_value.strip()

    if spec.get("optional") and text.lower() in {"none", "null"}:
        return None

    kind = spec["kind"]
    if kind == "int":
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"{param_name} must be an integer.") from exc
    if kind == "float":
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"{param_name} must be a number.") from exc
    if kind == "enum":
        normalized = text.lower()
        choices = tuple(str(choice) for choice in spec["choices"])
        for choice in choices:
            if normalized == choice.lower():
                return choice
        raise ValueError(f"{param_name} must be one of: {', '.join(choices)}.")
    if not text:
        raise ValueError(f"{param_name} cannot be empty.")
    return text


def _print_pipeline_validation_summary(report: dict[str, Any]) -> None:
    status = str(report["status"]).upper()
    style = COLOR_SUCCESS if report["status"] == "passed" else COLOR_WARNING
    passed_checks = [
        check for check in report["checks"]
        if isinstance(check, dict) and check.get("status") == "passed"
    ]
    skipped_checks = [
        check for check in report["checks"]
        if isinstance(check, dict) and check.get("status") == "skipped"
    ]
    summary_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary_table.add_column(style="dim", min_width=16)
    summary_table.add_column(style="white", overflow="fold")
    summary_table.add_row(_tr("validation"), f"[{style}]{_display_status(status)}[/{style}]")
    summary_table.add_row("Passed Checks" if not _is_chinese_ui() else "通过检查", str(len(passed_checks)))
    summary_table.add_row(_tr("skipped_checks"), str(len(skipped_checks)))
    planned_metrics = report.get("planned_outputs", {}).get("beta_metrics", [])
    if planned_metrics:
        summary_table.add_row(_tr("beta_metrics"), ", ".join(str(metric) for metric in planned_metrics))
    skipped_optional_steps = report.get("skipped_optional_steps", [])
    if skipped_optional_steps:
        summary_table.add_row(
            _tr("skipped_optional"),
            ", ".join(str(step) for step in skipped_optional_steps),
        )
    console.print(
        Panel(
            summary_table,
            title=f"[bold cyan]{_tr('validation_summary')}[/bold cyan]",
            border_style=style,
            padding=(0, 1),
        )
    )

    failed_checks = [
        check for check in report["checks"]
        if isinstance(check, dict) and check.get("status") == "failed"
    ]
    if failed_checks:
        console.print(f"[{COLOR_WARNING}]{_tr('blocking_issues')}[/{COLOR_WARNING}]")
        for check in failed_checks:
            console.print(
                f"[{COLOR_WARNING}]- {check['name']}: {check['message']}[/{COLOR_WARNING}]"
            )
        console.print(
            f"[{COLOR_WARNING}]"
            + (
                "These values are not active session defaults until validation passes and you confirm them."
                if not _is_chinese_ui()
                else "这些值在通过验证并确认前，不会成为当前会话默认参数。"
            )
            + f"[/{COLOR_WARNING}]"
        )
    console.print()


def _build_pipeline_session_context(params_path: str, params: dict[str, Any]) -> str:
    order, _ = _get_pipeline_param_specs()
    ordered_params = {key: params[key] for key in order if key in params}
    return (
        "Session pipeline defaults were confirmed from "
        f"{os.path.abspath(params_path)}. "
        "These defaults are active for the current session. "
        "When the user asks to quickly analyze data, start analysis, run the "
        "pipeline, or process the seq directory, call run_raw_amplicon_pipeline "
        "immediately with these defaults unless the user explicitly overrides a "
        "field or asks for a different workflow. "
        "Do not ask the user to repeat parameters that already appear here.\n"
        f"{json.dumps(ordered_params, ensure_ascii=False, default=str, indent=2)}"
    )


def _build_unconfirmed_pipeline_session_context(params_path: str) -> str:
    return (
        "A pipeline params file is available at "
        f"{os.path.abspath(params_path)}, but it has not been confirmed for this session. "
        "Do not assume those values are active defaults. Before calling "
        "run_raw_amplicon_pipeline, either use confirmed session defaults or rely on "
        "explicit user-provided required arguments. If the user wants to reuse the "
        "params file, direct them to /params and wait for confirmation."
    )


def _apply_session_pipeline_params(
    agent: Any,
    params_path: str,
    params: dict[str, Any],
) -> None:
    from agent.tools import set_session_pipeline_defaults

    resolved_params_path = os.path.abspath(params_path)
    resolved_params = dict(params)
    resolved_defaults = dict(resolved_params)
    resolved_defaults["params_source"] = resolved_params_path
    set_session_pipeline_defaults(resolved_defaults)
    agent.set_session_pipeline_params(
        params_path=resolved_params_path,
        params=resolved_params,
        context=_build_pipeline_session_context(resolved_params_path, resolved_params),
    )


def _set_unconfirmed_pipeline_context(agent: Any, params_path: str) -> None:
    resolved_params_path = os.path.abspath(params_path)
    agent.set_session_pipeline_params(
        params_path=resolved_params_path,
        params=None,
        context=_build_unconfirmed_pipeline_session_context(resolved_params_path),
    )


def _confirm_pipeline_params(
    params_path: str,
    *,
    current_params: dict[str, Any] | None = None,
    confirm_message: str = "Pipeline params confirmed for this session.",
    skip_message: str = "Pipeline parameter update cancelled.",
) -> tuple[dict[str, Any] | None, str | None]:
    from process import inspect_pipeline_params_dict, load_pipeline_params

    resolved_params_path = os.path.abspath(params_path)
    baseline_params: dict[str, Any] | None = None
    if current_params is None and not os.path.isfile(resolved_params_path):
        console.print(
            f"[yellow]{_tr('params_file_not_found')}[/yellow] "
            f"{resolved_params_path}\n"
        )
        return None, None

    if current_params is None:
        try:
            current_params = load_pipeline_params(resolved_params_path)
        except Exception as exc:
            console.print(
                f"[yellow]{_tr('params_file_load_failed')}[/yellow] "
                f"{exc}\n"
            )
            return None, None
    else:
        current_params = dict(current_params)
        if os.path.isfile(resolved_params_path):
            try:
                baseline_params = load_pipeline_params(resolved_params_path)
            except Exception:
                baseline_params = dict(current_params)

    if baseline_params is None:
        baseline_params = dict(current_params)

    while True:
        report = inspect_pipeline_params_dict(
            current_params,
            params_source=resolved_params_path,
        )
        _render_pipeline_params_table(
            resolved_params_path,
            current_params,
            baseline_params=baseline_params,
            validation_report=report,
        )
        _print_pipeline_validation_summary(report)

        action = console.input(
            f"[bold green]{_tr('params')}[/bold green] {_tr('params_action_prompt')}"
        ).strip().lower()

        if action in {"", "y", "yes", "c", "confirm"}:
            if report["status"] != "passed":
                console.print(
                    f"[yellow]{_tr('params_blocking_issue')}[/yellow]\n"
                )
                continue
            console.print(f"[green]{confirm_message}[/green]\n")
            return current_params, _build_pipeline_session_context(
                resolved_params_path,
                current_params,
            )

        if action in {"s", "skip"}:
            console.print(f"[yellow]{skip_message}[/yellow]\n")
            return None, None

        if action in {"r", "reload"}:
            try:
                current_params = load_pipeline_params(resolved_params_path)
            except Exception as exc:
                console.print(f"[red]{_tr('params_reload_failed')} {exc}[/red]\n")
                continue
            baseline_params = dict(current_params)
            console.print(f"[cyan]{_tr('params_reloaded')}[/cyan]\n")
            continue

        if action not in {"e", "edit"}:
            console.print(f"[yellow]{_tr('params_unknown_option')}[/yellow]\n")
            continue

        while True:
            selection = console.input(
                f"[bold green]Edit[/bold green] {_tr('params_edit_prompt')}"
            ).strip()
            if not selection:
                console.print()
                break

            key = _resolve_pipeline_param_key(selection, current_params)
            if key is None:
                console.print(f"[yellow]{_tr('unknown_parameter')}[/yellow]")
                continue

            _, specs = _get_pipeline_param_specs()
            optional_hint = _tr("optional_clear_hint") if specs[key].get("optional") else ""
            console.print(
                f"[cyan]{key}[/cyan] {_tr('current_value')}: {_format_pipeline_param_value(current_params.get(key))}"
            )
            new_value = console.input(f"[bold green]{_tr('new_value')}[/bold green]{optional_hint}: ").strip()
            if not new_value:
                console.print(f"[yellow]{_tr('empty_input_ignored')}[/yellow]")
                continue

            try:
                current_params[key] = _parse_pipeline_param_value(key, new_value)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                continue

            console.print(
                f"[green]{_tr('updated')}[/green] {key} = {_format_pipeline_param_value(current_params[key])}\n"
            )


def _cmd_params(agent: Any) -> None:
    params_path = getattr(agent, "session_pipeline_params_path", None)
    if not params_path:
        params_path = os.path.abspath("pipeline_params.yaml")
        _set_unconfirmed_pipeline_context(agent, params_path)

    confirmed_params, _ = _confirm_pipeline_params(
        params_path,
        current_params=getattr(agent, "session_pipeline_params", None),
        confirm_message=_tr("session_pipeline_params_updated"),
        skip_message=_tr("session_pipeline_params_unchanged"),
    )
    if confirmed_params is not None:
        _apply_session_pipeline_params(agent, params_path, confirmed_params)
        console.print(
            _render_session_status_panel(
                _build_session_snapshot(agent, params_status="Confirmed")
            )
        )
        console.print()


def _create_agent_state(args: argparse.Namespace) -> Any:
    from agent.state import AgentState

    state_kwargs: dict[str, Any] = {
        "autoload": bool(args.resume and not args.reset),
    }
    if args.state:
        state_kwargs["state_path"] = args.state

    state = AgentState(**state_kwargs)
    _set_ui_language(state.get_preference(LANGUAGE_PREFERENCE_KEY, LANGUAGE_ENGLISH))

    if args.reset:
        state.reset()
        state.startup_mode = "reset"
        state.startup_note_key = "startup_reset_note"
        state.startup_note_args = {}
        state.startup_note = _tr("startup_reset_note")
        console.print(f"[yellow]{_tr('state_reset')}[/yellow]")
    elif args.resume:
        state.startup_mode = "resumed"
        message_count = len(state.get_messages())
        tool_count = len(state.get_tool_results())
        if message_count or tool_count:
            state.startup_note_key = "startup_resume_note"
            state.startup_note_args = {"messages": message_count, "tools": tool_count}
            state.startup_note = _tr("startup_resume_note", messages=message_count, tools=tool_count)
            resume_counts = (
                f"{message_count} 条消息，{tool_count} 次工具结果。"
                if _is_chinese_ui()
                else f"{message_count} messages, {tool_count} tool results."
            )
            console.print(
                f"[cyan]{_tr('startup_resume_print')}[/cyan] "
                f"{resume_counts}\n"
            )
        else:
            state.startup_note_key = "startup_resume_empty_note"
            state.startup_note_args = {}
            state.startup_note = _tr("startup_resume_empty_note")
    elif os.path.isfile(state.state_path):
        state.startup_mode = "fresh"
        state.startup_note_key = "startup_history_exists_note"
        state.startup_note_args = {}
        state.startup_note = _tr("startup_history_exists_note")
        console.print(
            f"[dim]{_tr('startup_history_exists_print')}[/dim]\n"
        )
    else:
        state.startup_mode = "fresh"
        state.startup_note_key = "startup_fresh_note"
        state.startup_note_args = {}
        state.startup_note = _tr("startup_fresh_note")

    return state


def _load_saved_ui_language(args: argparse.Namespace) -> None:
    from agent.state import DEFAULT_STATE_PATH

    state_path = os.path.abspath(str(args.state or DEFAULT_STATE_PATH))
    payload = _load_json_file(state_path)
    if not isinstance(payload, dict):
        return

    preferences = payload.get("preferences", {})
    if not isinstance(preferences, dict):
        return

    _set_ui_language(preferences.get(LANGUAGE_PREFERENCE_KEY, LANGUAGE_ENGLISH))


def _summarize_tool_result_for_display(
    tool_name: str,
    result: dict[str, Any],
) -> str:
    status = str(result.get("status", "unknown")).lower()
    if status != "ok":
        error = str(result.get("error", "unknown error"))
        return (
            f"{tool_name} 失败：{' '.join(error.split())}"
            if _is_chinese_ui()
            else f"{tool_name} failed: {' '.join(error.split())}"
        )

    payload = result.get("result")
    file_paths = _extract_existing_file_paths(payload)
    if tool_name == "run_raw_amplicon_pipeline" and isinstance(payload, dict):
        summary_path = payload.get("summary_path")
        if isinstance(summary_path, str):
            summary_payload = _load_json_file(summary_path)
            if summary_payload is not None:
                sample_ids = summary_payload.get("sample_ids", [])
                effective_params = summary_payload.get("effective_params", {})
                analysis_outputs = summary_payload.get("outputs", {}).get("analysis_outputs", {})
                generated_metrics = analysis_outputs.get("generated_beta_metrics", [])
                skipped_metrics = analysis_outputs.get("skipped_beta_metrics", [])
                if _is_chinese_ui():
                    return (
                        f"Pipeline 已完成，样本数={len(sample_ids)}；"
                        f"feature_method={effective_params.get('feature_method', '(unknown)')}；"
                        f"generated_beta={len(generated_metrics)}；skipped_beta={len(skipped_metrics)}。"
                    )
                return (
                    f"Pipeline completed for {len(sample_ids)} sample(s); "
                    f"feature_method={effective_params.get('feature_method', '(unknown)')}; "
                    f"generated_beta={len(generated_metrics)}; skipped_beta={len(skipped_metrics)}."
                )

    if isinstance(payload, dict):
        summary_parts: list[str] = []
        if file_paths:
            summary_parts.append(
                f"已写入 {len(file_paths)} 个文件"
                if _is_chinese_ui()
                else f"{len(file_paths)} file(s) written"
            )
        keys = sorted(payload.keys())
        if keys:
            summary_parts.append("keys=" + ", ".join(keys[:5]))
        return (
            f"{tool_name} 成功：" + "；".join(summary_parts or ["结果可用"])
            if _is_chinese_ui()
            else f"{tool_name} succeeded: " + "; ".join(summary_parts or ["result available"])
        )

    return f"{tool_name} 成功。" if _is_chinese_ui() else f"{tool_name} succeeded."


def _extract_pipeline_progress(summary: dict[str, Any]) -> dict[str, Any]:
    steps = summary.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    completed_steps = [
        step for step in steps
        if isinstance(step, dict) and step.get("status") == "completed"
    ]
    failed_step = next(
        (
            step for step in steps
            if isinstance(step, dict) and step.get("status") == "failed"
        ),
        None,
    )
    active_step = next(
        (
            step for step in reversed(steps)
            if isinstance(step, dict) and step.get("status") == "in_progress"
        ),
        None,
    )
    recent_completed = [
        str(step.get("name", "step"))
        for step in completed_steps[-3:]
        if isinstance(step, dict)
    ]

    if failed_step is not None:
        if _is_chinese_ui():
            summary_text = (
                f"Pipeline 在 {failed_step.get('name', 'unknown_step')} 失败："
                f"{failed_step.get('error', summary.get('error', 'unknown error'))}"
            )
        else:
            summary_text = (
                f"Pipeline failed at {failed_step.get('name', 'unknown_step')}: "
                f"{failed_step.get('error', summary.get('error', 'unknown error'))}"
            )
    elif active_step is not None:
        summary_text = (
            f"已完成 {len(completed_steps)}/{len(steps)} 个步骤；"
            f"当前：{active_step.get('name', 'unknown_step')}"
            if _is_chinese_ui()
            else f"{len(completed_steps)}/{len(steps)} steps completed; "
            f"current: {active_step.get('name', 'unknown_step')}"
        )
    elif steps:
        summary_text = (
            f"已启动的 {len(completed_steps)} 个步骤全部完成。"
            if _is_chinese_ui()
            else f"All {len(completed_steps)} started steps are complete."
        )
    else:
        summary_text = "正在准备 pipeline 工作区..." if _is_chinese_ui() else "Preparing pipeline workspace..."

    return {
        "status": str(summary.get("status", "running")),
        "current_step": None if active_step is None else str(active_step.get("name", "")),
        "current_description": None if active_step is None else str(active_step.get("description", "")),
        "completed_steps": len(completed_steps),
        "started_steps": len(steps),
        "recent_completed": recent_completed,
        "summary": summary_text,
        "sample_count": len(summary.get("sample_ids", [])) if isinstance(summary.get("sample_ids"), list) else 0,
        "failed_step": None if failed_step is None else str(failed_step.get("name", "")),
        "output_root": str(summary.get("effective_params", {}).get("output_root", "")),
    }


def _monitor_pipeline_summary(
    summary_path: str,
    event: dict[str, Any],
    publish: Any,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        summary = _load_json_file(summary_path)
        if summary is not None:
            progress = _extract_pipeline_progress(summary)
            event["pipeline_progress"] = progress
            event["summary"] = progress["summary"]
            publish(
                f"{_tr('pipeline_progress')}: {progress['summary']}"
            )
        stop_event.wait(0.35)


def _build_timeline_advice(event: dict[str, Any]) -> str:
    if event["status"] == "error":
        summary = event["summary"].lower()
        if "usearch" in summary or "vsearch" in summary:
            return "在 /params 或 PATH 中检查可执行文件路径。" if _is_chinese_ui() else "Check executable paths in /params or your PATH."
        if "metadata_path" in summary:
            return "在 /params 中确认 metadata_path；它必须指向已有文件。" if _is_chinese_ui() else "Confirm metadata_path in /params; it must point to an existing file."
        if "seq_dir" in summary:
            return "在 /params 中确认 seq_dir；它必须指向 FASTQ 目录。" if _is_chinese_ui() else "Confirm seq_dir in /params; it must point to the FASTQ directory."
        if "beta_tree_path" in summary:
            return "移除外部树覆盖，或提供有效树文件；常规流程会自动生成 otus.tree。" if _is_chinese_ui() else "Remove the external tree override or provide a valid tree file; normal runs generate otus.tree automatically."
        if "reference_db" in summary:
            return "在 /params 中确认 reference_db；它必须指向已有 FASTA 文件。" if _is_chinese_ui() else "Confirm reference_db in /params; it must point to an existing FASTA file."
        return "查看上方错误摘要，然后调整 /params 或输入文件。" if _is_chinese_ui() else "Inspect the error summary above, then adjust /params or inputs."

    if event["name"] == "run_raw_amplicon_pipeline":
        return "使用 /report 导出 Markdown 报告。" if _is_chinese_ui() else "Use /report to export a Markdown report."
    return "继续提出下一步分析请求，或检查输出文件。" if _is_chinese_ui() else "Continue with the next analysis request or inspect outputs."


def _render_tool_activity_panel(activity: dict[str, Any]) -> Panel:
    timeline = activity.get("timeline", [])
    started_at = float(activity.get("started_at", time.time()))
    elapsed = time.time() - started_at

    header = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    header.add_column(style="dim", min_width=12)
    header.add_column(style="white", overflow="fold")
    header.add_row(_tr("phase"), str(activity.get("phase", "Thinking" if not _is_chinese_ui() else "思考中")))
    header.add_row(_tr("elapsed"), _format_duration(elapsed))
    header.add_row(_tr("tool_calls"), str(len(timeline)))

    renderables: list[Any] = [header]
    active_pipeline_progress = next(
        (
            event.get("pipeline_progress")
            for event in reversed(timeline)
            if event.get("status") == "running" and event.get("pipeline_progress")
        ),
        None,
    )
    if isinstance(active_pipeline_progress, dict):
        progress_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
        progress_table.add_column(style="dim", min_width=14)
        progress_table.add_column(style="white", overflow="fold")
        progress_table.add_row(
            _tr("pipeline_steps"),
            f"{active_pipeline_progress.get('completed_steps', 0)}/{active_pipeline_progress.get('started_steps', 0)} {_tr('completed')}",
        )
        current_step = active_pipeline_progress.get("current_step")
        if current_step:
            progress_table.add_row(_tr("current_step"), str(current_step))
        current_description = active_pipeline_progress.get("current_description")
        if current_description:
            progress_table.add_row(_tr("what_it_does"), str(current_description))
        recent_completed = active_pipeline_progress.get("recent_completed", [])
        if recent_completed:
            progress_table.add_row(
                _tr("recent"),
                " -> ".join(str(step) for step in recent_completed),
            )
        sample_count = active_pipeline_progress.get("sample_count", 0)
        if sample_count:
            progress_table.add_row(_tr("sample_count"), str(sample_count))
        renderables.append(
            Panel(
                progress_table,
                title=f"[bold cyan]{_tr('pipeline_progress')}[/bold cyan]",
                border_style=COLOR_INFO,
                padding=(0, 1),
            )
        )

    if timeline:
        table = Table(
            box=box.SIMPLE_HEAVY,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column(_tr("step"), style="dim", width=4, justify="right")
        table.add_column(_tr("tool"), style="bold white", min_width=24)
        table.add_column(_tr("status"), min_width=10)
        table.add_column(_tr("time"), style="white", min_width=8)
        table.add_column(_tr("highlights"), style="white", overflow="fold")

        for event in timeline[-MAX_VISIBLE_TIMELINE_ROWS:]:
            state_style = _style_for_status(event["status"])
            duration = event.get("duration_seconds")
            if event["status"] == "running":
                duration_text = _format_duration(time.time() - float(event["started_at"]))
            else:
                duration_text = _format_duration(duration)
            table.add_row(
                str(event["step"]),
                event["name"],
                f"[{state_style}]{_display_status(event['status']).upper()}[/{state_style}]",
                duration_text,
                event["summary"],
            )
        renderables.append(table)

    return Panel(
        Group(*renderables),
        title=f"[bold cyan]{_tr('activity')}[/bold cyan]",
        border_style=COLOR_INFO,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _print_tool_timeline(events: list[dict[str, Any]]) -> None:
    if not events:
        return

    table = Table(
        title=_tr("tool_timeline"),
        box=box.ROUNDED,
        border_style=COLOR_INFO,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column(_tr("step"), style="dim", width=4, justify="right")
    table.add_column(_tr("tool"), style="bold white", min_width=22)
    table.add_column(_tr("status"), min_width=10)
    table.add_column(_tr("time"), min_width=8)
    table.add_column(_tr("highlights"), overflow="fold")
    table.add_column(_tr("advice"), overflow="fold")

    for event in events:
        state_style = _style_for_status(event["status"])
        table.add_row(
            str(event["step"]),
            event["name"],
            f"[{state_style}]{_display_status(event['status']).upper()}[/{state_style}]",
            _format_duration(event.get("duration_seconds")),
            event["summary"],
            event["advice"],
        )

    console.print(table)
    console.print()


def _build_pipeline_summary_panels(payload: dict[str, Any]) -> list[Panel]:
    summary_path = payload.get("summary_path")
    if not isinstance(summary_path, str):
        return []

    summary = _load_json_file(summary_path)
    if summary is None:
        return []

    effective_params = summary.get("effective_params", {})
    sample_ids = summary.get("sample_ids", [])
    steps = summary.get("steps", [])
    analysis_outputs = summary.get("outputs", {}).get("analysis_outputs", {})
    final_outputs = summary.get("outputs", {}).get("final_outputs", {})
    skipped_optional_steps = summary.get("skipped_optional_steps", [])
    completed_steps = [
        step for step in steps
        if isinstance(step, dict) and step.get("status") == "completed"
    ]

    overview = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    overview.add_column(style="dim", min_width=14)
    overview.add_column(style="white", overflow="fold")
    overview.add_row(_tr("status"), _display_status(summary.get("status", "unknown")).upper())
    overview.add_row(_tr("sample_count"), str(len(sample_ids)))
    overview.add_row(_tr("feature_method"), str(effective_params.get("feature_method", "(unknown)")))
    overview.add_row(_tr("filter_route"), str(effective_params.get("filter_route", "(unknown)")))
    overview.add_row(_tr("output_root"), str(effective_params.get("output_root", "(unknown)")))
    overview.add_row(_tr("completed_steps"), str(len(completed_steps)))

    diversity = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    diversity.add_column(style="dim", min_width=14)
    diversity.add_column(style="white", overflow="fold")
    diversity.add_row("Rarefaction", str(analysis_outputs.get("rarefaction_depth", "(auto)")))
    diversity.add_row(
        _tr("generated_beta"),
        ", ".join(str(item) for item in analysis_outputs.get("generated_beta_metrics", [])) or "(none)",
    )
    diversity.add_row(
        _tr("skipped_beta"),
        ", ".join(str(item) for item in analysis_outputs.get("skipped_beta_metrics", [])) or "(none)",
    )
    diversity.add_row(_tr("pipeline_steps"), str(len(steps)))
    if skipped_optional_steps:
        diversity.add_row(_tr("optional_skips"), ", ".join(str(item) for item in skipped_optional_steps))

    files = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    files.add_column(style="dim", min_width=14)
    files.add_column(style="white", overflow="fold")
    files.add_row("Feature Table", str(final_outputs.get("feature_table", "(missing)")))
    files.add_row("Taxonomy", str(final_outputs.get("taxonomy", "(missing)")))
    files.add_row(_tr("summary"), os.path.abspath(summary_path))

    return [
        Panel(overview, title=f"[bold cyan]{_tr('run_overview')}[/bold cyan]", border_style=COLOR_SUCCESS),
        Panel(diversity, title=f"[bold cyan]{_tr('diversity')}[/bold cyan]", border_style=COLOR_INFO),
        Panel(files, title=f"[bold cyan]{_tr('key_outputs')}[/bold cyan]", border_style=COLOR_INFO),
    ]


def _print_result_highlights(tool_events: list[dict[str, Any]]) -> None:
    successful_events = [event for event in tool_events if event["status"] == "ok"]
    if not successful_events:
        return

    latest = successful_events[-1]
    payload = latest.get("result", {}).get("result")
    if latest["name"] == "run_raw_amplicon_pipeline" and isinstance(payload, dict):
        panels = _build_pipeline_summary_panels(payload)
        if panels:
            console.print(Columns(panels, equal=True, expand=True))
            console.print()
            return

    if isinstance(payload, dict):
        files = _extract_existing_file_paths(payload)
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column(style="dim", min_width=14)
        table.add_column(style="white", overflow="fold")
        table.add_row(_tr("tool"), latest["name"])
        table.add_row(_tr("summary"), latest["summary"])
        if files:
            table.add_row(_tr("outputs"), "\n".join(files[:3]))
        console.print(
            Panel(
                table,
                title=f"[bold cyan]{_tr('highlights')}[/bold cyan]",
                border_style=COLOR_INFO,
                padding=(0, 1),
            )
        )
        console.print()


def _build_next_actions(agent: Any, tool_events: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []

    if not agent.session_pipeline_params:
        suggestions.append(
            "使用 /params 确认或编辑当前 pipeline 默认参数。"
            if _is_chinese_ui()
            else "/params to confirm or edit the active pipeline defaults."
        )

    if tool_events:
        latest = tool_events[-1]
        if latest["status"] == "error":
            if _is_chinese_ui():
                suggestions.append("使用 /params 检查输入、可执行文件路径或可选设置。")
                suggestions.append("修复上方问题后，再用更具体的请求重试。")
            else:
                suggestions.append("/params to inspect inputs, executable paths, or optional settings.")
                suggestions.append("Retry with a more specific run request after fixing the highlighted issue.")
            return suggestions[:3]

        if latest["name"] == "run_raw_amplicon_pipeline":
            if _is_chinese_ui():
                suggestions.append("使用 /report 导出本次运行的 Markdown 摘要。")
                suggestions.append("使用 /history 查看本会话的对话和工具轨迹。")
                suggestions.append("继续要求解读 alpha、beta 或 taxonomy 输出。")
            else:
                suggestions.append("/report to export a Markdown summary of this run.")
                suggestions.append("/history to review the session trace in dialogue form.")
                suggestions.append("Ask for interpretation of alpha, beta, or taxonomy outputs.")
            return suggestions[:3]

    if agent.state.get_completed_steps():
        if _is_chinese_ui():
            suggestions.append("使用 /status 查看当前产物和最近工具运行。")
            suggestions.append("使用 /report 将当前会话导出为 Markdown。")
            suggestions.append("使用 /history 查看对话和工具轨迹。")
        else:
            suggestions.append("/status to inspect current artifacts and recent tool runs.")
            suggestions.append("/report to export the current session into Markdown.")
            suggestions.append("/history to inspect the conversation and tool trace.")
    else:
        if _is_chinese_ui():
            suggestions.append("描述下一步分析目标，例如：快速分析 seq/。")
            suggestions.append("使用 /tools 查看可用分析动作。")
        else:
            suggestions.append("Describe the next analysis goal, for example: quickly analyze seq/.")
            suggestions.append("/tools to inspect the available analysis actions.")

    if agent.session_pipeline_params:
        suggestions.append(
            "使用 /params 查看或微调已确认默认参数。"
            if _is_chinese_ui()
            else "/params to review or fine-tune the confirmed defaults."
        )

    return suggestions[:3]


def _print_next_actions(agent: Any, tool_events: list[dict[str, Any]]) -> None:
    suggestions = _build_next_actions(agent, tool_events)
    if not suggestions:
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    table.add_column(style=f"bold {COLOR_INFO}", width=3)
    table.add_column(style="white", overflow="fold")
    for index, suggestion in enumerate(suggestions, start=1):
        table.add_row(str(index), suggestion)

    console.print(
        Panel(
            table,
            title=f"[bold cyan]{_tr('next_steps')}[/bold cyan]",
            border_style=COLOR_MUTED,
            padding=(0, 1),
        )
    )
    console.print()


def _build_input_prompt(agent: Any) -> str:
    mode_raw = str(getattr(getattr(agent, "state", None), "startup_mode", "session"))
    mode = _display_status(mode_raw) if _is_chinese_ui() else mode_raw.upper()
    if _is_chinese_ui():
        params_badge = "参数已确认" if getattr(agent, "session_pipeline_params", None) else "参数未确认"
    else:
        params_badge = "PARAMS OK" if getattr(agent, "session_pipeline_params", None) else "PARAMS?"
    return (
        f"[bold {COLOR_USER}]{_tr('you')}[/bold {COLOR_USER}] "
        f"[dim][{mode} | {params_badge}][/dim] "
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X-Amplicon AI Agent - interactive 16S analysis assistant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python agent_cli.py\n"
            "  python agent_cli.py --resume\n"
            "  python agent_cli.py --model gpt-4o\n"
            "  python agent_cli.py --model openai/qwen-max --api-base https://proxy.example.com/v1\n"
            "  python agent_cli.py --list-models\n"
            "  python agent_cli.py --reset\n"
            "\nSpecial commands during chat:\n"
            "  /status  - show session status, artifacts, and recent tool runs\n"
            "  /new     - start a new conversation\n"
            "  /reset   - clear conversation history and start fresh\n"
            "  /tools   - list all available analysis tools\n"
            "  /params  - review or update pipeline params\n"
            "  /language - switch CLI language (Chinese or English)\n"
            "  /help    - show command help and example prompts\n"
            "  /clear   - clear the terminal and redraw the dashboard\n"
            "  /history - show conversation history (supports role/limit)\n"
            "  /report  - generate or preview the Markdown analysis report\n"
            "  /config  - show current model / API configuration\n"
            "  /quit    - exit the agent\n"
        ),
    )
    parser.add_argument("--model", default=None,
        help="LiteLLM model string. Overrides DEFAULT_MODEL env var and .env file.")
    parser.add_argument("--api-key", default=None, dest="api_key",
        help="API key. Overrides LLM_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY.")
    parser.add_argument("--api-base", default=None, dest="api_base",
        help="Custom base URL for OpenAI-compatible proxy.")
    parser.add_argument("--env-file", default=None, dest="env_file",
        help="Path to a .env file (default: .env in project root).")
    parser.add_argument("--list-models", action="store_true",
        help="Print a list of common supported model strings and exit.")
    parser.add_argument("--state", default=None,
        help="Path to the agent state JSON file.")
    parser.add_argument("--resume", action="store_true",
        help="Resume the saved conversation state instead of starting fresh.")
    parser.add_argument("--reset", action="store_true",
        help="Clear saved state before starting.")
    parser.add_argument("--quiet", action="store_true",
        help="Suppress tool call details from stdout.")
    parser.add_argument("--params", default="pipeline_params.yaml",
        help="Path to the pipeline params YAML file shown at startup.")
    parser.add_argument("--skip-param-confirmation", action="store_true",
        help="Start the agent without the startup pipeline parameter confirmation step.")
    parser.add_argument("--offline", action="store_true",
        help="Start without an LLM API key. Slash commands remain available; natural-language orchestration is disabled.")
    parser.add_argument("--require-llm", action="store_true",
        help="Exit with a configuration error if no LLM API key is available.")
    return parser.parse_args()


def _print_models() -> None:
    from agent.config import KNOWN_MODELS
    table = Table(
        title="Common LiteLLM Model Strings",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold cyan",
        expand=False,
    )
    table.add_column("Model String", style="bold white", min_width=45)
    table.add_column("Description", style="white")
    for model_id, description in KNOWN_MODELS:
        table.add_row(model_id, description)
    console.print(table)
    console.print("[dim]Full list: https://docs.litellm.ai/docs/providers[/dim]")
    console.print("[dim]Proxy models: prefix with 'openai/' and set --api-base.[/dim]\n")


class OfflineAmpliconAgent:
    """Minimal agent shell used when no LLM API key is configured."""

    llm_available = False

    def __init__(
        self,
        *,
        config: Any,
        state: Any,
        reason: str,
    ) -> None:
        self.config = config
        self.state = state
        self.offline_reason = reason
        self.verbose = False
        self.session_context: str | None = None
        self.session_pipeline_params_path: str | None = None
        self.session_pipeline_params: dict[str, Any] | None = None

    def reset(self) -> None:
        self.state.reset()

    def set_session_context(self, context: str | None) -> None:
        self.session_context = context

    def set_session_pipeline_params(
        self,
        *,
        params_path: str | None,
        params: dict[str, Any] | None,
        context: str | None = None,
    ) -> None:
        self.session_pipeline_params_path = (
            None if params_path is None else os.path.abspath(params_path)
        )
        self.session_pipeline_params = None if params is None else dict(params)
        self.session_context = context

    def chat(self, user_message: str) -> str:
        task_id = uuid.uuid4().hex
        task_start_time = time.perf_counter()
        self.state.add_message("user", user_message)
        turn_index = sum(
            1 for message in self.state.get_messages() if message.get("role") == "user"
        )
        reply = (
            "Natural-language Agent orchestration is disabled because no LLM API key "
            "is configured. The deterministic CLI remains fully available. Use "
            "`python process.py cli-only-workflow` to print the recommended command "
            "sequence, or use slash commands here: /help, /params, /status, /tools, "
            "/report, /config, /language, /quit."
        )
        if _is_chinese_ui():
            reply = (
                "当前处于无 LLM 模式：未配置 LLM API key，因此自然语言自动编排已禁用。"
                "确定性 CLI 仍可完整使用。可以运行 "
                "`python process.py cli-only-workflow` 查看推荐命令序列，或在此使用 "
                "/help、/params、/status、/tools、/report、/config、/language、/quit。"
            )
        self.state.add_message("assistant", reply)
        try:
            from agent.evaluation_logger import record_task_evaluation_event

            event = record_task_evaluation_event(
                task_id=task_id,
                user_message=user_message,
                status="no_llm",
                start_time=task_start_time,
                turn_index=turn_index,
                round_count=0,
                tool_call_count=0,
                failure_reason=reply,
                assistant_reply=reply,
                model=getattr(self.config, "model", None),
                llm_available=False,
            )
            self.state.record_task_result(event)
        except Exception:  # noqa: BLE001
            pass
        return reply


def _print_no_llm_mode_notice(reason: str, *, params_path: str, output_root: str = "work") -> None:
    workflow_text = format_cli_only_workflow(
        build_cli_only_workflow(
            params_path=params_path,
            output_root=output_root,
        )
    )

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    table.add_column(style="dim", min_width=16)
    table.add_column(style="white", overflow="fold")
    if _is_chinese_ui():
        table.add_row("状态", "无 LLM 模式")
        table.add_row("原因", reason)
        table.add_row("可用", "CLI、/params、/status、/tools、/report、/config、/language")
        table.add_row("不可用", "自然语言自动 tool 调用，直到配置 LLM_API_KEY 或 --api-key")
        title = "无 LLM 模式"
    else:
        table.add_row("Mode", "No LLM / CLI-only")
        table.add_row("Reason", reason)
        table.add_row("Available", "CLI, /params, /status, /tools, /report, /config, /language")
        table.add_row("Disabled", "Natural-language tool orchestration until LLM_API_KEY or --api-key is set")
        title = "No LLM Mode"

    console.print(
        Panel(
            table,
            title=f"[bold yellow]{title}[/bold yellow]",
            border_style=COLOR_WARNING,
            padding=(0, 1),
        )
    )
    console.print(
        Panel(
            Syntax(workflow_text, "text", word_wrap=True),
            title="[bold cyan]CLI-only workflow[/bold cyan]",
            border_style=COLOR_INFO,
            padding=(0, 1),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------

def _cmd_language(agent: Any, requested_language: str | None = None) -> None:
    language = _normalize_language(requested_language)
    if requested_language is None:
        console.print(
            f"[dim]{_tr('current_language')}: {_display_language_name()}[/dim]"
        )
        choice = console.input(
            f"[bold green]{_tr('language')}[/bold green] {_tr('language_prompt')}"
        ).strip()
        if not choice:
            console.print(f"[yellow]{_tr('language_cancelled')}[/yellow]\n")
            return
        language = _normalize_language(choice)

    if language is None:
        console.print(f"[yellow]{_tr('language_invalid')}[/yellow]\n")
        return

    _set_ui_language(language)
    state = getattr(agent, "state", None)
    if state is not None and hasattr(state, "set_preference"):
        state.set_preference(LANGUAGE_PREFERENCE_KEY, language)

    console.print(
        f"[green]{_tr('language_switched', language=_display_language_name(language))}[/green]\n"
    )
    console.print(
        _render_session_status_panel(
            _build_session_snapshot(agent, params_status=_current_params_status(agent))
        )
    )
    console.print()


def _handle_slash_command(command: str, agent: Any) -> bool:
    raw_cmd = command.strip()
    cmd = raw_cmd.lower()

    if cmd in ("/quit", "/exit"):
        console.print(Rule(style=COLOR_MUTED))
        console.print(f"[dim]{_tr('goodbye')}[/dim]\n")
        sys.exit(0)

    if cmd in ("/new", "/reset"):
        agent.reset()
        state = getattr(agent, "state", None)
        if state is not None:
            state.startup_mode = "fresh"
            state.startup_note_key = "new_conversation_started"
            state.startup_note_args = {}
            state.startup_note = _tr("new_conversation_started")
        suffix = _tr("confirmed_params_remain_active") if agent.session_pipeline_params else ""
        console.print(f"[yellow]{_tr('new_conversation_started')}{suffix}[/yellow]\n")
        console.print(
            _render_session_status_panel(
                _build_session_snapshot(agent, params_status=_current_params_status(agent))
            )
        )
        console.print()
        return True

    if cmd in ("/help", "/?"):
        _cmd_help(agent)
        return True

    if cmd == "/clear":
        console.clear()
        _cmd_help(agent)
        return True

    if cmd == "/status":
        _cmd_status(agent)
        return True

    if cmd == "/tools":
        _print_tools()
        return True

    if cmd == "/params":
        _cmd_params(agent)
        return True

    if cmd == "/language" or cmd.startswith("/language "):
        requested_language = (
            raw_cmd.split(maxsplit=1)[1].strip()
            if len(raw_cmd.split(maxsplit=1)) > 1
            else None
        )
        _cmd_language(agent, requested_language=requested_language)
        return True

    if cmd == "/history" or cmd.startswith("/history "):
        role_filter, limit = _resolve_history_options(raw_cmd)
        _print_history_view(agent, role_filter=role_filter, limit=limit)
        return True

    if cmd == "/config":
        _print_config(agent)
        return True

    if cmd == "/report" or cmd.startswith("/report "):
        report_mode = raw_cmd.split(maxsplit=1)[1].strip().lower() if len(raw_cmd.split(maxsplit=1)) > 1 else "write"
        _cmd_report(agent, mode=report_mode)
        return True

    return False


def _chat_with_events(
    agent: Any,
    user_message: str,
    *,
    on_activity: Any | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run agent.chat() while intercepting tool calls for rich timeline display."""
    import agent.agent as agent_module
    from agent.tools import execute_tool as original_execute_tool

    events: list[dict[str, Any]] = []
    started_at = time.time()

    def _publish(phase: str) -> None:
        if on_activity is None:
            return
        on_activity(
            {
                "phase": phase,
                "started_at": started_at,
                "timeline": [dict(event) for event in events],
            }
        )

    def _patched_execute_tool(name: str, arguments: dict) -> dict:
        step = len(events) + 1
        event = {
            "step": step,
            "name": name,
            "status": "running",
            "started_at": time.time(),
            "arguments": dict(arguments),
            "summary": "正在执行工具调用..." if _is_chinese_ui() else "Executing tool call...",
            "advice": "等待工具输出。" if _is_chinese_ui() else "Waiting for tool output.",
        }
        events.append(event)
        _publish(f"{'正在运行工具' if _is_chinese_ui() else 'Running tool'} {step}: {name}")

        stop_monitor = threading.Event()
        monitor_thread: threading.Thread | None = None
        if name == "run_raw_amplicon_pipeline":
            output_root = arguments.get("output_root")
            if not isinstance(output_root, str) or not output_root.strip():
                session_params = getattr(agent, "session_pipeline_params", None) or {}
                output_root = session_params.get("output_root")
            if isinstance(output_root, str) and output_root.strip():
                summary_path = os.path.abspath(
                    os.path.join(output_root, "06_final", "run_summary.json")
                )
                event["summary_path"] = summary_path
                monitor_thread = threading.Thread(
                    target=_monitor_pipeline_summary,
                    args=(summary_path, event, _publish, stop_monitor),
                    daemon=True,
                )
                monitor_thread.start()

        try:
            result = original_execute_tool(name, arguments)
        finally:
            stop_monitor.set()
            if monitor_thread is not None:
                monitor_thread.join(timeout=1.0)
        event["duration_seconds"] = time.time() - float(event["started_at"])
        event["result"] = result
        event["status"] = "ok" if result.get("status") == "ok" else "error"
        event["summary"] = _summarize_tool_result_for_display(name, result)
        event["advice"] = _build_timeline_advice(event)
        _publish(
            f"已完成 {len(events)} 次工具调用"
            if _is_chinese_ui()
            else f"Completed {len(events)} tool call(s)"
        )
        return result

    agent_module.execute_tool = _patched_execute_tool
    try:
        _publish(
            "等待模型选择下一步动作"
            if _is_chinese_ui()
            else "Waiting for the model to choose the next action"
        )
        reply = agent.chat(user_message)
    finally:
        agent_module.execute_tool = original_execute_tool

    return reply, events


def main() -> None:
    args = _parse_args()
    _load_saved_ui_language(args)

    if args.list_models:
        _print_models()
        return

    from agent.config import AgentConfig
    from agent.tools import set_session_pipeline_defaults

    if args.offline and args.require_llm:
        console.print(
            "[bold red]Configuration error:[/bold red] --offline and --require-llm cannot be used together."
        )
        sys.exit(2)

    config_kwargs: dict[str, Any] = {}
    if args.model:
        config_kwargs["model"] = args.model
    if args.api_key:
        config_kwargs["api_key"] = args.api_key
    if args.api_base:
        config_kwargs["api_base"] = args.api_base
    if args.env_file:
        config_kwargs["env_file"] = args.env_file

    config = AgentConfig(**config_kwargs)
    offline_reason: str | None = None

    if args.offline:
        offline_reason = "--offline was requested."
    else:
        try:
            config.validate()
        except ValueError as exc:
            if args.require_llm:
                console.print(f"[bold red]{_tr('configuration_error')}:[/bold red] {exc}")
                sys.exit(1)
            offline_reason = str(exc)

    state = _create_agent_state(args)
    if offline_reason is None:
        from agent.agent import AmpliconAgent

        agent = AmpliconAgent(
            config=config,
            state=state,
            verbose=False,
        )
    else:
        state.startup_mode = "offline"
        state.startup_note_key = None
        state.startup_note_args = {}
        state.startup_note = (
            "LLM API key is not configured; natural-language orchestration is disabled."
        )
        agent = OfflineAmpliconAgent(
            config=config,
            state=state,
            reason=offline_reason,
        )
    _set_unconfirmed_pipeline_context(agent, args.params)

    startup_params_status = (
        _tr("startup_params_skipped")
        if args.skip_param_confirmation
        else _tr("startup_params_pending")
    )
    _print_banner(
        config.summary(),
        _build_session_snapshot(agent, params_status=startup_params_status),
    )
    if offline_reason is not None:
        _print_no_llm_mode_notice(offline_reason, params_path=args.params)

    set_session_pipeline_defaults(None)
    if not args.skip_param_confirmation:
        session_pipeline_params, _ = _confirm_pipeline_params(
            args.params,
            confirm_message=_tr("pipeline_params_confirmed"),
            skip_message=_tr("startup_param_confirmation_skipped"),
        )
        if session_pipeline_params is not None:
            _apply_session_pipeline_params(agent, args.params, session_pipeline_params)
            console.print(
                _render_session_status_panel(
                    _build_session_snapshot(agent, params_status=_current_params_status(agent))
                )
            )
            console.print()

    while True:
        try:
            user_input = console.input(_build_input_prompt(agent)).strip()
        except (EOFError, KeyboardInterrupt):
            console.print(Rule(style=COLOR_MUTED))
            console.print(f"[dim]{_tr('goodbye')}[/dim]\n")
            break

        if not user_input:
            continue

        if user_input.lower() == "language":
            if _handle_slash_command("/language", agent):
                continue

        if user_input.startswith("/"):
            if _handle_slash_command(user_input, agent):
                continue

        try:
            if not getattr(agent, "llm_available", True):
                reply = agent.chat(user_input)
                tool_events = []
            elif not args.quiet:
                activity: dict[str, Any] = {
                    "phase": "正在理解你的请求" if _is_chinese_ui() else "Thinking about your request",
                    "started_at": time.time(),
                    "timeline": [],
                }
                with Live(
                    _render_tool_activity_panel(activity),
                    console=console,
                    refresh_per_second=6,
                    transient=True,
                ) as live:
                    def _update_activity(next_activity: dict[str, Any]) -> None:
                        activity.clear()
                        activity.update(next_activity)
                        live.update(_render_tool_activity_panel(activity))

                    reply, tool_events = _chat_with_events(
                        agent,
                        user_input,
                        on_activity=_update_activity,
                    )
            else:
                reply = agent.chat(user_input)
                tool_events = []
        except Exception as exc:
            console.print(f"\n[bold red]{_tr('error')}:[/bold red] {type(exc).__name__}: {exc}\n")
            continue

        _print_tool_timeline(tool_events)
        for event in tool_events:
            if event["status"] == "ok":
                _try_preview_result(event["result"])
        _print_result_highlights(tool_events)

        console.print(
            Panel(
                reply,
                title=f"[bold cyan]{_tr('agent')}[/bold cyan]",
                border_style=COLOR_AGENT,
                padding=(0, 2),
            )
        )
        console.print()
        _print_next_actions(agent, tool_events)


if __name__ == "__main__":
    main()
