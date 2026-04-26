# X-Amplicon Visualization Agent Integration - Project Constitution

## 项目概述

我们正在将 `visualization/` 目录下的现有 16S 扩增子分析可视化程序，**完全按照 `src/core/` 的代码风格重构**，并封装为标准的 Agent 可调用工具，接入现有的 16S 分析 Agent 工作流，最终将所有生成的图表按类型输出到 `work/06_final/plots/` 的子目录下。

### 当前状态

- 已有完整的 16S 分析 Agent 系统，核心分析工具在 `src/core/`，Agent 逻辑在 `agent/`
- `visualization/` 目录下有可运行的 16S 可视化程序，但代码风格、接口格式与 `src/core/` 不统一
- 核心分析结果已稳定输出到 `work/06_final/`，图表需直接对接该目录的输入文件
- 标准可视化输出默认写入 `work/06_final/plots/`，并按图表类型分成独立子目录，避免所有图表混在同一目录

### 最终目标

1. 重构 `visualization/` 下的所有程序，使其**100%符合 `src/core/` 的代码规范**
2. 为每个可视化功能生成标准的 OpenAI-compatible Function Calling 定义
3. 将所有可视化工具注册到 `agent/tools.py`，Agent 可自主调用或响应用户自然语言请求生成图表
4. 所有图表默认输出到 `work/06_final/plots/` 的分类子目录，支持自定义输出路径
5. 完全保留 `src/core/` 和 `agent/` 下的原有逻辑，不做任何破坏性修改

---

## 核心技术栈

- **语言**: Python 3.10+（严格使用仓库内 `.tools/python-3.13.13-amd64/python.exe`）
- **可视化库**: 默认使用 `plotly` 生成离线 HTML 图表；静态 `png`/`pdf` 导出依赖 `kaleido`；所有输出必须支持无界面运行
- **数据验证**: Pydantic（用于定义工具 Schema）
- **Agent 集成**: 复用现有 `agent/config.py`, `agent/tools.py`, `agent/agent.py` 的架构

---

## 任务优先级 (P0 = 必须做, P1 = 应该做, P2 = 可选做)

### P0: 核心重构与集成

1. **探索与梳理**: 先完整探索 `visualization/` 目录，列出所有可运行的可视化程序及其功能、输入输出要求
2. **代码风格重构**: 将所有程序**完全迁移到 `src/core/` 风格**：
    - 每个独立可视化功能封装为独立的 `.py` 文件，放在 `src/core/` 下（命名规则：`viz_*.py`，如 `viz_alpha_diversity.py`）
    - 所有函数必须有**现代类型提示**（含 `|` 联合语法）
    - 所有公共 API 函数必须有**完整的 Google 风格 docstring**（含 `Args:`, `Returns:`, `Raises:` 部分）
    - 输入验证使用 `pydantic` 或清晰的异常抛出
    - 公共 API 函数与私有 `_helpers` 函数明确分离
    - 所有图表必须支持无界面运行，默认输出离线 HTML，静态导出不得依赖 GUI 后端
3. **工具注册**: 更新 `agent/tools.py`，自动发现并注册 `src/core/viz_*.py` 下的所有公共 API 函数，生成标准的 OpenAI-compatible JSON Schema
4. **输出路径约束**: 所有可视化工具的默认输出路径必须为 `work/06_final/plots/` 下的分类子目录，自动创建不存在的目录，支持用户通过参数自定义输出路径

### P1: 增强与优化

1. **图表质量优化**: 统一图表风格（字体、配色、布局），默认保存为交互式 HTML；按需支持 PNG/PDF 静态导出
2. **Agent 提示词优化**: 在 `agent/agent.py` 的系统提示词中补充可视化相关的上下文，让 Agent 知道在什么情况下应该自动生成什么图表
3. **结果预览**: 保留并增强 Agent 的结果预览功能，生成图表后自动显示图表的文件路径和简要说明

### P2: 可选功能

1. **批量可视化**: 增加一个批量生成所有常见 16S 分析图表的公共 API 函数
2. **交互式图表**: 默认支持生成 `plotly` 交互式图表，保存为 HTML 文件

---

## 代码规范

### 严格遵循 `src/core/` 的现有规范

