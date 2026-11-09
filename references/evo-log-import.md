# 导入已保存的 EVO 原始日志

手里已有 EVO 原始消息流时，可以直接生成评分入口要读的文件，不必手填每道题的回答、费用和 token。导入与评分都在本机完成，不联网、不登录，也不会在 EVO 上重跑或切换版本。

## 准备文件

- 先固定 `suite.json`、`manifest.json`、`versions.json`。新旧两版各放一份 `版本名.txt`，文件原始字节的 SHA256 必须和 `versions.json` 中的对应值一致。
- 保存每次调用的原始 EVO 消息流。支持一行一个 JSON 对象、外层为 `direction` 和 `message` 的采集格式；保留一个 `input` 用户消息和原有的 `output` 事件。需要会话开始、实际生效的模型选项和带 `cost.usd`、`cost.tokens` 的结束事件。普通聊天 Markdown、截图或手抄答案不能当成这种日志。
- 如能另外从平台取得会话回读，把每份放成 `会话编号.json`。程序逐份核对会话、项目、模型、用户输入、回合编号和最终回答。没有回读也可以导入，审计会标为未提供或未找到。回读和原日志冲突时停止。
- 建一个 `index.json`，给本次要比较的每次调用填一行。索引只负责把文件指向冻结版本和重复编号，不填评分或改回答。以下只演示一行，新旧版都要按冻结次数提供完整的独立会话。耗时是采集时记下的整次调用秒数，不能把它当作逐题延迟。

```json
[
  {"session_id":"qs-example","protocol_file":"capture-example.jsonl","version":"v1","repeat":0,"elapsed_seconds":18.4}
]
```

目前支持单轮批量 JSON 任务，无附件、无引用。发送时使用同一前缀、冻结任务和对应版本指令，要求最终返回 `{"responses":[{"task_id":"题号","output":{}}]}`。原输入文本要和冻结内容逐字匹配。新建任务时可用下列短脚本生成要发送的文本，只把输出的请求交给被测模型，不发送评分规则。

```python
import json
from pathlib import Path
import sys

sys.path.insert(0, "scripts")
from import_evo import DEFAULT_PREFIX, request_text

suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
tasks = [task for task in suite["tasks"] if task["split"] == "holdout"]
prompt = Path("prompts/v1.txt").read_bytes().decode("utf-8")
sys.stdout.write(request_text(tasks, prompt, DEFAULT_PREFIX))
```

如需自定前缀，两版必须用同一句；生成请求和导入时都传入同一前缀（导入用 `--request-prefix`）。每批把全部冻结题交给同一个新会话。不要复制一次调用来凑重复，也不要把别的格式手工改成看起来像 EVO 原始事件的文件。

## 导入并评分

在项目目录安装好[依赖](getting-started.md#1-检查环境)后运行。没有会话回读时删掉 `--receipts-dir` 那一项，其他输入不能省略。

```powershell
.venv\Scripts\python scripts/import_evo.py --project "你的项目编号" --suite suite.json --manifest manifest.json --versions versions.json --index index.json --prompts-dir prompts --protocol-dir wire --receipts-dir receipts --split holdout --output "outputs/evo-input"
.venv\Scripts\python start.py --run --input-dir "outputs/evo-input" --output "outputs/evo-score"
```

这两条命令都要求新的输出目录。导入可选 `development`，但上面简易评分入口只评保留集；评开发集请用[评分命令](../SKILL.md)指定 `--split development`。

先看 `outputs/evo-input/evo-import-audit.json`，每次调用都有原始文件校验值、回读状态和计费读数。再打开 `outputs/evo-score/使用结果.md`，从 `run_scores.csv` 的运行编号查回导入审计和本地原始文件。整批美元费用均摊，整数 token 按题序分余数，批次总额不重复计算。USD 是日志里的费用读数，不能拿来核对钱包或算力扣款。

有重写时只读标为最终回答的片段。最终输出有围栏、额外文字、缺题或重复题时，不修补，不丢弃整批记录。已结束但格式不合格会记为评分失败；明确中断且仍有结束事件与费用记录的调用保留为执行失败。如果没有终止或计费记录，导入停止，不猜填零。只有会话输入能核对而最终回答无法核对时，审计也会单独标出。

## 用真实日志复跑的结果

本版使用先前保存的 EVO 量化输入检查工作流，覆盖下单手数、信息时点、参数缺项和双边成本。导入的是 v1 和 v3 各三次真实保留集调用，每次六题，共 36 条逐题记录。没有重新调用模型，也没有更改原来的题、规则或版本。旧版 0/18，新版 18/18，推荐 v3，与原冻结评分一致。这个小样本只说明这批任务的结果。

六份独立会话回读均核对一致，包括最终回答文本。原始消息流的费用合计为 0.6154 美元、176,759 tokens。这套任务没有执行外部工具，因此没有原生工具执行回执可核对，也不证明工具调用隔离或平台生产可靠性。评分报告仍不会自动标为平台已验收。原始消息、回读和索引留在本地，不随 GitHub 或公开包发布。
