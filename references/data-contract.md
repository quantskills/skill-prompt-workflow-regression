# 回归测试数据协议

`suite.json` 包含任务和评价参数。任务分别标记 `development` 或 `holdout`，每题有独立编号、输入和规则。规则目前支持 JSON 路径、类型、精确答案及包含元素检查。此版适合结构化输出与工具参数核验，开放式研究结论需另附冻结人工量规，不可强行转成字符串匹配。

```json
{"model":"平台实际模型版本","model_parameters":{"temperature":0,"seed":42},"evaluator":"deterministic-json-rules-v1","min_repeats":3,"max_pass_rate_drop":0,"max_cost_ratio":1.2,"tasks":[{"id":"dev-1","split":"development","input":{"question":"请返回answer等于2的JSON"},"rules":[{"path":["answer"],"equals":2,"type":"number"}]},{"id":"holdout-1","split":"holdout","input":{"question":"计算3加4并输出answer字段"},"rules":[{"path":["answer"],"equals":7,"type":"number"}]}]}
```

例子只说明结构，正式任务应覆盖真实用途、边界输入、工具参数和失败恢复，不能拿两道简单计算题代表工作流质量。

`manifest.json` 由 `freeze` 生成，包含整个任务集和各题的 SHA256，已存在的不同内容不能覆盖。

`versions.json` 包含 `baseline,candidate,suite_hash,version_hashes`。版本散列应由完整提示词与工作流定义按固定序列化生成，不能只写人工别名。候选选择必须在查看保留集响应之前记录。

`runs.jsonl` 每行包含 `run_id,task_id,version,repeat,model,model_parameters,task_hash,version_hash,platform_run_id,status,response,cost,tokens,latency_seconds`。重复编号从 0 到 min_repeats-1。运行失败也计入分母。逐题调用的 `response` 保存原始最终回答；批量调用可从严格 JSON 中拆出各题对象，但必须注明这是规范化子结果，另存完整原始协议及散列。不能剥掉代码围栏、删解释文字或猜测补齐字段后再算通过。费用使用同一单位，另附平台计费凭据。供应商无法固定 seed 时应记录不支持，不能伪填固定参数。

本地测试标识必须以 `fixture:` 开头。真实平台编号同样不能单独证明运行，应对照导出日志和原始产物。报告始终保留平台执行待独立核验状态。

`tokens` 必须为JSON非负整数。小数、布尔值及字符串不自动转换，以免错误输入被取整后混入成本统计。

当前入口也会拒绝重复 JSON 键、NaN、Infinity 等非标准结果，不能绕过批量解析器直接导入宽松 JSON。非测试的 `platform_run_id` 不得跨版本或跨重复编号复用；同一次批量调用的多题可以共用该编号。报告另列不同平台调用数，不能把逐题记录数当作独立调用次数。

单题 `response` 也必须是严格 JSON。代码围栏和解释文字会判失败，评分器不替模型清洗答案；只允许按平台协议区分已放弃的重试段与原始最终回答，不能从最终回答中截取较好的一部分。

精确答案规则仍按冻结的 `equals` 比较，不在看过保留结果后放宽数值容差。需要容差的任务，应先建立新的量规版本与未见测试集。

配对任务的通过率差异使用固定种子 Bootstrap 生成区间，成本比也参与通过条件。任务数量太少时区间缺乏解释力，正式研究需同时报告任务数与覆盖范围。

报告的 `n_tasks` 为本次实际评价任务数；`interval_scope` 明确该区间只是任务级描述性重抽样，不代表独立模型调用的置信度。当前 `verify_session` 只核对单用户输入会话；多轮会话应另建明确协议，不能拼接后冒充单轮输入。

`min_candidate_pass_rate` 默认 0.9，可在冻结前配置。候选和基线都低于最低质量门槛时，recommended_version 为 null，本地状态写入 block 并保留原指针但标记不可使用，不伪造安全回滚目标。

批量调用需记录批次编号。每组至少三次独立调用，不是把一次调用的三个题目算作三次重复；共同费用可按事先约定分摊，分摊后总额须守恒。批内结果相关，任务 Bootstrap 不能当作独立调用的置信度。EVO 中遇到重写时，使用 `platform_export.final_response` 读取最终回答段，保留被放弃的重写段作审计；再用 `verify_session` 对照另行读取的真实平台会话核对输入、最终回答、项目和模型。
