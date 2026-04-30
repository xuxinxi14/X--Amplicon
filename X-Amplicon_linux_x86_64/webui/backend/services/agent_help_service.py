"""Rule-based and optional LLM help services for the Web UI Agent page."""

from __future__ import annotations

import importlib.util
import json
import re
from typing import Any

from agent.config import AgentConfig

from webui.backend.models.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentExplainRequest,
    AgentExplainResponse,
    AgentStatusResponse,
)


AGENT_CAPABILITIES = [
    "offline_guided_help",
    "analysis_chat",
    "error_explanation",
    "parameter_guidance",
    "reproducible_command_suggestions",
]


def _provider_from_model(model: str) -> str:
    text = model.lower()
    if text.startswith("openai/") or text.startswith("gpt-"):
        return "openai-compatible"
    if text.startswith("claude"):
        return "anthropic"
    if text.startswith("gemini/"):
        return "gemini"
    return text.split("/", 1)[0] if "/" in text else "default"


def get_agent_status() -> AgentStatusResponse:
    """Return a safe status summary for the optional LLM layer."""

    config = AgentConfig()
    key_configured = bool(config.api_key)
    litellm_available = importlib.util.find_spec("litellm") is not None

    if not key_configured:
        return AgentStatusResponse(
            status="no-key",
            llm_available=False,
            key_configured=False,
            model=config.model,
            api_base_configured=bool(config.api_base),
            provider=_provider_from_model(config.model),
            message="No LLM API key is configured. The Web UI will use local rule-based help only.",
            capabilities=AGENT_CAPABILITIES,
            disabled_reason="missing_api_key",
        )

    if not litellm_available:
        return AgentStatusResponse(
            status="offline",
            llm_available=False,
            key_configured=True,
            model=config.model,
            api_base_configured=bool(config.api_base),
            provider=_provider_from_model(config.model),
            message="LLM key is configured, but the litellm package is not available.",
            capabilities=AGENT_CAPABILITIES,
            disabled_reason="missing_litellm",
        )

    return AgentStatusResponse(
        status="online",
        llm_available=True,
        key_configured=True,
        model=config.model,
        api_base_configured=bool(config.api_base),
        provider=_provider_from_model(config.model),
        message="LLM configuration is present. Explanations can use the optional LLM layer.",
        capabilities=[*AGENT_CAPABILITIES, "llm_explanation", "llm_chat"],
    )


def _is_chat_zh(request: AgentChatRequest) -> bool:
    return request.language == "Chinese"


