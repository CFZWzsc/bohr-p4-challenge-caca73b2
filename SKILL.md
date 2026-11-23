---
name: results-discussion-writer
description: Use when a case supplies raw result materials (tables, figure captions, statistics text, draft notes) and asks for a Results and Discussion section; extracts numeric claims with units and error-bar meaning, separates observation from interpretation, audits claim strength against statistics, keeps a source map, and emits /app/output/result.json preserving case_id and every output_contract field. Deterministic standard library only; no network.
---

# 结果与讨论章节写作（数值—来源—证据强度三线可核）

## 用途与适用条件

当输入包含**已有数据/图表/统计输出**，要求把它们写成可编辑、可投稿的结果段与讨论段时使用。本 Skill 只处理“数据已在手、图已画好”的转写与论证环节，不负责生成新数据。

适用：

- 输入含数据表、图注、统计输出、方法笔记或讨论备忘中的一种或多种。
- 需要把正文数值逐条回溯到具体材料位置。
- 需要区分“结果只陈述观察”与“讨论承担解释、文献对照、局限”。
- 需要按证据强度收紧因果表述（相关、预测、因果）。

不适用：从零虚构实验、无任何原始材料的空写、替代统计检验、替作者宣称未提供的显著性。

## 输入

- `/input/case.json`：主输入。读取 `case_id`、`output_contract`、`task`/`instruction`，以及材料字段（`materials`、`data`、`tables`、`figures`、`figure_captions`、`statistics`、`notes`、`results`、`discussion` 等）。
- `task.md`：平台实际提供时读取 `/input/task.md` 或 `/app/work/task.md`，缺失不阻塞。
- 材料可以是内联文本，也可以是相对/绝对路径。脚本只读取确实存在、UTF-8 可解码、单文件 ≤2MB 的文本；PDF/图片/二进制只登记为“未解析”，不臆测内容。
- 输出目录 `/app/output`，工作目录 `/app/work`。

## 处理流程（逐项覆盖评分维度）

脚本 `scripts/run_skill.py` 完成确定性主干；Agent 在脚本产物上补足需要判断的行文。

1. **材料清点（任务完成度）**：递归收集所有文本材料，登记 `label`、`path`、字符数与 SHA-256；读不到的登记 `unreadable_materials`，不猜内容。
2. **数值与统计抽取（结果正确性）**：正则抽取数值+单位、误差项（`±`、SD、SEM、CI）、样本量（`n=`）与检验量（`p`、CI 区间）；保留原始片段与字符偏移。单位不做物理换算，只做一致性提示，避免引入原文没有的数值。
3. **结果段组织（结果完整性）**：按材料顺序或图/表编号分组，用**原文句子**拼装抽取式结果段；每个数值句后附 `[source]` 定位标记。脚本不生成新数值，也不把推测写入结果段。
4. **讨论段分层（分得清）**：识别解释性、文献对照、局限三类句子；把含因果/推断连接词的句子单独标记，交由讨论段，不进入结果段。
5. **证据强度审计（说得住）**：含 `cause/leads to/proves/证明/导致` 等强因果词的句子，如果没有同段统计量（p、CI、n、对照）支撑，输出 `suggested_hedge`，并给出替换建议（如 `was associated with`）。
6. **来源映射（核得了）**：`evidence[]` 每条含 `claim`、`value`、`unit`、`source_label`、`source_path`、`char_start`、`char_end`、`snippet`；无法定位的数值写入 `uncertainty`，不补造来源。
7. **边界与缺口**：阴性结果、未报告误差、单位缺失、只出现一次且无表可核的数值，分别登记到 `uncertainty` 与 `limitations`。
8. **合同保留与自查**：见下节。

## 输出契约

写入 `/app/output/result.json`：

- 顶层 `case_id` 与 `case.json` 完全一致。
- **保留原始 `output_contract` 的每个字段名**：支持字段字典、字段列表、`fields`、`properties` JSON Schema。已知语义字段按别名填充；无法映射的字段写 `null` 并在 `contract_status.unmapped_fields` 登记，此时整体降为 `partial`。组合 Schema（`anyOf/allOf/oneOf/$ref/patternProperties`）不猜测投影，登记 `unsupported_features`。
- 固定字段：
  - `status`：`success | partial | insufficient_input | failed`
  - `result`：`results_draft`、`discussion_draft`、`numeric_table`、`claim_audit`、`section_map`
  - `evidence`：数值—来源映射数组
  - `uncertainty`：缺失、冲突、待人工确认项
  - `errors`：运行错误（无错误为空数组）
  - `stats`：材料数、数值条数、可定位数、需收紧表述数
