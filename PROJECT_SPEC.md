# 当前数据契约

标尺和道次区段是半开像素列区间；判读条目两端含在内。仅一个区段完全覆盖时可判读相应事实。共同起跑；两位选手的闭时间区间严格分开才证明先后；断段仍参与合资格选手的名次不确定性。

结构与字段示例以 `examples/baseline.json` 为准。`changed.json` 是可合法发布的另一个输入；`invalid.json` 是必须拒绝的反例。

独立核对值：r1 确定第 1，r4 确定第 4，r2/r3 均为 [2,3]。改版将最后一条判读移入标尺断段，r1 也不再能发布确定第 1。

## 仲裁（可选 `arbitrations` 块）

一次异议只针对一条判读（即一位选手）；不因此假定其他选手的名次必然稳定，也不撤销整条不确定链。每条仲裁给出：

- `protest_text`：仅原样存档的陈述文本，不承载任何读值，系统绝不从中解析数字或区间；
- `options`：仲裁员允许的全部替代项，非空且 id 全局唯一。`{"retain": true}` 保留原测量区间（仅当该判读被标尺与道次完全覆盖时合法）；否则用 `finish_us: [lo, hi]` 给出精确替代闭区间（支持有理数字符串，lo ≤ hi，且不早于共同起跑）；
- `conflicts`：不能同时采用的两个选项 id 组成的对，可跨判读引用，但 id 必须存在且互不相同。

一个**解释**为每条受争议判读各选一个允许选项，并排除命中互斥对的组合；组合数超过 10000 或无任何相容解释时拒绝发布。名次在每个解释内按同一闭区间规则重算，断段未覆盖的合资格选手仍参与全部名次不确定性。

仅对所有相容解释都稳定的名次开放对外引用（`citable_places` / `athlete_outcomes.*.citable_place`）。每位合资格选手的分类：

- `citable`：仲裁后仍确定的名次；
- `challengeable`：原来确定、但确实可被异议改变的名次（真的可被异议改变）；
- `previously_undecidable_widened`：原来就不可判、仲裁后区间进一步扩大；
- `stable_undecidable`：原来就不可判、且不受本次异议影响（不进入受影响名单）。

交付字段：`affected_athletes`（名次稳健区间发生变化者）、`affected_place_range`（这些选手覆盖的名次并集）、`challengeable_places`（丢失的确定名次）、`previously_undecidable_ranges`（原本就不可判的区间），以及每个相容解释的完整 `interpretations` 以便复算。验收样例 `examples/protest.json`：只异议 r2，未提异议的相邻选手 r1 从确定第 1 变为 [1,2]（受影响），时间区间链更远处的 r4 在全部解释中均为第 4（有证稳定、唯一可引用），r3 保持原 [2,3] 不可判且不受影响。`arbitration_conflict.json` 演示互斥替代项；`invalid_arbitration.json` 是必须以状态 2 拒绝的反例。

入口为 `finishline/cli.py`，归约编排在 `finishline/workflow.py`。有理数输出为整数或 `分子/分母` 字符串；输入的精确非整数应使用 JSON 字符串。不将 `null` 当作零。SQLite 每版保留规范化输入、成果及两者的 SHA-256；这是本地完整性核对，不是数字签名。
