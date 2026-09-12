# 第三问：小风险预算几何算法

把严格全域覆盖的末段补扫，改为带保守概率积分上界的风险预算停止。
待清的已发现源仍必须清除；预算只作用于可能存在但尚未发现的源。

冻结确认选择为 `risk005`。源清除顺序与补扫位置在每个决策回合根据
新观测更新，只执行当前选定的行动，不锁定全程路线。固定的是比较
规则与风险预算。最终收益、风险上界和发布判定见下列证据文件。

- [算法与模型依据](DESIGN.md)
- [离线实验结果](RESULTS.md)
- `configs/protocol.json`：小风险、大收益与独立确认样本的预设条件。
- `evidence/`：逐局结果、未删减的失败局、动作归档、风险复算和发布门禁。

本目录依赖同一分支中的 `q3/geometry_v3`。该目录提供冻结的定位与路由
基线、严格全清参考以及原离线模拟器；测试不会连接在线比赛接口。

在本目录运行：

```powershell
python -m pip install -r ../geometry_v3/requirements.txt
python -B -m unittest discover -s tests -v
python -B benchmark.py --variants risk005 --seeds 0,7,10040 --workers 3 --label smoke
python -B benchmark.py --variants certified_reference,risk005 --seed-range 70000 70600 --workers 6 --label confirmation
python -B verify_evidence.py
```

`benchmark.py` 真正执行控制器和原模拟器。`verify_evidence.py` 重放
已归档动作，并依据公开阴性观测重新计算风险上界；重放与重新执行的
作用不同。依赖版本在前轮 requirements.txt 中冻结为 NumPy 2.3.5、
SciPy 1.17.1，验证环境为 Python 3.11。

## 可选算法

| 名称 | 行为 |
|---|---|
| certified_reference | 前轮严格几何证明版 |
| fast_reference | 冻结的概率快速版，仅作对照 |
| risk001 | 内部模型风险预算 0.1% |
| risk003 | 内部模型风险预算 0.3% |
| risk005 | 内部模型风险预算 0.5% |
| risk010 | 内部模型风险预算 1% |
| risk001_discrete | 关闭连续选点精化的消融版本 |

模型风险预算不是测得的失败率。发布判断另外检查至少 600 个新场景
上的实际失败率置信上界和包含失败局的配对耗时。未选中的算法仍可
复算，但不因此视为通过发布验证。

`risk_controller.Q3ParticleController(client, tune={'risk_epsilon': 0.005})`
保留既有公开 client 接口。使用时需把本目录 src 和 geometry_v3/src
加入模块路径。返回记录中的 `bounded_model_risk` 表示允许剩余模型
风险，不可将其解释为零风险覆盖证明。

上述命令和接入方式显式选择经过确认的 0.5% 预算；类本身不传 tune
时默认使用更保守的 0.1% 预算，其耗时不应与 risk005 的报告混用。

所有结论限定于说明中的独立源与接收半径先验及离线练习分布。代码
没有读取单局真值、生成种子或实际源数来决定动作；离线成绩不等于
官方正式测试成绩。
