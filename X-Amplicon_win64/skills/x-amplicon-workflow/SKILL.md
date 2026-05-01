---
name: x-amplicon-workflow
description: Work with the X-Amplicon repository in either a quick-start mode or an advanced checked mode for the end-to-end 16S amplicon workflow from raw paired-end FASTQ to final otutab, taxonomy, alpha diversity, beta diversity, and taxonomy summaries.
---

# X-Amplicon Workflow

这个 skill 只负责模式规则和执行约束，不再重复 README 中的默认值、输出清单或参数事实。仓库事实源统一以 `README.md` 为准，快速模式最小上下文统一以 `AGENT_QUICKSTART.md` 为准。

## 模式选择

- 当用户明确要求“快速启动”“直接开始”“不要检查”“直接跑流程”时，使用 `快速模式`
- 当用户要求“先检查”“先确认参数”“详细解释过程/结果/结构”时，使用 `高级模式`
- 如果用户没有明确指定，默认使用 `高级模式`

## 共享规则

- 工作目录：`D:\16s_translate\X-Amplicon`
- 完整流程默认命令：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml
```

- CLI 原生预检查命令：

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
```

- 运行后优先读取 `output_root/06_final/run_summary.json`
- 不要在回复中手工复制 README 里的默认参数和输出清单；需要引用时直接引用 README 或 `run_summary.json`

## 快速模式

只读取最少上下文：

1. `AGENT_QUICKSTART.md`
2. `pipeline_params.yaml`

执行规则：

1. 不主动做依赖、数据库、输入文件、样本匹配、参数一致性预检查
2. 不在开始前列检查清单，也不因为常规不确定项反复等待确认
3. 直接基于现有 `pipeline_params.yaml` 启动用户要求的流程或子命令
4. 如果运行报错，只针对当前阻塞错误做最小定位、修复或说明
5. 输出说明保持精简，优先报告成功/失败、`run_summary.json`、关键结果目录和阻塞原因
6. 只有在快速模式无法回答的问题确实需要更多背景时，才回看 `README.md`

## 高级模式

先做 CLI 原生检查，再进入耗时流程：

1. `README.md`
2. `pipeline_params.yaml`
3. `AGENT_QUICKSTART.md`

执行规则：

1. 在正式运行前，先执行 `check-pipeline-config` 或 `run-pipeline-config --check-only`
2. 预检查以 CLI 输出为准，不再手工重写同一套检查逻辑
3. 运行前说明任务理解、关键生效参数、待确认项，以及检查结论
4. 如果预检查发现明显阻塞问题，先报告问题，再决定是否继续执行
5. 运行后优先依据 `run_summary.json` 说明实际步骤、跳过步骤、关键输出和失败步骤
6. 可以补充适度解释，但不要夸大生物学结论