def _last_user_message(request: AgentChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _chat_commands_for_text(text: str) -> list[str]:
    lowered = text.lower()
    if _contains(lowered, "metadata", "sampleid", "sample id"):
        return ["python process.py validate-metadata --metadata metadata.txt --sample-id-col SampleID --group-col Group"]
    if _contains(lowered, "fastq", "r1", "r2", "pair"):
        return ["python process.py preview-fastq-pairs --metadata metadata.txt --seq-dir seq --read1-suffix _1.fq.gz --read2-suffix _2.fq.gz"]
    if _contains(lowered, "database", "rdp", "silva", "sintax"):
        return ["python process.py list-databases", "python process.py check-database rdp_16s_v18"]
    if _contains(lowered, "plot", "visual", "图", "可视化", "report", "报告", "06_final"):
        return [
            "python process.py visualization-suite --final-dir work\\06_final --format html",
            "python process.py generate-report --final-dir work\\06_final",
        ]
    if _contains(lowered, "differential", "差异", "ko", "wt", "case", "control"):
        return ["python process.py differential-abundance --metadata metadata.txt --otutab work\\06_final\\otutab.txt --compare KO:WT --format html"]
    return [
        "python process.py check-pipeline-config --params pipeline_params.webui.yaml",
        "python process.py run-pipeline-config --params pipeline_params.webui.yaml",
    ]


def _rule_based_chat(request: AgentChatRequest, *, mode: str = "rule_based", warning: str | None = None) -> AgentChatResponse:
    zh = _is_chat_zh(request)
    user_text = _last_user_message(request)
    context = f"{user_text}\n{request.project_summary}"
    has_project = bool(request.project_summary.strip())

    if not user_text:
        message = (
            "你可以直接告诉我你的分析目标，例如“我想分析这一批 16S 双端测序数据”。我会按项目创建、metadata 检查、FASTQ 配对、分组设置、preflight、完整分析、结果解读的顺序带你完成。"
            if zh else
            "Tell me what you want to analyze, for example: \"I want to analyze this paired-end 16S dataset.\" I will guide you through project setup, metadata checks, FASTQ pairing, groups, preflight, full analysis, and result review."
        )
    elif _contains(context, "plot", "visual", "可视化", "图表", "report", "报告", "index.html"):
        message = (
            "如果旧任务显示 completed 但没有图表，原因通常是只运行了数据处理阶段，尚未继续执行 visualization-suite 和 generate-report。当前 Web UI 的完整分析任务会在 pipeline 完成后自动继续生成 plots 和 report；旧结果可以重新启动完整分析，或在 Results 页面单独生成报告。"
            if zh else
            "If an older job was marked completed but produced no plots, it usually ran only the data-processing stage and did not continue to visualization-suite and generate-report. The current Web UI full-analysis job continues to plots and report after the pipeline finishes. For older outputs, rerun full analysis or generate the report from Results."
        )
    elif _contains(context, "start", "begin", "开始", "新建", "分析"):
        message = (
            "建议先从“新建分析”创建项目。第一步只需要确认项目目录、metadata 文件和 FASTQ 文件夹；随后运行 metadata 与 FASTQ 配对检查。检查通过后再设置分组和差异比较，最后先跑 preflight，再启动完整分析。"
            if zh else
            "Start from New Analysis. First confirm the project directory, metadata file, and FASTQ folder, then run metadata and FASTQ pairing checks. After those pass, set groups and optional comparisons, run preflight, then start the full analysis."
        )
    elif _contains(context, "metadata", "sampleid", "sample id", "group"):
        message = (
            "metadata 至少需要样本 ID 列和分组列。请确认列名与界面设置完全一致，SampleID 唯一且非空，Group 没有缺失值；然后再预览 FASTQ 配对。"
            if zh else
            "Metadata needs at least a sample ID column and a group column. Confirm the column names exactly match the UI settings, SampleID values are unique and non-empty, and Group has no missing values before previewing FASTQ pairs."
        )
    elif _contains(context, "fastq", "r1", "r2", "pair", "配对"):
        message = (
            "FASTQ 配对依赖 SampleID 与文件名前缀一致。请检查 read1/read2 后缀，例如 `_1.fq.gz` 和 `_2.fq.gz`，并确认每个样本都有 R1 与 R2。"
            if zh else
            "FASTQ pairing depends on SampleID matching filename prefixes. Check read1/read2 suffixes such as `_1.fq.gz` and `_2.fq.gz`, and confirm every sample has both R1 and R2."
        )
    elif _contains(context, "database", "rdp", "silva", "sintax", "数据库"):
        message = (
            "数据库问题优先检查 FASTA 文件是否存在、数据库名称是否已注册，以及 taxonomy_format 是否与数据库格式一致。小型 rdp_16s_v18.fa 可以作为开箱即用测试库。"
            if zh else
            "For database issues, first check whether the FASTA exists, the database name is registered, and taxonomy_format matches the database format. The small rdp_16s_v18.fa database is suitable for out-of-box testing."
        )
    elif _contains(context, "differential", "差异", "ko", "wt", "case", "control"):
        message = (
            "差异比较方向使用 CASE:CONTROL，例如 KO:WT 表示 KO 相对 WT 的变化。每个比较组建议至少有 2 个样本；样本数过低时结果只能作为探索性参考。"
            if zh else
            "Differential comparison direction uses CASE:CONTROL, for example KO:WT means KO relative to WT. Each compared group should preferably have at least two samples; very small groups should be treated as exploratory."
        )
    else:
        message = (
            "我可以围绕 X-Amplicon 的完整 16S 工作流回答问题，也可以一步步引导你完成分析。请告诉我当前停在哪一步，或把 Run Monitor 中最后几十行日志发给我。"
            if zh else
            "I can answer questions around the full X-Amplicon 16S workflow or guide you step by step. Tell me where you are in the workflow, or paste the last few dozen lines from Run Monitor."
        )

    actions = (
        ["打开新建分析并检查输入", "运行 preflight", "完成后查看 Results 中的 plots、report 和 provenance"]
        if zh else
        ["Open New Analysis and check inputs", "Run preflight", "After completion, review plots, report, and provenance in Results"]
    )
    if has_project:
        actions.insert(0, "使用当前项目上下文继续判断下一步" if zh else "Use the selected project context for the next step")

    warnings = [warning] if warning else []
    if mode == "rule_based" and request.prefer_llm:
        warnings.append(
            "当前未使用 LLM，回复来自本地规则引导。" if zh else "LLM was not used; this response comes from local workflow rules."
        )

    return AgentChatResponse(
        status="ok" if mode != "fallback" else "warning",
        mode=mode,  # type: ignore[arg-type]
        message=message,
        suggested_actions=actions,
        suggested_commands=_chat_commands_for_text(context),
        warnings=_unique(warnings),
    )


def _llm_chat(request: AgentChatRequest) -> AgentChatResponse:
    config = AgentConfig()
    status = get_agent_status()
    if not status.llm_available:
        return _rule_based_chat(request)

    from litellm import completion  # type: ignore[import-not-found]

    language = "Chinese" if request.language == "Chinese" else "English"
    system_prompt = (
        "You are X-Amplicon Agent, a specialist assistant for Windows-first 16S rRNA amplicon analysis. "
        "You are built on a deterministic X-Amplicon workflow that handles paired-end FASTQ input, metadata checks, "
        "OTU/ASV generation, taxonomy annotation, alpha/beta diversity, visualization, differential abundance, "
        "reports, and provenance. Guide users step by step through the Web UI when they want to start analysis. "
        "Use the selected project context when provided, but never invent files, sample groups, or completed results. "
        "Never claim that you executed commands or changed files from this chat. Keep advice practical for bench scientists. "
        "When useful, mention the exact Web UI page or deterministic CLI command. "
        f"Reply in {language}; keep technical terms such as FASTQ, metadata, preflight, OTU/ASV, PCoA, and provenance in English when clearer."
    )
    context_prompt = {
        "language": language,
        "project_summary": request.project_summary[:5000],
        "response_contract": {
            "message": "natural language answer",
            "suggested_actions": ["short actionable UI steps"],
            "suggested_commands": ["optional deterministic commands"],
            "warnings": ["optional caveats"],
        },
    }
    history = [
        {"role": message.role, "content": message.content[:4000]}
        for message in request.messages[-12:]
        if message.content.strip()
    ]
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context_prompt, ensure_ascii=False)},
            *history,
        ],
        "api_key": config.api_key,
        "timeout": 45,
        "temperature": 0.25,
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = completion(**kwargs)
    content = str(response.choices[0].message.content or "").strip()
    if not content:
        return _rule_based_chat(request, mode="fallback", warning="LLM returned an empty response.")

    return AgentChatResponse(
        status="ok",
        mode="llm",
        message=content,
        suggested_actions=[],
        suggested_commands=[],
        warnings=[],
    )


