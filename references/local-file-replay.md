# 三组本地文件任务复现

本地交付版用三组冻结的合成文件核对金额累计、业务编号与读表顺序。三组人民币合计分别为 20.454 元、49.25 元和 35.11125 元，业务编号保留前导零。完整本地测试 141 项通过。这个案例未调用模型或 EVO，产物不含平台回执。

把[本地复现材料](../assets/v7-local-replay.zip)解压到新目录。用 Python 3.11 或更新版本即可，无需额外依赖。

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

看到三行 `verified` 后，在各任务的 `output/result.json` 查看结果。输入、执行脚本和本次产物可按冻结清单核对。材料另附此前本机运行的 `v7-local-observed-results.zip`，也可传给同一核对命令。

每组包含一次预设超时后的重试和一次模拟的受限表拒绝。它们用于核对程序行为。以前的真实平台实验及其边界见 [EVO 验证记录](evo-recovery-20261105.md)与[固定流程记录](evo-fixed-workflow-20261105.md)。
