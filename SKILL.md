---
name: prompt-workflow-regression
description: Freeze task suites and prompt or workflow versions on EVO, compare repeated runs for pass rate, variability and cost, and audit reproducible regression detection and rollback. Use software quality metrics rather than strategy drawdowns.
metadata:
  platform: EVO
  development_status: research-platform-behavior-failures-documented
  organization: https://github.com/quantskills
---

# 提示词与工作流回归测试

将提示词和工作流视为有版本的软件，以冻结任务与量规比较迭代效果，检测退化并回滚到已知可用版本。

## 流程

普通使用先读[入门说明](references/getting-started.md)，使用 `start.py --check`、`--demo --output 新目录` 或 `--run --input-dir 输入目录 --output 新目录`。无参数显示中文菜单。用户已有符合协议的数据时不要求先登录平台；以下平台流程仅在需要采集或复验证据时使用。新入口不联网、不安装、不登录、不修改平台状态。正式评分与模型审查只在需要时读[可选评估](references/assessment.md)。

1. 在 EVO 建立真实研究会话。保存平台版本、模型名称与版本、采样参数、提示词、工作流与工具版本。
2. 冻结开发集和保留集。标准答案与量规保留给评价程序，不能放进发给被测模型的输入。
3. 运行 `freeze` 建立不可覆盖的任务清单。开发时只看开发集，候选版本冻结后才评价保留集。
   新增语义答案、工具参数和失败恢复任务时，使用 v2 的 `exact_json`，参见[故障测试](references/semantic-workflow-tests.md)。不要沿用只检查格式的规则，也不要修改历史 v1 保留题。
4. 每版每题至少三次运行，保留原始响应、失败状态、token、费用、延迟和平台任务编号。按 [数据协议](references/data-contract.md) 导出。
   文件任务需要限定读取方式或核验运行回执时，先读并使用[文件任务执行约定](references/execution-contract.md)。把说明文件白名单、禁止预读数据、权限失败不绕过、回执未知字段填 null 放进实际发送的请求；不能只在验收时追加要求。平台工具轨迹与模型自报记录分开保存和核对。
   有独立平台响应时可用[回执核对工具](references/receipt-validation.md)。只有 UI 摘要时要单列证据缺口，不能把模型填写的来源当成独立证明。[最新三轮复验](references/kimi-provenance-20261105.md)中断恢复后发生了跨轮读取，说明结果正确仍不足以放行。
5. 比较配对任务通过率、重复波动和成本。稳定性不能用策略净值或回撤替代。
   候选默认至少 90% 通过。基线与候选同时不合格时阻止发布，不能把“同样失败”当作不退化。批量任务按独立模型调用计算重复次数，批内任务不能冒充独立样本。
6. 预设一个退化候选，在真实平台复跑并检测。保留候选失败、回滚版本以及回滚后复测记录。
7. `--local-state` 只更新本机版本指针，不会替你完成 EVO 工作流回滚。必须另核平台真实状态。
8. 输出研究结果与局限。正式活动评估另见[可选评估](references/assessment.md)，不作为运行条件。

```powershell
python scripts/regression.py freeze --suite suite.json --manifest manifest.json
python scripts/regression.py evaluate --suite suite.json --manifest manifest.json --versions versions.json --runs runs.jsonl --split development --output outputs/development
```

首次使用可运行 `python scripts/demo.py --output outputs/demo-01`，只演示合成输入与本地回滚，不调用模型。每次评价使用新输出目录，不覆盖旧证据。

保留集用 `--split holdout`，必要时传入 `--local-state state.json` 演示本地回滚。平台操作见 [真实复跑](references/platform-run.md)。已完成一轮限定任务集的 EVO 多版本运行、独立项目回滚与恢复后复测、DeepSeek Flash 初审，以及补强代码的平台复验；负责人验收仍待完成。中文 JSON 输出见[平台适配约定](references/zh-json-contract.md)。