def chat_with_agent(request: AgentChatRequest) -> AgentChatResponse:
    """Return a conversational 16S workflow response using optional LLM assistance."""

    if not request.prefer_llm:
        return _rule_based_chat(request)
    try:
        return _llm_chat(request)
    except Exception as exc:
        return _rule_based_chat(request, mode="fallback", warning=str(exc))


def _is_zh(request: AgentExplainRequest) -> bool:
    return request.language == "Chinese"


def _contains(text: str, *patterns: str) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _commands_for_context(context_type: str) -> list[str]:
    if context_type == "metadata":
        return [
            "python process.py validate-metadata --metadata metadata.txt --sample-id-col SampleID --group-col Group",
        ]
    if context_type == "fastq":
        return [
            "python process.py preview-fastq-pairs --metadata metadata.txt --seq-dir seq --read1-suffix _1.fq.gz --read2-suffix _2.fq.gz",
        ]
    if context_type == "database":
        return [
            "python process.py list-databases",
            "python process.py check-database rdp_16s_v18",
        ]
    if context_type == "results":
        return [
            "python process.py visualization-suite --output-root work",
            "python process.py generate-report --final-dir work\\06_final",
        ]
    if context_type == "differential":
        return [
            "python process.py differential-abundance --metadata metadata.txt --otu-table work\\06_final\\otutab.txt --comparisons KO:WT",
        ]
    return [
        "python process.py check-pipeline-config --params pipeline_params.webui.yaml",
        "python process.py run-pipeline-config --params pipeline_params.webui.yaml",
    ]


