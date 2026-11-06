# 提示词与工作流稳定性回归测试

这套工具用来比较提示词修改前后的实际表现。先固定任务和检查标准，再核对重复运行的答案、工具参数、失败处理和成本。它不会替模型执行真实任务，也不会凭模型一句“已完成”判定通过。

**v7 是本地交付版。** 下面三组是用冻结的合成数据在本机实际跑出来的结果。v7 没有在 EVO 上执行这三组任务，也没有调用 DS-V4-Pro 或取得平台原始回执。以前的 EVO 实验仅供查阅，不能算作 v7 的平台验收。

## v7 三组本地实跑

| 任务 | 人民币折算合计 | 重复业务编号 | 缺失数量的业务编号 |
| --- | --- | --- | --- |
| `fixed-v7-1` | 20.454 元 | `0007` | `0040` |
| `fixed-v7-2` | 49.25 元 | `0030` | `0002` |
| `fixed-v7-3` | 35.11125 元 | `0101` | `0105` |

三组金额都和独立预期一致，业务编号的前导零也保留了。每组读表记录都有五次调用，其中包括库存读取预设超时后的一次重试，以及受限表的一次拒绝。拒绝由合成测试模拟，不证明平台有文件隔离。本地完整测试 141 项通过。

## 复现这三组

用 Python 3.11 或更新版本即可，不需要安装额外依赖、登录平台或联网。把 [v7 本地复现材料](assets/v7-local-replay.zip) 解压到新目录，然后在该目录运行下面的 PowerShell 命令。重新跑时请换一个新目录，避免覆盖已有结果。

```powershell
python -X utf8 qs_prepare_v7.py
if ($LASTEXITCODE) { throw '准备失败' }
foreach ($i in 1..3) {
    python -X utf8 "fixed-v7-$i/solve.py"
    if ($LASTEXITCODE) { throw "第 $i 组执行失败" }
}
python -X utf8 qs_collect_v7.py
if ($LASTEXITCODE) { throw '收集结果失败' }
python -X utf8 verify_results.py --download fixed-v7-results.zip
```

最后应看到三行 `verified`。每组的详细结果在各自的 `output/result.json`，汇总包是刚生成的 `fixed-v7-results.zip`。复现材料另附此前本机生成的 `v7-local-observed-results.zip`，可和新结果对照。两个包都是本地结果，没有平台回执。

要跑完整演示或评价自己的数据，先看[三步入门](references/getting-started.md)。金额和读表规则见[固定文件流程](references/fixed-file-workflow.md)。[正式评分与模型审查](references/assessment.md)是可选步骤。

## 先跑一个例子

