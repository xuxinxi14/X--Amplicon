# X-Amplicon 提示词模板

这里保留两类模板：

- `快速模式`：不预检查，直接启动，解释尽量精简
- `高级模式`：先用 CLI 做预检查，再决定是否开跑

默认事实源在 `README.md`，快速模式最小上下文在 `AGENT_QUICKSTART.md`。这里不再重复默认参数值、默认输出清单或完整流程事实。

## 快速模式模板

```text
请按“快速模式”处理这个 X-Amplicon 仓库任务。

工作目录：
D:\16s_translate\X-Amplicon

先只阅读以下最少文件，不要扩大阅读范围：
1. AGENT_QUICKSTART.md
2. pipeline_params.yaml

执行要求：
1. 不要先做依赖、数据库、输入文件、样本匹配、参数一致性预检查
2. 不要在开始前列检查清单，也不要等待我二次确认
3. 直接基于当前 pipeline_params.yaml 开始执行
4. 如果要跑完整流程，优先使用：
   & .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml
   如果完整流程完成后还要生成标准图表，使用：
   & .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite --final-dir work\06_final --format html
5. 如果运行报错，再只针对当前阻塞错误做最小定位和处理
6. 结果汇报保持精简，只需要告诉我：
   - 是否成功启动或成功完成
   - run_summary.json 在哪里
   - 如果本次任务要求可视化，`work/06_final/plots` 下生成了哪些图表目录
   - 当前失败步骤和阻塞原因
7. 除非我继续追问，不要主动展开流程原理、参数含义或结果解释
8. 除非我明确允许，不要做与当前任务无关的代码或文档修改

本次任务目标：
[在这里填写目标]

本次允许范围：
[例如“直接跑完整流程但不改代码”或“直接跑流程，必要时允许最小修复”]

输入文件或目录：
[如需覆盖当前参数文件中的路径，在这里说明]

期望输出：
[在这里填写结果文件、目录或比较对象]

开始后直接执行，不需要先向我复述任务或列出待确认项。
```

## 高级模式通用模板

```text
请按“高级模式”处理这个 X-Amplicon 仓库任务。

工作目录：
D:\16s_translate\X-Amplicon

请先阅读并理解这些文件：
1. README.md
2. pipeline_params.yaml
3. AGENT_QUICKSTART.md

执行要求：
1. 在开始耗时步骤前，先使用 CLI 做预检查：
   & .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
   或
   & .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml --check-only
2. 预检查结论以 CLI 输出为准，不要再手工复制一份检查逻辑
3. 开始执行前，先说明：
   - 你对任务的理解
   - 已检查出的关键生效参数
   - 当前仍需确认的前提
4. 如果预检查通过且任务要求完整流程，优先使用：
   & .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml
   如果任务要求可视化，完整流程成功后再使用：
   & .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite --final-dir work\06_final --format html
5. 结果汇报要比快速模式更详细，但优先依据 run_summary.json 说明：
   - 实际执行了哪些步骤
   - 哪些步骤被跳过
   - 关键输出目录和文件
   - 如果生成了可视化，列出 `work/06_final/plots` 下的图表子目录和代表性文件
   - 若失败，失败步骤和阻塞原因
6. 如果发现差异、异常或缺失，先定位原因，再决定是否继续修改
7. 只修改与当前任务直接相关的代码或文档

本次任务目标：
[在这里填写你的目标]

本次允许范围：
[例如“只读代码并报告参数”、“先检查再跑完整流程”、“只测试 taxonomy-summary”]

输入文件或目录如下：
[在这里填写输入路径]

期望输出如下：
[在这里填写输出文件、目录或比较对象]

成功标准如下：
[在这里填写成功标准]
```

## 高级模式完整流程模板

```text
请按“高级模式”完成一次 X-Amplicon 完整流程检查，并在检查完成后再决定是否开跑。

工作目录：
D:\16s_translate\X-Amplicon

请先阅读：
1. README.md
2. pipeline_params.yaml
3. AGENT_QUICKSTART.md

要求：
1. 使用 .\.tools\python-3.13.13-amd64\python.exe
2. 先执行：
   & .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
3. 汇报中列出：
   - CLI 预检查是否通过
   - 关键生效参数
   - 如果继续运行，最终会把结果写到哪里
   - 如果运行完成，后续应优先读取哪个 run_summary.json
4. 在我确认前，不要真正运行流程
5. 如果我要求生成图表，完整流程成功后再调用 `process.py visualization-suite` 或 Agent 可视化工具，将图表写入 `work/06_final/plots` 的分类子目录
```

## 高级模式单模块模板

```text
请按“高级模式”测试这个 X-Amplicon 模块。

工作目录：
D:\16s_translate\X-Amplicon

请先阅读以下文件：
1. README.md
2. [在这里填写模块路径]
3. 与该模块直接相关的测试文件或标准输出文件

要求：
1. 先完整读取模块源代码
2. 先说明这个模块的功能、输入、输出和关键限制
3. 再说明你准备如何测试
4. 使用 .\.tools\python-3.13.13-amd64\python.exe 执行测试
5. 报告测试结果、差异和必要修改
6. 只修改与这个模块直接相关的代码
```
