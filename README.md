# 径赛冲线判读数据集

从合成裁判判读区间、机位标尺与道次关联发布单场名次或可能名次。 使用合成资料。无需联网、账户或第三方 Python 依赖；已验证 Python 3.14。

```sh
python3 -m finishline preview examples/baseline.json
python3 -m finishline publish examples/baseline.json ledger.sqlite original
python3 -m finishline publish examples/changed.json ledger.sqlite revised
python3 -m finishline history ledger.sqlite
python3 -m finishline show ledger.sqlite original
python3 -m finishline source ledger.sqlite original
python3 -m finishline replay ledger.sqlite revised
```

分段发令用 `starts` 描述每次发令及它覆盖的选手，发布 `arrival_places` 和 `net_places` 两张表；旧 `start_us` 场次仍只发布 `places`，结果不变：

```sh
python3 -m finishline preview examples/segmented.json
python3 -m finishline preview examples/missing-start.json
python3 -m finishline publish examples/segmented.json ledger.sqlite segmented
python3 -m finishline replay ledger.sqlite segmented
```

`preview` 不写库；`show` 读已发布成果，`source` 读随版封存的输入，`replay` 重算并核对。`publish` 不覆盖已用版名。命令在输入错误时以状态 2 退出，不发布结果。重复演示请换版名或用新库。

验收测试（含对发令未知量的随机枚举核对）：

```sh
python3 -m unittest discover -s tests
```

样本字段及成果口径见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。这里的规则仅用于合成数据，并非真实业务规范。
