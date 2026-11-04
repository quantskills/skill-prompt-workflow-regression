# 提示词与工作流稳定性回归测试

提示词改过一轮之后，旧任务是否仍然通过，结果是否更不稳定，成本是否上涨，可以用冻结任务集逐版比较。这套工具读取 EVO 的重复运行记录，核对模型和输入版本，再给出通过率、波动、成本和回滚建议。

已完成一轮 EVO 实测。原版、改写版与修订版分别在开发集上重复运行，修订版再经过保留集检验。故意破坏格式的版本被拦下后，已在独立 EVO 研究项目中恢复正常版本并复测。输入校验与独立重复检查也已完成 EVO 平台复验；这不等于负责人正式验收，也不是所有模型和任务的可靠性保证。

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

## 实际验证结果

2026 年 11 月在 EVO 完成一轮多版本实验。保留集含 6 项任务，每版进行三次独立批量调用，共得到 18 个任务评分。任务评分数不等于独立模型调用数。

| 检查项目 | 实际结果 |
|---|---|
| 原版严格格式检查 | 0 / 18 通过 |
| 修订版严格格式检查 | 18 / 18 通过 |
| 故意破坏格式的版本 | 0 / 18 通过，被拦下 |
| 独立 EVO 项目恢复正常版本后复测 | 6 / 6 通过 |

代码经过 Kimi-K3 两轮文件审查，25 项测试在 Windows Python 3.12、EVO Python 3.11 / Linux 和解压后的交付目录分别通过，零失败、零跳过。覆盖冻结清单、输入校验、重复调用识别、失败版本拦截、输出防覆盖和本地回滚。修订后重算的历史核心评分与结论完全一致。Kimi 用于代码审查，上表不能称为 Kimi 的任务通过率。

实测中遇到的平台中文检查问题及处理方式见[中文 JSON 约定](references/zh-json-contract.md)。这轮任务较窄、每组只有三次独立调用，结果不能外推为任意工作流的可靠性保证。

后续检查补上了token数量校验，小数、负数和布尔值会明确报错，不再自动取整。本地完整测试现为28项通过，原保留集重算结论不变。这次补丁尚未重新在EVO执行，前面的25项平台测试对应补丁前版本。

`assets/prompt-v3.txt` 保留了修订版提示词的原文，可作为中文 JSON 工作流的起点。换模型、任务或工具后仍要重新冻结并检验，不沿用本轮通过率。

## 适用范围

当前评分要求完整响应是合法 JSON，不自动剥除 Markdown 包裹或解释文字。平台会话核验按单轮调用设计，多轮对话和复杂工具链需要另加核验规则。

报告中的区间是任务级重抽样的描述性结果。任务数较少，一次调用内的任务也可能相关，不能把区间当成独立调用成功率的保证。

仓库不包含账户凭据、私人平台会话或模型思考过程。离线演示可直接复现，真实模型实验需自己的 EVO 授权。
