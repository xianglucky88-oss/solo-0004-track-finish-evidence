# 当前数据契约

标尺和道次区段是半开像素列区间；判读条目两端含在内。仅一个区段完全覆盖时可判读相应事实。共同起跑；两位选手的闭时间区间严格分开才证明先后；断段仍参与合资格选手的名次不确定性。

结构与字段示例以 `examples/baseline.json` 为准。`changed.json` 是可合法发布的另一个输入；`invalid.json` 是必须拒绝的反例。

独立核对值：r1 确定第 1，r4 确定第 4，r2/r3 均为 [2,3]。改版将最后一条判读移入标尺断段，r1 也不再能发布确定第 1。

入口为 `finishline/cli.py`，归约编排在 `finishline/workflow.py`。有理数输出为整数或 `分子/分母` 字符串；输入的精确非整数应使用 JSON 字符串。不将 `null` 当作零。SQLite 每版保留规范化输入、成果及两者的 SHA-256；这是本地完整性核对，不是数字签名。

## 资格轮席位

输入带 `qualification` 块时（示例 `examples/qualification.json`），除小组名次外另发资格轮成果。`scales[].timebase` 为可选精确字符串：同一相机的标尺段必须同属一个时基，判读事实回带其 `timebase`，无时基标注时为 `null`。

- `qualification.groups[]`：每个合资格选手恰好属于一个组；`automatic_slots` 为组内自动席，不得超过组内人数。
- `qualification.at_large_pools[]`：每个组恰好喂给一个池；池内 `at_large_slots` 按净成绩补跨组席。可读成绩的时基在同一池内不一致即拒绝（不可比的时基不能混入同一池）；无读段成绩不带时基，不参与该约束。

闭区间只证明偏序，偏序的每个线性延拓是一套可接受的名次解释。自动席与跨组席在同一套解释内联合发放：解释中各组先取组内前 `automatic_slots` 名，剩余选手在池内按同一总序取前 `at_large_slots` 名。不允许先固定自动席、再用另一套解释独立挑跨组。可接受的解释数按池用记忆化拓扑计数设上限（50000），超限要求先人工复判，不发布结果。

每位合资格选手给出：

- `decision`：`qualified`（每套解释都拿到席）、`no_slot`（每套解释都无席）、`review`（解释之间不一致，必须复判）。
- `slot`：`automatic` / `at_large`（来源在所有解释中一致）、`undetermined`（肯定晋级但组内边界与跨组补位互相影响，来源未定）、无席或复判时为 `null`。
- `possible_slots`：该选手在各解释中出现过的全部结果（`automatic`、`at_large`、`none`）。
- `timebase`、`readable_finish`：时基归属与成绩是否可读。

`places` 始终按组单独发布小组名次（新增 `group` 字段；无资格轮块时为 `_default`），原小组成绩不依赖资格轮结论、仍可独立读取。

