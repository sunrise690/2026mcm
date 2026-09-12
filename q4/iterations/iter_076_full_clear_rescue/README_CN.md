# iter_076_full_clear_rescue

第四问全清率优化实验候选；不覆盖 `q4/CURRENT.json`。

## 35-case 可复现结果

- 平均时间：`358.339572132 s/source`
- 总清除：`436 / 455 = 95.824176%`
- 完全清除：`25 / 35 = 71.428571%`
- seeds：`950000..950034`
- `N = 10 + i % 7`
- `directional_fraction = (i % 5) / 4`

## 一键运行

克隆整个仓库后：

```bash
cd q4/iterations/iter_076_full_clear_rescue
python run_iter076.py
```

`run_iter076.py` 会：

1. 拼接 `bundle_b64/part_00.txt ... part_06.txt`；
2. Base64 解码得到完整源码 ZIP；
3. 校验 SHA256；
4. 解压 `workspace/`；
5. 执行 `workspace/code/benchmark_iter076.py`。

源码包期望值：

```text
size   = 30859 bytes
sha256 = 73a3027f7f26f762cc5259968539237c57227e088f345e46a0b860d6de034757
```

如缺依赖：

```bash
python -m pip install -r workspace/code/requirements.txt
python workspace/code/benchmark_iter076.py
```

## 完整源码

重组后的源码包包含：

- `workspace/PROBLEM_FACTS.json`
- `workspace/code/params.py`
- `workspace/code/utils.py`
- `workspace/code/sim_engine.py`
- `workspace/code/deferred_proto.py`
- `workspace/code/iter076_policy.py`
- `workspace/code/benchmark_iter076.py`
- `workspace/code/requirements.txt`
- `workspace/iter076_validation.csv`

## 冻结参数

```python
radius = 520
startup_angles = (0, 120, 240)
radii = (525, 1700)
route_lambda = 0.000472
unknown_gate = 426
second_if = 12
tail_ring_radius = 1225
tail_travel_penalty = 0.00012
third_if = 10
third_radius = 1800
third_angle = 40
dir_prior = 0.55
```

之前 README-only 版本漏写了 `radii=(525,1700)`，且第一次直接上传 ZIP 被接口截断。本版本改为可校验的 7 个文本分块，启动器会在运行前验证完整 SHA256；本地已用同一流程复跑并得到上面的 35-case 指标。
