# 提示词与工作流回归测试

改完提示词，拿同一批任务再跑一遍，就能看出哪些答案变好了，哪些工具调用变了，费用和耗时有没有上升。这个 Skill 把输入、评分规则和运行记录留在一起，方便定位变化，也方便复现一次版本比较。

## 适合用来做什么

- 固定任务集和评分规则，比较不同提示词或工作流的正确性、稳定性与成本。
- 核对结构化答案、工具参数和中断后的恢复步骤。文件任务可用固定程序准备输入和核对结果，保留原始业务编号。
- 输出逐次评分和汇总报告。需要试演回滚时，可以单独恢复本地版本指针。

## 快速开始

需要 Python 3.11 或更新版本。下载代码后，在项目目录执行下面的命令。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python start.py --demo --output outputs/first-demo
```

打开 `outputs/first-demo/使用结果.md` 查看报告。演示使用合成数据，运行时无需账号或模型密钥。macOS 和 Linux 请用 `.venv/bin/python` 替换示例中的 Python 路径。

评价自己的运行记录时，按[三步入门](references/getting-started.md)准备任务集、冻结清单、版本与运行记录，再运行下面的命令。

```powershell
.venv\Scripts\python start.py --run --input-dir "我的输入" --output "outputs/我的结果"
```

每次运行请选一个新输出目录。需要了解各字段时，见[数据协议](references/data-contract.md)。

## 历史 EVO 验证记录

此前已在 EVO 验证提示词对照、保留任务复测和回滚后复跑。具体环境和运行范围见 [EVO 验证记录](references/evo-recovery-20261105.md)及[固定流程记录](references/evo-fixed-workflow-20261105.md)。

## 本地复现

随包的三组文件任务在本地实跑，人民币合计分别为 20.454 元、49.25 元和 35.11125 元。金额、业务编号和读表顺序均与独立预期一致，完整本地测试共 141 项通过。这三组使用合成数据，核验记录来自本地程序。

### 复现这三组

把[本地复现材料](assets/v7-local-replay.zip)解压到一个新目录。在该目录运行以下 PowerShell 命令，只需 Python，无需安装额外依赖。

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

看到三行 `verified` 后，可以在各任务的 `output/result.json` 查看详细结果。材料还附有本地实跑结果包，可用同一条核对命令对照。