def _rule_based_explanation(request: AgentExplainRequest, *, mode: str = "rule_based") -> AgentExplainResponse:
    text = f"{request.context_type}\n{request.question}\n{request.technical_text}\n{request.project_summary}"
    zh = _is_zh(request)
    causes: list[str] = []
    steps: list[str] = []
    warnings: list[str] = []
    context = request.context_type

    if _contains(text, "metadata", "sampleid", "sample id", "group_col", "group column", "missing columns"):
        context = "metadata"
        causes.extend([
            "metadata 文件路径不正确，或文件无法读取。" if zh else "The metadata path is wrong or the file cannot be read.",
            "SampleID 或 Group 列名与实际表头不一致。" if zh else "The SampleID or Group column name does not match the actual header.",
            "样本 ID 可能存在重复、空值，或分组列存在空值。" if zh else "Sample IDs may be duplicated or empty, or group values may be missing.",
        ])
        steps.extend([
            "在“新建分析”的“输入文件”步骤重新选择 metadata，并确认 SampleID 列和 Group 列。" if zh else "In New Analysis, select the metadata file again and confirm the SampleID and Group columns.",
            "打开 metadata 第一行检查列名，避免隐藏空格、大小写不一致或不可见字符。" if zh else "Inspect the first metadata row for column-name spelling, hidden whitespace, and case mismatches.",
            "重新运行 metadata 检查，再继续 FASTQ 配对预览。" if zh else "Run metadata validation again before continuing to FASTQ pairing.",
        ])

    if _contains(text, "fastq", "read1", "read2", "missing_r1", "missing r1", "missing_r2", "paired"):
        context = "fastq"
        causes.extend([
            "FASTQ 文件夹路径不正确，或文件名后缀与设置不一致。" if zh else "The FASTQ folder path is wrong, or file suffixes do not match the settings.",
            "metadata 中的 SampleID 与 FASTQ 文件名前缀无法对应。" if zh else "Sample IDs in metadata do not match FASTQ filename prefixes.",
            "部分样本缺少 R1 或 R2 文件。" if zh else "Some samples are missing R1 or R2 files.",
        ])
        steps.extend([
            "确认 read1_suffix 和 read2_suffix 与真实文件名一致，例如 _1.fq.gz 和 _2.fq.gz。" if zh else "Confirm that read1_suffix and read2_suffix match real filenames, for example _1.fq.gz and _2.fq.gz.",
            "确保 metadata 的 SampleID 不包含 FASTQ 后缀，只保留样本名前缀。" if zh else "Keep metadata SampleID values as sample prefixes without FASTQ suffixes.",
            "重新运行 FASTQ 配对预览，确认 matched pairs 等于样本数。" if zh else "Run FASTQ pairing preview again and confirm matched pairs equals the sample count.",
        ])

    if _contains(text, "database", "fasta", "sintax", "rdp", "silva", "reference", "sha-256", "sha256"):
        context = "database"
        causes.extend([
            "数据库 FASTA 路径不存在，或 registry 记录仍指向旧位置。" if zh else "The database FASTA path is missing or the registry still points to an old location.",
            "annotation_database 或 reference_db 名称没有注册。" if zh else "annotation_database or reference_db is not registered.",
            "数据库文件被替换后，SHA-256 与 registry 中的记录不一致。" if zh else "The database file was replaced and its SHA-256 no longer matches the registry value.",
        ])
        steps.extend([
            "在“数据库”页面检查数据库状态；大型 FASTA 文件不需要默认计算 hash。" if zh else "Check database status on the Databases page; avoid hashing large files unless needed.",
            "如果文件移动过，请用当前 FASTA 位置重新注册数据库。" if zh else "If the file moved, register the database again with the current FASTA path.",
            "确认 taxonomy_format 与数据库格式匹配；SINTAX 数据库通常使用 sintax。" if zh else "Confirm taxonomy_format matches the database; SINTAX databases usually use sintax.",
        ])

    if _contains(text, "usearch", "vsearch", "executable", "not recognized", "no such file", "permission"):
        causes.extend([
            "USEARCH/VSEARCH 可执行文件路径未设置、不可执行，或没有加入 PATH。" if zh else "The USEARCH/VSEARCH executable path is unset, not executable, or not in PATH.",
            "Windows 路径包含空格或中文时，命令必须使用安全参数数组传递。" if zh else "Windows paths with spaces or non-ASCII characters must be passed as safe argument arrays.",
        ])
        steps.extend([
            "在“设置”中配置 usearch_path 或 vsearch_path，或在 pipeline 参数中显式填写。" if zh else "Set usearch_path or vsearch_path in Settings, or explicitly in pipeline params.",
            "先运行 preflight，不要直接启动 full analysis。" if zh else "Run preflight before starting the full analysis.",
        ])

    if _contains(text, "tree", "unifrac", "weighted_unifrac", "unweighted_unifrac"):
        causes.append(
            "UniFrac beta diversity 需要有效系统发育树；未提供 tree 时应使用非 UniFrac 距离。"
            if zh else
            "UniFrac beta diversity requires a valid phylogenetic tree; use non-UniFrac distances if no tree is available."
        )
        steps.append(
            "提供 beta_tree_path，或暂时使用 braycurtis、jaccard、euclidean 等距离。"
            if zh else
            "Provide beta_tree_path, or use distances such as braycurtis, jaccard, or euclidean."
        )

    if _contains(text, "differential", "comparison", "ko", "wt", "case", "control", "log2fc"):
        context = "differential"
        causes.extend([
            "差异比较需要明确 case/control 方向。" if zh else "Differential analysis requires an explicit case/control direction.",
            "某些组样本数过低会降低统计稳定性。" if zh else "Low group sample size reduces statistical stability.",
        ])
        steps.extend([
            "使用 CASE:CONTROL 格式定义比较，例如 KO:WT 表示 KO 相对 WT。" if zh else "Use CASE:CONTROL comparisons, for example KO:WT means KO relative to WT.",
            "检查 metadata 中每个比较组是否有足够样本数。" if zh else "Check that each compared group has an acceptable number of samples.",
        ])

    if _contains(text, "plot", "visualization", "06_final", "report", "index.html", "result"):
        context = "results"
        causes.extend([
            "完整 pipeline 尚未成功写入 work/06_final。" if zh else "The full pipeline has not successfully written work/06_final.",
            "可视化或 report 任务尚未运行，或输出路径与当前项目不一致。" if zh else "Visualization or report generation has not run, or output paths do not match the current project.",
        ])
        steps.extend([
            "先检查“运行监控”中最近任务是否 completed。" if zh else "First check whether the latest job is completed in Run Monitor.",
            "在“结果”页面刷新当前工作目录，或选择对应项目。" if zh else "Refresh the current workspace in Results or select the matching project.",
            "必要时重新运行 visualization-suite 和 generate-report。" if zh else "If needed, rerun visualization-suite and generate-report.",
        ])

    if not causes:
        causes.extend([
            "当前信息不足，最可能是路径、参数或依赖配置问题。" if zh else "The current context is limited; the most likely issue is path, parameter, or dependency configuration.",
            "需要查看 preflight log 或具体错误行才能准确定位。" if zh else "The preflight log or exact error line is needed for a precise diagnosis.",
        ])
        steps.extend([
            "复制“运行监控”中的 technical log 最后 50-100 行到本页面解释框。" if zh else "Paste the last 50-100 technical-log lines from Run Monitor into this help panel.",
            "先运行 check-pipeline-config，确认所有输入路径、数据库和外部工具可用。" if zh else "Run check-pipeline-config first to verify input paths, databases, and external tools.",
        ])

    title = "本地帮助建议" if zh else "Local Help Suggestion"
    summary = (
        "这是基于错误文本和当前上下文生成的规则化解释，不会执行任何命令。"
        if zh else
        "This is a rule-based explanation from the error text and context. No commands are executed."
    )
    if mode == "fallback":
        warnings.append(
            "LLM 调用失败，已回退到本地规则解释。" if zh else "The LLM call failed, so the response fell back to local rules."
        )

    return AgentExplainResponse(
        status="ok" if mode != "fallback" else "warning",
        mode=mode,  # type: ignore[arg-type]
        title=title,
        summary=summary,
        likely_causes=_unique(causes),
        recovery_steps=_unique(steps),
        commands=_commands_for_context(context),
        warnings=_unique(warnings),
    )


