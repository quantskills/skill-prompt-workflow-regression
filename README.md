# 提示词与工作流回归测试

改了一句提示词，回答看起来更顺了，可原来能做的任务还做得对吗？这个工具适合在替换提示词、切换模型或修改工具调用流程前用。让新旧方案做同一批任务，再把运行记录交给它，它会告诉你哪些题做对了、哪些地方变差了，以及有没有足够理由换掉旧方案。

检查规则由你定。除了答案，也可以检查工具参数填没填对、失败有没有如实记录，还能比较记录中的耗时和成本。它在本地读记录和评分，实际调用模型仍由你自己的工作流负责。

## 第一次用，先跑一个示例

在 GitHub 点 **Code → Download ZIP**，解压后在能看到 `start.py` 的文件夹里打开 PowerShell。准备好 Python 3.11 或更新版本，然后依次运行下面三行。安装依赖通常需要联网，跑示例不用账号或密钥。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python start.py --demo --output outputs/first-demo
```

用 macOS 或 Linux 时，把 `.venv\Scripts\python` 换成 `.venv/bin/python`。不想记参数，可以运行 `.venv\Scripts\python start.py` 打开中文菜单，选 `2` 跑示例，按提示填一个新的输出目录。每次换一个目录，旧报告会保留下来。

## 新提示词少填了一项，怎么查？

1. 打开 `outputs/first-demo/使用结果.md`。示例里「建议版本」是 `baseline`，也就是继续用原方案。想知道是哪道题出了问题，接着看明细。
2. 从报告打开 `evaluation/run_scores.csv`。找到任务 `2` 的 `broken` 行，这是示例中的新方案。`reasons` 显示缺少 `answer`，说明这道题的答案没有放在规则要求的位置。
3. 换成自己的任务后，也先查这种具体原因。修改时用开发任务反复试，等方案定下来，再用之前没拿来调过提示词的任务比较，避免刚修好几道熟题就误以为新方案更稳。

## 换成自己的任务

第一次整理记录，可以先跟着[完整例子](references/from-raw-runs.md)做一遍。从原始回答和超时日志出发，整理两版记录、运行比较，再找出哪道题退步、是哪一次运行出了问题。

把下面四个文件放在同一个目录里。可以先打开演示目录里同名的文件，对照看它们是怎么写的。

| 文件 | 放什么 |
| --- | --- |
| `suite.json` | 要做的题，以及每道题怎样算答对 |
| `manifest.json` | 确认评分时用的还是事先定好的那一套题 |
| `versions.json` | 哪个是现用方案，哪个是要比较的新方案 |
| `runs.jsonl` | 两个方案的实际运行记录，一次运行占一行 |

在中文菜单选 `3`，按提示填输入和输出目录。想直接运行也可以用下面这行。第一次准备自己的数据，先看[文件怎么准备](references/getting-started.md)。

```powershell
.venv\Scripts\python start.py --run --input-dir "我的输入" --output "outputs/我的结果"
```

## 文件放在哪

日常从 [`start.py`](start.py) 进，示例材料在 [`assets/`](assets/)，一般不用改 [`scripts/`](scripts/) 里的程序。更细的[数据格式](references/data-contract.md)和[工具参数与失败恢复怎么检查](references/semantic-workflow-tests.md)都放在参考文档。

<a name="复现这三组"></a>
<a name="历史-evo-验证记录"></a>

[本地任务复现](references/local-file-replay.md) · [EVO 验证记录](references/evo-recovery-20261105.md) · [历史软件复验](references/revalidation-r3.md)
