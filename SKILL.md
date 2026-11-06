---
name: prompt-workflow-regression
description: Freeze task suites and prompt or workflow versions, then locally compare repeated run records for quality, variability and cost. Use to detect regressions, verify file-task outputs, or audit supplied platform evidence.
metadata:
  platform: local
  development_status: v7-local-verified
  organization: https://github.com/quantskills
---

# 提示词与工作流回归测试

将提示词和工作流视为有版本的软件，以冻结任务与量规比较迭代效果，检测退化并回滚到已知可用版本。

## 流程

普通使用先读[入门说明](references/getting-started.md)，使用 `start.py --check`、`--demo --output 新目录` 或 `--run --input-dir 输入目录 --output 新目录`。无参数显示中文菜单。用户已有符合协议的数据时不要求先登录平台；以下平台流程仅在需要采集或复验证据时使用。新入口不联网、不安装、不登录、不修改平台状态。正式评分与模型审查只在需要时读[可选评估](references/assessment.md)。

复现 v7 的三组本地文件任务时，按 [README](README.md#复现这三组) 使用冻结材料。v7 未做 EVO 验收，不把本地读表日志当作平台回执或文件隔离证据。

1. 本地评价使用现有运行记录。仅在用户要求平台研究时建立 EVO 会话，并保存平台版本、模型版本、采样参数、提示词、工作流和工具版本。
2. 冻结开发集和保留集。标准答案与量规保留给评价程序，不能放进发给被测模型的输入。
3. 运行 `freeze` 建立不可覆盖的任务清单。开发时只看开发集，候选版本冻结后才评价保留集。
   新增语义答案、工具参数和失败恢复任务时，使用 v2 的 `exact_json`，参见[故障测试](references/semantic-workflow-tests.md)。不要沿用只检查格式的规则，也不要修改历史 v1 保留题。
4. 每版每题至少三次运行，保留原始响应、失败状态、token、费用、延迟和平台任务编号。按 [数据协议](references/data-contract.md) 导出。
   文件任务使用[固定准备与打包](references/fixed-file-workflow.md)：操作者先运行固定脚本准备本轮输入，模型不得自行编写解包/打包程序或寻找旧脚本。业务编号保留源字符串，不用行号替代；完成后由操作者核对并打包。
   文件任务需要限定读取方式或核验运行回执时，先读并使用[文件任务执行约定](references/execution-contract.md)。把说明文件白名单、禁止预读数据、权限失败不绕过、回执未知字段填 null 放进实际发送的请求；不能只在验收时追加要求。平台工具轨迹与模型自报记录分开保存和核对。
   有独立平台响应时可用[回执核对工具](references/receipt-validation.md)。只有 UI 摘要时要单列证据缺口，不能把模型填写的来源当成独立证明。参见[固定流程三轮复验](references/evo-fixed-workflow-20261105.md)和[此前跨轮读取记录](references/kimi-provenance-20261105.md)。
   会话中断、刷新、压缩上下文或交接后，先执行[恢复检查](references/recovery-boundary.md)，重新提供本轮范围和进度证据。没有恢复范围时停止，不从旧轮次目录寻找线索。
   需要强制禁止跨轮读取时，参见[受限工具入口](references/scoped-tools.md)。这是未接入 EVO 的本地候选，必须由宿主关闭其他工具；仅上传 Skill 不生效。接入条件不满足时停止平台验收，不宣称隔离已完成。
5. 比较配对任务通过率、重复波动和成本。稳定性不能用策略净值或回撤替代。
   候选默认至少 90% 通过。基线与候选同时不合格时阻止发布，不能把“同样失败”当作不退化。批量任务按独立模型调用计算重复次数，批内任务不能冒充独立样本。
6. 平台研究可预设一个退化候选并复跑。保留候选失败、回滚版本和复测记录。本地演示不需要平台。
7. `--local-state` 只更新本机版本指针，不会替你完成 EVO 工作流回滚。必须另核平台真实状态。
8. 输出研究结果与局限。正式活动评估另见[可选评估](references/assessment.md)，不作为运行条件。

```powershell
python scripts/regression.py freeze --suite suite.json --manifest manifest.json
python scripts/regression.py evaluate --suite suite.json --manifest manifest.json --versions versions.json --runs runs.jsonl --split development --output outputs/development
```

首次使用可运行 `python scripts/demo.py --output outputs/demo-01`，只演示合成输入与本地回滚，不调用模型。每次评价使用新输出目录，不覆盖旧证据。

保留集用 `--split holdout`，必要时传入 `--local-state state.json` 演示本地回滚。平台操作见[真实复跑](references/platform-run.md)，旧版平台结果见 [README 的历史记录](README.md#历史-evo-验证记录)。中文 JSON 输出见[平台适配约定](references/zh-json-contract.md)。
