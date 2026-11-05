# 提示词与工作流稳定性回归测试

这套工具用来比较提示词修改前后的实际表现。先固定任务和检查标准，再核对重复运行的答案、工具参数、失败处理和成本。它不会替模型执行真实任务，也不会凭模型一句“已完成”判定通过。

最新三轮 Kimi-K3 实际任务已执行并取回原包。三轮计算结果正确，但第三轮中断恢复后读取了第二轮脚本，违反本轮文件白名单，完整行为验收失败。回执编号和状态与平台显示一致，未知退出码都留空；完整原始响应尚未独立导出，不能宣称来源字段全部核验通过。过程见[新版三轮复验](references/kimi-provenance-20261105.md)。当前仍按研究工具使用，不保证模型遵守访问边界，不建议用提示词约定独自保护敏感文件。

新增[回执核对工具](references/receipt-validation.md)，用于逐字段比较独立保存的运行证据。软件测试通过只说明检查器按规则工作，不能抵消模型实际执行中的失败。

已在 EVO 通过 70 项软件测试及中文演示，见[平台复验记录](references/evo-recovery-20261105.md)。此前的 [Kimi 文件任务实测](references/kimi-file-workflow-20261105.md)暴露了越界读取问题。补上[文件任务执行约定](references/execution-contract.md)后，用三组新会话复验，三组结果都算对，未观察到越界读取或猜填运行状态；第二组回执缺少来源标注，完整要求只满足了两组。第二、三组都经历了平台中断和原会话续跑，不能称为三次一次性成功。详细过程和原包摘要见[读取边界与回执复验](references/kimi-boundary-20261105.md)。

首次使用先看[三步入门](references/getting-started.md)：运行 `python start.py --check` 检查环境，`python start.py` 打开中文菜单。准备好依赖后，运行 `python start.py --demo --output outputs/first-demo`，打开结果目录里的 `使用结果.md`。每次使用新目录；示例是合成数据，不证明真实效果。

自己的数据统一放进一个文件夹，再运行 `python start.py --run --input-dir "我的输入" --output "outputs/我的结果"`。所需文件与准备步骤见入门说明。以下保留原始命令和历史研究记录，供进一步使用；[正式评分与模型审查](references/assessment.md)均为可选，不阻止普通使用。

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

后续检查补上了 token 数量校验，并新增语义错误、工具参数和失败恢复检查。Kimi 审查后又补严了重复编号及次数校验，防止布尔值、小数被当成整数。最终56项测试在本地、解压目录和EVO均通过，两个环境的离线示例也正常完成。新增 v2 规则可核对完整答案和嵌套参数，区分布尔值与数值，拦截缺失或多余字段；失败的运行明确记录原因，不能因答案内容正确就放行。写法见[语义与恢复检查](references/semantic-workflow-tests.md)。原保留集核心结果重算不变。

新增故障用例是人工构造的检查器测试，不是模型在真实工具链上的成功率。历史 v1 规则和已看过的保留集没有改写。最新版 EVO 复验记录见[本轮验证](references/revalidation-r3.md)，不要把此前 25 项平台测试当成最新版的全量结果。

`assets/prompt-v3.txt` 保留了修订版提示词的原文，可作为中文 JSON 工作流的起点。换模型、任务或工具后仍要重新冻结并检验，不沿用本轮通过率。

## 适用范围

当前评分要求完整响应是合法 JSON，不自动剥除 Markdown 包裹或解释文字。平台会话核验按单轮调用设计，多轮对话和复杂工具链需要另加核验规则。

报告中的区间是任务级重抽样的描述性结果。任务数较少，一次调用内的任务也可能相关，不能把区间当成独立调用成功率的保证。

仓库不包含账户凭据、私人平台会话或模型思考过程。离线演示可直接复现，真实模型实验需自己的 EVO 授权。
