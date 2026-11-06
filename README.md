# 提示词与工作流回归测试

改了提示词或工具流程，怎样知道旧任务还能不能做好？把两套方案的运行记录交给这个 Skill，它按同一批任务和评分规则比较答案、工具参数与成本，指出哪些任务发生退化，给出保留原方案还是试用新方案的建议。评分在本地运行，模型调用由你自己的工作流负责。

## 快速上手

在代码目录打开 PowerShell。需要 Python 3.11 或更新版本。首次安装依赖通常需要联网，示例运行不需要账号或密钥。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python start.py --demo --output outputs/first-demo
```

macOS 或 Linux 用 `.venv/bin/python` 替换命令中的 Python 路径。再次运行时换一个新的输出目录。

## 例子 · 改过的提示词该不该替换原版？

打开 `outputs/first-demo/使用结果.md`。示例特意放入一组表现变差的候选记录，报告会建议保留 `baseline`。实际使用时也先看「建议版本」和通过率差，再打开 `evaluation/run_scores.csv`，按 `task_id` 找到候选结果，读 `reasons` 查明是答案、工具参数还是其他规则出了问题。在开发集修正问题，最后用没参与调优的保留任务做比较。

## 换成自己的记录

把任务集 `suite.json`、冻结清单 `manifest.json`、版本信息 `versions.json` 和重复运行记录 `runs.jsonl` 放进同一个目录。文件如何生成，见[三步入门](references/getting-started.md)和[数据协议](references/data-contract.md)。

```powershell
.venv\Scripts\python start.py --run --input-dir "我的输入" --output "outputs/我的结果"
```

## 参考资料

<a name="复现这三组"></a>
<a name="历史-evo-验证记录"></a>

[语义与工具规则](references/semantic-workflow-tests.md) · [本地文件任务复现](references/local-file-replay.md) · [EVO 验证记录](references/evo-recovery-20261105.md) · [历史软件复验](references/revalidation-r3.md)