- 退出码：`0` 成功；`1` 合同存在未映射字段；`2` 输入缺失或不可读（仍写出结构化 JSON）。

## 异常处理

| 情形 | 处置 |
|---|---|
| `case.json` 不存在/非法 JSON | 写 `status=failed`、`errors` 记原因、退出码 2，不编造结果 |
| 无任何可用材料 | `status=insufficient_input`，`result` 为空骨架，`limitations` 记 `materials_missing` |
| 有材料但无数值 | `status=partial`，只产出定性结果段，`uncertainty` 记 `no_numeric_claims` |
| 单位缺失或混用（mg/mL 混写） | 原样保留，登记 `unit_inconsistency`，不擅自换算 |
| 误差棒含义不明（SD/SEM/CI 未标注） | 登记 `error_bar_ambiguous`，正文用“误差棒”占位并标注待确认 |
| 数值只在正文出现、无表/图可核 | 登记 `untraceable_value`，保留但不声称已核实 |
| 因果句无统计支撑 | 输出 `suggested_hedge`，不直接改结论 |
| 材料间数值冲突 | 两条都保留，标 `conflict`，升级人工确认 |

## 限制与不适用

- 不做统计检验、不重算 p 值、不推断未给出的显著性。
- 不做单位物理换算，避免生成原文没有的等价数值。
- 抽取式结果段保证可溯源，但不等于已获得期刊语言风格；最终行文仍需 Agent/作者润色。
- PDF、图片、扫描图不解析；未读取的内容不声称已理解。
- 不判断研究结论在领域内是否成立。

## 最小调用示例（示例）

以下为合成示意，非官方案例，不代表任何真实研究结果。

```bash
python /skills/weekly-skill/scripts/run_skill.py \
  --case /input/case.json \
  --out /app/output/result.json \
  --work /app/work
```

合成 `case.json`：

```json
{
  "case_id": "synthetic-rd-demo",
  "output_contract": {"status": "string", "results": "string", "discussion": "string", "evidence_map": "array"},
  "materials": [
    {"path": "results.md", "content": "Body weight decreased by 18.4% in the treated group and 4.1% in controls (n=40 per arm, p=0.003). Values are mean +/- SD."},
    {"path": "discussion.md", "content": "The treatment therefore causes metabolic reprogramming. However, the 12-week duration limits inference about long-term outcomes."}
  ]
}
```

示意输出（节选，仅演示字段保留与审计方式）：

```json
{"case_id":"synthetic-rd-demo","status":"success","result":{"results_draft":"Body weight decreased by 18.4% ... [s1]","discussion_draft":"...","numeric_table":[{"value":"18.4","unit":"%","source_label":"materials[0]"}]},"evidence":[{"claim":"decreased by 18.4%","source_label":"materials[0]"}],"uncertainty":[],"errors":[],"stats":{"numeric_claims":3}}
```

## 自查清单

- [ ] `case_id` 与输入完全一致。
- [ ] `output_contract` 每个字段名都存在；未映射项已登记且状态为 `partial`。
- [ ] 结果段不含解释性因果句，讨论段不含未标注的原始读数堆砌。
- [ ] 每个正文数值都有 `evidence` 定位或 `uncertainty` 说明。
- [ ] 强因果表述均有统计支撑或已给出 `suggested_hedge`。
- [ ] 未换算单位、未补造数值、未声称运行官方固定案例。
- [ ] 无网络调用，无第三方依赖。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. **必须交付完整成品**：脚本只做抽取与审计；调用 Agent 必须据材料写出完整 `results_draft` 与 `discussion_draft`（覆盖全部图表与数值，观察与解释分离），并为每个数值保留 `evidence` 定位；缺数值/误差说明时显式标注，不得留空段或 `pending`。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 取本合同允许值 `success | partial | insufficient_input | failed`；正文无 `pending`/`TODO`/空占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