1. **文件命名**: 所有可视化工具文件以 `viz_` 开头，小写字母，下划线分隔
2. **函数命名**: 公共 API 函数使用小写字母，下划线分隔；私有 `_helpers` 函数以下划线开头
3. **类型提示**: 所有函数必须有完整的类型提示，包括参数、返回值、局部变量（如需要）
4. **Docstrings**: 所有公共 API 函数必须有完整的 Google 风格 docstring，示例如下：

    ```python
    def plot_alpha_boxplots(
        alpha_diversity_path: str,
        metadata_path: str | None = None,
        output_dir: str = "work/06_final/plots/alpha_boxplot_chart",
        sample_id_col: str = "SampleID",
        group_col: str = "Group",
        output_format: str = "html",
    ) -> list[str]:
        """
        Plot alpha diversity boxplots.

        Args:
            alpha_diversity_path: Path to alpha_diversity.tsv.
            metadata_path: Optional metadata table used for grouping.
            output_dir: Directory to save plots. Defaults to the alpha boxplot subdirectory.
            sample_id_col: Metadata column containing sample IDs.
            group_col: Metadata column containing group labels.
            output_format: html, png, pdf, or all. Static formats require kaleido.

        Returns:
            List of paths to the generated plot files.

        Raises:
            FileNotFoundError: If required input files are missing.
            ValueError: If input tables cannot be parsed or matched.
        """
    ```

5. **输入验证**: 使用清晰的异常抛出或 `pydantic` 模型进行输入验证
6. **无界面运行**: 可视化工具不能依赖 GUI 后端；默认 HTML 输出应可在无界面环境中生成
7. **目录创建**: 所有可视化工具必须自动创建不存在的输出目录，使用 `os.makedirs(output_dir, exist_ok=True)`

---

## 文件结构约束

```text
project_root/
├── src/core/              # 保持原有分析工具不变，新增可视化工具
│   ├── alpha_diversity.py
│   ├── beta_diversity.py
│   ├── ...
│   ├── viz_alpha_diversity.py  # 新增：重构后的alpha多样性可视化
│   ├── viz_beta_diversity.py   # 新增：重构后的beta多样性可视化
│   ├── viz_taxonomy.py         # 新增：重构后的物种分类可视化
│   └── ...
├── agent/                 # 保持原有架构不变，仅更新 tools.py
│   ├── __init__.py
│   ├── config.py
│   ├── tools.py          # 更新：自动发现并注册 src/core/viz_*.py 下的工具
│   ├── state.py
│   └── agent.py          # 可选：补充可视化相关的系统提示词
├── visualization/         # 保留原目录作为备份，不删除
├── work/06_final/
│   ├── otutab.txt
│   ├── otutab_rare.txt
│   ├── ...
│   └── plots/            # 新增：所有可视化工具的默认输出目录
│       ├── alpha_boxplot_chart/
│       ├── alpha_barplot_chart/
│       ├── alpha_rare_chart/
│       ├── beta_pcoa_chart/
│       ├── beta_cpcoa_chart/
│       ├── beta_heatmap_chart/
│       ├── taxonomy_stacked_bar_chart/
│       └── taxonomy_heatmap_chart/
├── agent_cli.py          # 保持不变
├── process.py            # 保持不变
└── CLAUDE.md             # 本文件
```

---

## 非谈判性约束

1. **DO NOT MODIFY ANY CODE IN THE `src/core/` DIRECTORY EXCEPT FOR NEWLY ADDED `viz_*.py` FILES**：绝对不能修改原有的分析工具代码
2. **DO NOT MODIFY ANY CODE IN THE `agent/` DIRECTORY EXCEPT FOR `agent/tools.py` AND OPTIONALLY `agent/agent.py`'S SYSTEM PROMPT**：绝对不能修改 Agent 的核心循环、状态管理、配置加载等逻辑
3. **STRICTLY USE THE WAREHOUSE-INCLUDED PYTHON INTERPRETER**: 所有代码必须使用 `.tools/python-3.13.13-amd64/python.exe` 运行，不能使用系统 Python
4. **ALL PLOTS MUST DEFAULT TO `work/06_final/plots/` SUBDIRECTORIES**: 所有可视化工具的默认输出路径必须是该目录下的分类子目录，自动创建不存在的目录
5. **ALL PLOTS MUST SUPPORT HEADLESS EXECUTION**: 必须支持无界面运行，不能依赖 GUI 后端

---

## 后续维护

后续维护时，先以 `README.md` 和 `AGENT_QUICKSTART.md` 为当前事实源；修改可视化实现后，同步更新 `PROMPT_TEMPLATE.md`、本文件和相关测试，确保 Agent 的自然语言说明、工具接口和实际输出目录保持一致。