需要 Python 3.11 或以上。下载仓库后，在仓库目录打开终端，建立独立环境，运行无需模型密钥的合成演示。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts/demo.py --output outputs/demo-01
```

macOS / Linux 将 `.venv\Scripts\python` 换成 `.venv/bin/python`。演示生成任务集、冻结清单、虚构运行记录和报告，故意让候选版本失败，并把本地指针恢复到基线。查看 `outputs/demo-01/evaluation/report.json` 与 `state.json`。所有记录标有 `fixture:`，没有调用模型，也不能用作平台证据。

## 测试自己的提示词

先按[数据协议](references/data-contract.md)准备任务、版本与运行记录，在同一个独立环境中执行以下命令。

```powershell
.venv\Scripts\python scripts/regression.py freeze --suite suite.json --manifest manifest.json
.venv\Scripts\python scripts/regression.py evaluate --suite suite.json --manifest manifest.json --versions versions.json --runs runs.jsonl --split development --output outputs/development
.venv\Scripts\python -m pytest tests -q
```

开发完成后先冻结候选版本，再统一评价保留集。使用 `--split holdout`，如需更新本地版本指针可添加 `--local-state state.json`。

输出包括 `report.json` 和逐次评分 `run_scores.csv`。输入字段见[数据协议](references/data-contract.md)，真实平台复跑和回滚见[运行说明](references/platform-run.md)。

每次评价使用新的输出目录，程序不会覆盖已有目录。冻结清单只允许原样复用；修改任务、量规或模型后，应建立新版本。不要把已看过结果的保留题反复当成未见测试。

`requirements.txt` 固定的独立安装依赖为 NumPy 2.2.6、pandas 2.3.1、pytest 9.0.2、PyYAML 6.0.3。EVO 已有环境分别为 1.26.4、2.3.3、9.1.1、6.0.3。两组分别验证，平台无需更换全局依赖。

默认要求候选通过率至少 90%，同时检查相对退化和成本。如果候选与基线都不合格，会阻止放行。`--local-state` 只改本地记录，不会操作 EVO 项目。

`assets/task-suite.draft.json` 提供 12 项量化工作流任务，开发集和保留集各 6 项。先确认 EVO 的实际模型版本与参数，再复制为正式任务集并冻结。`prompt-v1.txt` 为基线，`prompt-v2.txt` 为开发候选，`prompt-negative-control.txt` 是预先定义的输出格式破坏样例。正式实验前需冻结三个版本的散列，保留集不用于反复调优。

## 历史 EVO 验证记录

本节记录的是旧版本的实验。两轮较近的工具行为记录见 [DS-V4-Pro 固定流程](references/evo-fixed-workflow-20261105.md)和 [Kimi-K3 文件读取边界](references/kimi-provenance-20261105.md)，其中保留了计算修正、工具调用错误和原始回执缺口。

2026 年 11 月在 EVO 完成一轮多版本实验。保留集含 6 项任务，每版进行三次独立批量调用，共得到 18 个任务评分。任务评分数不等于独立模型调用数。

| 检查项目 | 实际结果 |
|---|---|
| 原版严格格式检查 | 0 / 18 通过 |
| 修订版严格格式检查 | 18 / 18 通过 |
| 故意破坏格式的版本 | 0 / 18 通过，被拦下 |
| 独立 EVO 项目恢复正常版本后复测 | 6 / 6 通过 |

代码经过 Kimi-K3 两轮文件审查，25 项测试在 Windows Python 3.12、EVO Python 3.11 / Linux 和解压后的交付目录分别通过，零失败、零跳过。覆盖冻结清单、输入校验、重复调用识别、失败版本拦截、输出防覆盖和本地回滚。修订后重算的历史核心评分与结论完全一致。Kimi 用于代码审查，上表不能称为 Kimi 的任务通过率。

实测中遇到的平台中文检查问题及处理方式见[中文 JSON 约定](references/zh-json-contract.md)。这轮任务较窄、每组只有三次独立调用，结果不能外推为任意工作流的可靠性保证。

后续检查补上了 token 数量校验，并新增语义错误、工具参数和失败恢复检查。Kimi 审查后又补严了重复编号及次数校验，防止布尔值、小数被当成整数。最终56项测试在本地、解压目录和EVO均通过，两个环境的离线示例也正常完成。新增 v2 规则可核对完整答案和嵌套参数，区分布尔值与数值，拦截缺失或多余字段；失败的运行明确记录原因，不能因答案内容正确就放行。写法见[语义与恢复检查](references/semantic-workflow-tests.md)。原保留集核心结果重算不变。

新增故障用例是人工构造的检查器测试，不能用于推断模型在真实工具链上的成功率。历史 v1 规则和已看过的保留集没有改写。旧版的软件复验详见[历史复验记录](references/revalidation-r3.md)。

`assets/prompt-v3.txt` 保留了修订版提示词的原文，可作为中文 JSON 工作流的起点。换模型、任务或工具后仍要重新冻结并检验，不沿用本轮通过率。

## 适用范围

当前评分要求完整响应是合法 JSON，不自动剥除 Markdown 包裹或解释文字。平台会话核验按单轮调用设计，多轮对话和复杂工具链需要另加核验规则。

报告中的区间是任务级重抽样的描述性结果。任务数较少，一次调用内的任务也可能相关，不能把区间当成独立调用成功率的保证。

仓库不包含账户凭据、私人平台会话或模型思考过程。离线演示可直接复现，真实模型实验需自己的 EVO 授权。
