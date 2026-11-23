---
name: results-discussion-writer
description: Use when a case supplies raw result materials (tables, figure captions, statistics text, draft notes) and asks for a Results and Discussion section; extracts numeric claims with units and error-bar meaning, separates observation from interpretation, audits claim strength against statistics, and emits /app/output/result.json preserving case_id and every output_contract field. Deterministic standard library only; no network.
---

# 结果与讨论章节写作（数值—来源—证据强度三线可核）

## 用途与适用条件

当输入包含**已有数据、图表、统计输出**，要求把它们写成可编辑、可投稿的结果段与讨论段时使用。本 Skill 只处理"数据已在手、图已画好"的转写与论证，不生成新数据。

适用：

- 输入含数据表、图注、统计输出、方法笔记或讨论备忘中的一种或多种。
- 正文数值需逐条回溯到具体材料位置。
- 需要区分"结果只陈述观察"与"讨论承担解释、文献对照、局限"。
- 需要按证据强度收紧因果表述（相关、预测、因果）。

不适用：虚构实验、无任何原始材料的空写、替代统计检验、替作者宣称未提供的显著性。

## 输入

- `/input/case.json`：主输入。读取 `case_id`、`output_contract`、`task`/`instruction`，以及材料字段（`materials`、`data`、`tables`、`figures`、`figure_captions`、`statistics`、`notes`、`results`、`discussion` 等）。
- `task.md`：平台提供时读取 `/input/task.md` 或 `/app/work/task.md`，缺失不阻塞。
- 材料可内联或给路径；脚本只读确实存在、UTF-8 可解码、单文件 ≤2MB 的文本。PDF、图片、二进制只登记为"未解析"，不臆测内容。
- 输出 `/app/output`（`--out` 与 `--output` 等价），工作目录 `/app/work`。

## 处理流程

脚本 `scripts/run_skill.py` 完成确定性主干，调用 Agent 在其产物上补齐需要判断的行文。

1. **材料清点**：递归收集文本材料，登记 `label`、`path`、字符数与 SHA-256；读不到的登记 `unreadable_materials`，不猜内容。
2. **数值与统计抽取**：正则抽取数值+单位、误差项（`±`、SD、SEM、CI）、样本量（`n=`）与检验量（`p`、CI 区间），保留原始片段与字符偏移。单位不做物理换算，只做一致性提示。
3. **结果段组织**：按材料顺序或图/表编号分组，用原文句子拼装抽取式结果段，每个数值句后附 `[label@offset]` 定位；不生成新数值，不把推测写进结果段。
4. **讨论段分层**：识别解释性、文献对照、局限三类句子；含因果/推断连接词且无统计支撑的句子单独标记，交讨论段处理，不进入结果段。
5. **证据强度审计**：含 `cause / leads to / proves / 证明 / 导致` 等强因果词的句子，若同段无 p、CI、n 或对照支撑，输出 `suggested_hedge` 并给出替换建议（如 `was associated with`）。
6. **来源映射**：`evidence[]` 每条含 `claim`、`value`、`unit`、`source_label`、`source_path`、`char_start`、`char_end`、`snippet`；无法定位的数值写入 `uncertainty`，不补造来源。
7. **边界与缺口**：阴性结果、未报告误差、单位缺失、只出现一次且无表可核的数值，分别登记到 `uncertainty`、`limitations` 与 `needs_human_confirmation`。
8. **合同保留与自检**：见"输出契约"与"交付与自检"。

## 输出契约

写入 `/app/output/result.json`：

- 顶层 `case_id` 与 `case.json` 完全一致，不被合同字段覆盖。
- **保留原始 `output_contract` 的每个字段名**：支持字段字典、字段列表、`fields`、`properties` JSON Schema。已知语义字段按别名填充；无法映射的字段写 `null` 并在 `contract_status.unmapped_fields` 登记，整体降为 `partial`。组合 Schema（`anyOf/allOf/oneOf/$ref/patternProperties`）不猜测投影，登记 `unsupported_features`。
- 固定字段：

