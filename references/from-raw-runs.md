# 从原始运行记录找出退步的题

这次比较两版提取提示词。旧版叫 `baseline`，精简后的新版叫 `short`。我们想知道，发票月份还能不能提对，订单号里的前导零还在不在。

[完整样例](../examples/from-raw/)自带任务、两个版本的定义和原始记录。记录是构造的，可以离线跑；它演示怎么核对结果，不代表某个真实模型的表现。已有平台原始消息流时，可改走[EVO 日志导入](evo-log-import.md)。命令都从能看到 `start.py` 的项目目录运行，依赖按[入门说明](getting-started.md#1-检查环境)安装。

## 1. 先定题和规则

打开[任务集](../examples/from-raw/suite.json)。`dev-format` 是用来试改动的开发题，另两题标成 `holdout`，留到新旧版本定下来之后再比较。比如订单号题要求 `order_id` 是字符串，且内容恰好为 `0041`。数字 `41` 即使看起来是同一个号码，也会丢掉两位前导零。

先运行下面这行，把任务和版本定下来。它会创建 `outputs/records-walkthrough`，复制 `suite.json`，并写出记录任务指纹的 `manifest.json` 和记录新旧版本指纹的 `versions.json`。版本指纹由[提示词和工作流定义](../examples/from-raw/versions/)计算。

```powershell
.venv\Scripts\python examples/from-raw/prepare.py lock --work-dir "outputs/records-walkthrough"
```

自己做实验时，先用开发题改提示词，把最终要比的两版和规则记下来，再收集保留题的回答。标准答案和评分规则留给评分工具，不发给被测模型。样例为了方便复跑已随包提供全部记录。

## 2. 把原始记录整理成一行一次运行

[原始记录](../examples/from-raw/raw-runs.jsonl)里，每行有一道题的一次运行。新旧版用同一个模型和同一组采样设置，各跑三次，次数从 `0` 编到 `2`。样例里的 `fixture:` 编号只标记离线样本。用自己的记录时，应使用真实运行编号，保留原始导出和计费凭据，不把一次运行复制成三次。

样例整理脚本先把原始输入和定好的题逐条核对，再按下表整理。你自己的导出列名可能不同，按右栏准备即可。

| 原始记录 | 写入 `runs.jsonl` |
| --- | --- |
| `id`、`task`、`variant`、`attempt` | 唯一的 `run_id`，以及 `task_id`、`version`、整数 `repeat`。另保留真实平台调用编号 `platform_run_id` |
| `model`、`parameters` | `model`、`model_parameters`，照录实际使用的设置 |
| `input` 与版本定义 | 先核对实际输入和版本，再从冻结文件取 `task_hash`、`version_hash` |
| `state`、`final_text` | `status`、`response`。保留原始最终回答，包括多余文字或错误字段；超时保留 `failed`，没有最终回答时留空 |
| `usage`、`elapsed_seconds` | `cost`、整数 `tokens` 和 `latency_seconds`。费用要统一单位，耗时用秒 |

以新版订单号题的第 2 次运行（`repeat=1`）为例，原始回答是 `{"order_id":41}`。整理后，`response` 仍是一段原样保留的文本。下一次超时记录也会写入，不会删掉或补成答对。错误详情可回到原始记录看 `error`。

```powershell
.venv\Scripts\python examples/from-raw/prepare.py pack --work-dir "outputs/records-walkthrough"
```

运行后目录中会多出 `runs.jsonl`。这个脚本只整理随包提供的样例格式，不连接平台，也不接管你的导出。整理真实记录时可对照[数据协议](data-contract.md)和[平台运行说明](platform-run.md)。

## 3. 跑比较，再回查原始回答

```powershell
.venv\Scripts\python start.py --run --input-dir "outputs/records-walkthrough" --output "outputs/records-walkthrough-result"
```

打开结果目录里的 `使用结果.md`。这次只评两道保留题，旧版通过 6 次，新版通过 4 次，通过率下降 **33.33 个百分点**，建议继续用 `baseline`。若要重跑，给整理目录和结果目录都换个新名字。

接着从 `使用结果.md` 打开同目录的 `run_scores.csv`，按 `task_id` 把同一题的新旧两版放在一起看。

| 题目 | 旧版通过 | 新版通过 | 怎么判断 |
| --- | --- | --- | --- |
| `invoice-month` | 3/3 | 3/3 | 这道题在样例里没有退步 |
| `order-id` | 3/3 | 1/3 | 先查第 2 次的类型和值，再查第 3 次的执行失败 |

`order-id` 的第 2 次有 `wrong_exact_json` 和 `wrong_type`。把这行的 `platform_run_id` 拿回原始记录查，能看到返回的是数字 `41`。第 3 次的 `execution_failed` 则对应原始记录里的超时。前者要查提取和格式要求，后者先查执行日志，别混成同一个问题。修订时先在开发题上验证，下一次正式比较再留一批没看过的题。
