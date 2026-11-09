# 从这里开始

本入口在本地运行，不联网、不登录、不自动安装软件，也不下单。正式评分、模型审查和平台复验不是普通使用的前提。

## 1. 检查环境

需要 Python 3.11 或以上。在本仓库目录打开终端，先运行：

```powershell
python start.py --check
```

检查会列出缺失或不同于已验证版本的依赖；不修改现有环境。未就绪时，手动建立独立环境并安装固定依赖（安装通常需要联网）：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python start.py --check
```

macOS / Linux 将下文的 `.venv\Scripts\python` 换成 `.venv/bin/python`。不要替换平台全局依赖。

入口识别两套完整环境。独立安装采用 requirements.txt 的固定版本；EVO 环境采用 NumPy 1.26.4、pandas 2.3.3、pytest 9.1.1、PyYAML 6.0.3，CTA 还需要 SciPy 1.17.1。不同组合不能混用，缺少依赖或出现其他版本仍会停止。检查本身只核对版本，实际运行证据见[验收记录](validation-20261105.md)。在已经匹配的 EVO 环境中直接使用 `python`，不需要建立新环境或重新安装。

## 2. 跑合成示例

```powershell
.venv\Scripts\python start.py --demo --output "outputs/我的示例 01"
```

打开输出目录里的 `使用结果.md`，先看本次结果和限制，再通过链接打开原始报告。合成数据只检查流程，不证明真实市场或模型效果。演示仅在新输出目录内恢复示例的本地版本指针，不操作平台。

## 3. 用自己的数据

没整理过运行记录的话，可以先照着[完整例子](from-raw-runs.md)跑一遍。里面有两版原始记录和对应的失败原因，可以从评分表一路查回原始回答。

把以下文件放进一个文件夹，字段和内容按[数据协议](data-contract.md)准备；不能只是改文件名。

| 文件 | 内容 |
|---|---|
| `suite.json` | 冻结任务集 |
| `manifest.json` | 与任务集匹配的冻结清单 |
| `versions.json` | 基线与候选版本 |
| `runs.jsonl` | 包含保留集的重复运行记录 |

```powershell
.venv\Scripts\python start.py --run --input-dir "我的输入" --output "outputs/我的结果 01"
```

此入口只评价保留集，不生成冻结清单、不改变本地或平台指针。开发阶段和清单冻结使用 SKILL.md 所列的原命令；候选冻结后才运行保留集。

程序只知道文件由使用者提供，不会自动认证数据真实、授权充分、历史发布时间正确或可成交。已看过的保留样本不能再次冒充未见数据。每次必须指定新输出目录，已有目录即停止，不覆盖旧结果。缺文件时不会建立输出目录；内容错误时会停止，可能保留部分诊断产物，修正后换新目录重试。

不带参数运行 `python start.py` 可使用中文菜单；输入 0 或结束输入即可退出。路径有空格时请加双引号。错误提示不会转印输入正文或凭据。

需要实际平台取数或复跑时读[平台运行](platform-run.md)；仅在需要正式评分、模型审查或负责人确认时读[可选评估](assessment.md)。

