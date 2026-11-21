# 径赛冲线判读数据集

从合成裁判判读区间、机位标尺与道次关联发布单场名次或可能名次。 使用合成资料。无需联网、账户或第三方 Python 依赖；已验证 Python 3.14。

```sh
python3 -m finishline preview examples/baseline.json
python3 -m finishline publish examples/baseline.json ledger.sqlite original
python3 -m finishline publish examples/changed.json ledger.sqlite revised
python3 -m finishline publish examples/protest.json ledger.sqlite protested
python3 -m finishline history ledger.sqlite
python3 -m finishline show ledger.sqlite original
python3 -m finishline source ledger.sqlite protested
python3 -m finishline replay ledger.sqlite revised
```

仲裁（`protest.json`）只对一位选手提出异议：输出的 `arbitration` 块枚举所有相容解释，仅对全部解释都稳定的名次给出 `citable_places`，并区分 `challengeable`（真的可被异议改变的确定名次）与原本就不可判的区间；异议陈述文本只存档，从不作为测量。`arbitration_conflict.json` 含不能同时采用的替代项，`invalid_arbitration.json` 必须被拒绝。

`preview` 不写库；`show` 读已发布成果，`source` 读随版封存的输入，`replay` 重算并核对。`publish` 不覆盖已用版名。命令在输入错误时以状态 2 退出，不发布结果。重复演示请换版名或用新库。无 `arbitrations` 块的输入输出与旧版完全一致。测试：`python3 -I -m unittest discover -s tests -v`。

样本字段及成果口径见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。这里的规则仅用于合成数据，并非真实业务规范。