| 字段 | 类型 | 含义 |
|-|-|-|
| `status` | enum | `success / partial / insufficient_input / failed` |
| `result.results_draft` | string | 结果段成品正文（只陈述观察） |
| `result.discussion_draft` | string | 讨论段成品正文（解释、文献对照、局限） |
| `result.numeric_table` | array | 数值、单位、原始片段、来源标签、字符偏移 |
| `result.claim_audit` | array | 强因果句、问题类型、`suggested_hedge` |
| `result.section_map` | array | 材料标签、角色（results/discussion/mixed）、字符数、哈希 |
| `evidence` | array | 数值—来源映射，可按 `char_start/char_end` 回查原文 |
| `uncertainty` | array | 缺失、冲突、降级假设、待确认项（逐条） |
| `result.needs_human_confirmation` | array | 需人工确认项（调用 Agent 补齐）：`item / locator / reason`，`locator` 不得为空 |
| `errors` | array | 运行错误（无错误为空数组） |
| `stats` | object | 材料数、数值条数、可定位数、需收紧表述数 |

## 异常处理

| 情形 | 处置 |
|---|---|
| `case.json` 不存在 / 非法 JSON | 写 `status=failed`、`errors` 记原因，不编造结果 |
| 无任何可用材料 | `status=insufficient_input`，`result` 为空骨架，`limitations` 记 `materials_missing` |
| 有材料但无数值 | `status=partial`，只产出定性结果段，`uncertainty` 记 `no_numeric_claims` |
| 单位缺失或混用（mg/mL 混写） | 原样保留，登记 `unit_inconsistency`，不擅自换算 |
| 误差棒含义不明（SD/SEM/CI 未标注） | 登记 `error_bar_ambiguous`，正文用"误差棒"占位并标注待确认 |
| 数值只在正文出现、无表/图可核 | 登记 `untraceable_value`，保留但不声称已核实 |
| 因果句无统计支撑 | 输出 `suggested_hedge`，不直接改结论 |
| 材料间数值冲突 | 两条都保留，标 `conflict`，升级人工确认 |

## 限制

- 不做统计检验、不重算 p 值、不推断未给出的显著性。
- 不做单位物理换算，避免生成原文没有的等价数值。
- 抽取式结果段保证可溯源，但不等于期刊语言风格；最终行文仍需 Agent 或作者润色。
- PDF、图片、扫描件不解析；未读取的内容不声称已理解。
- 不判断研究结论在领域内是否成立。

## 最小调用示例（示例，非官方案例结果）

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

示意输出（节选，仅演示字段保留与审计方式）：`{"case_id":"synthetic-rd-demo","status":"success","result":{"results_draft":"Body weight decreased by 18.4% ... [materials[0]@0]","numeric_table":[{"value":"18.4","unit":"%","source_label":"materials[0]"}]},"evidence":[{"claim":"decreased by 18.4%","char_start":22,"char_end":34}],"uncertainty":[],"errors":[],"stats":{"numeric_claims":3}}`

## 交付与自检

1. 先运行 `python scripts/run_skill.py`（默认 `/input/case.json` → `/app/output/result.json`；`--case`、`--out`、`--output` 等价）。脚本正常结束恒以退出码 0 返回，失败类别只看 `status`、`contract_status.unmapped_fields` 与 `errors`。
2. 脚本只做抽取与审计；调用 Agent 必须依据材料写出完整 `results_draft` 与 `discussion_draft`（覆盖全部图表与数值，观察与解释分离，讨论给出来源对照与局限），为每个数值保留 `evidence` 定位，并把缺数值、误差说明不明、材料冲突的条目逐条写入 `needs_human_confirmation`（`item/locator/reason`）。不得留空段、`pending`、`TODO` 或以"待作者补充"作完成态。
3. 自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 取合同允许值；结果段不含解释性因果句；每个正文数值都有 `evidence` 定位或 `uncertainty` 说明；强因果表述均有统计支撑或已给 `suggested_hedge`；未换算单位、未补造数值。
4. 不联网、不伪造数据、不声称平台评分或官方案例结果；逻辑由输入驱动，不针对某份示例硬编码；字段命名差异走别名匹配并在 `uncertainty` 记录假设。