def _safe_json_response(text: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            loaded = json.loads(match.group(0))
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            return None


def _llm_explanation(request: AgentExplainRequest) -> AgentExplainResponse:
    config = AgentConfig()
    status = get_agent_status()
    if not status.llm_available:
        return _rule_based_explanation(request)

    from litellm import completion  # type: ignore[import-not-found]

    language = "Chinese" if request.language == "Chinese" else "English"
    system_prompt = (
        "You are the X-Amplicon Web UI help layer. Explain 16S amplicon "
        "pipeline errors and parameter choices. Never claim that you executed "
        "commands. Never recommend deleting files. Keep commands deterministic "
        "and reproducible. Return compact JSON with keys: title, summary, "
        "likely_causes, recovery_steps, commands, warnings."
    )
    user_prompt = {
        "language": language,
        "context_type": request.context_type,
        "question": request.question[:4000],
        "technical_text": request.technical_text[-8000:],
        "project_summary": request.project_summary[:4000],
    }

    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "api_key": config.api_key,
        "timeout": 30,
        "temperature": 0.2,
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = completion(**kwargs)
    content = str(response.choices[0].message.content or "")
    parsed = _safe_json_response(content)
    if not parsed:
        fallback = _rule_based_explanation(request, mode="fallback")
        fallback.raw_response = content[:4000]
        return fallback

    default_title = "LLM 解释" if language == "Chinese" else "LLM explanation"
    return AgentExplainResponse(
        status="ok",
        mode="llm",
        title=str(parsed.get("title") or default_title),
        summary=str(parsed.get("summary") or ""),
        likely_causes=[str(item) for item in parsed.get("likely_causes", []) if str(item).strip()],
        recovery_steps=[str(item) for item in parsed.get("recovery_steps", []) if str(item).strip()],
        commands=[str(item) for item in parsed.get("commands", []) if str(item).strip()],
        warnings=[str(item) for item in parsed.get("warnings", []) if str(item).strip()],
        raw_response=None,
    )


def explain_agent_issue(request: AgentExplainRequest) -> AgentExplainResponse:
    """Explain an issue using optional LLM assistance with deterministic fallback."""

    if not request.prefer_llm:
        return _rule_based_explanation(request)
    try:
        return _llm_explanation(request)
    except Exception as exc:
        fallback = _rule_based_explanation(request, mode="fallback")
        fallback.warnings.append(str(exc))
        return fallback
