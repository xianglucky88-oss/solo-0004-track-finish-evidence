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

`preview` 不写库；`show` 读已发布成果，`source` 读随版封存的输入，`replay` 重算并核对。`publish` 不覆盖已用版名。命令在输入错误时以状态 2 退出，不发布结果。重复演示请换版名或用新库。

含机位零点偏差的两份合成输入演示联合可行域验收：

```sh
python3 -m finishline preview examples/shared_offsets.json   # 同机可证先后 + 跨机循环冲突
python3 -m finishline preview examples/camera_cycle.json     # 三对单独可行、联合不可行
python3 -I tests/acceptance.py                               # 全部验收断言
```

`camera_offsets` 给出每机位共享未知零点偏差的校验界，`proposed_orderings` 检验裁判拟宣告的先后能否在同一套偏差下同时成立；没有这些材料的历史输入输出不变。口径见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。

样本字段及成果口径见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。这里的规则仅用于合成数据，并非真实业务规范。
