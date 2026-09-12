# iter_076_full_clear_rescue

这是第四问当前的**完整可运行实验候选**。不覆盖 `q4/CURRENT.json`。

## 已复现 35-case 结果

- 平均时间：`358.339572 s/source`
- 总清除：`436 / 455 = 95.8242%`
- 完全清除：`25 / 35 = 71.4286%`
- seeds：`950000..950034`
- `N = 10 + i % 7`
- `directional_fraction = (i % 5) / 4`

## 一键运行

进入本目录后：

```bash
python run_iter076.py
```

`run_iter076.py` 会自动解压 `iter076_source_bundle.zip` 到本目录的 `workspace/`，然后执行：

```bash
python workspace/code/benchmark_iter076.py
```

首次运行前如缺依赖：

```bash
python -m pip install -r workspace/code/requirements.txt
```

也可以手动解压源码包后运行：

```bash
unzip iter076_source_bundle.zip
cd workspace
python -m pip install -r code/requirements.txt
python code/benchmark_iter076.py
```

运行后会生成：

```text
workspace/iter076_validation.csv
```

## 源码包内容

`iter076_source_bundle.zip` 内含完整复现实验所需文件：

- `workspace/PROBLEM_FACTS.json`
- `workspace/code/params.py`
- `workspace/code/utils.py`
- `workspace/code/sim_engine.py`
- `workspace/code/deferred_proto.py`
- `workspace/code/iter076_policy.py`
- `workspace/code/benchmark_iter076.py`
- `workspace/code/requirements.txt`
- `workspace/iter076_validation.csv`

源码包 SHA256：

```text
73a3027f7f26f762cc5259968539237c57227e088f345e46a0b860d6de034757
```

## 冻结参数

```python
radius = 520
startup_angles = (0, 120, 240)
radii = (525, 1700)       # 延后第 5 点候选半径集合
route_lambda = 0.000472
unknown_gate = 426
second_if = 12
tail_ring_radius = 1225
tail_travel_penalty = 0.00012
third_if = 10
third_radius = 1800
third_angle = 40
```

之前只提交 README 时漏写了 `radii=(525,1700)`，导致无法复现 358.34；本版本已补齐完整源码包、运行入口和精确参数，指标以 `benchmark_iter076.py` 的实际输出为准。
