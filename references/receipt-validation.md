# 核对运行回执

`scripts/receipt.py` 比较回执与验收者独立保存的平台响应。它能拦下缺少来源、虚构响应编号、混用其他运行、猜填退出码等不一致，不能证明观察文件真实，也不能替代读取轨迹检查。

先保存平台原始响应，再由验收者整理 observations.json。每条记录以响应定位标签为键，包含 tool、run_id 和 response。response 保留实际字段，不替缺失字段补 null。只有 UI 摘要时，注明证据不完整，不把摘要冒充完整响应。

以下为虚构格式示例。field_map 由验收者依据实际接口确认，允许 run_id 对应 runId；不从被测模型的回执自动推导映射。

```json
{
  "script_status/example-run": {
    "tool": "script_status",
    "run_id": "example-run",
    "field_map": {"run_id": "runId"},
    "response": {"runId": "example-run", "status": "succeeded"}
  }
}
```

```bash
python scripts/receipt.py --receipt run_receipt.json --observations observations.json --run-id example-run
```

输出 consistent=true 只说明与所给记录一致。失败返回非零退出码并逐项指出差异。缺少独立原始响应、发现越界读取或任务结果错误时，即使一致性检查通过，也不能放行。
