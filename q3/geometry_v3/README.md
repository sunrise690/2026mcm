# 第三问几何 V3

独立的严格全清实验版本。核心是连续圆域覆盖检查、残余点簇的凸约束
投影、沿服务路线提前插入补扫站，以及独立闭方格完成验证。

这是上一轮严格全清基线：可靠性验证通过，但当时约定的绝对速度门槛
未达到，见 [历史发布判定](PUBLICATION_DECISION.md)。用户随后允许小
风险换取收益，新迭代在相邻的 [risk_v4](../risk_v4/README.md) 中；本目录
保留为其冻结依赖和严格对照，不替换 q3/current。

- [仿真结果](RESULTS.md)：全清率、耗时与同种子配对比较。
- [算法推导与历史版本分析](DESIGN.md)：适用条件、证明、复杂度及失效处理。
- `configs/evaluation_protocol.json`：冻结比较协议和新确认集区间。
- `evidence/`：逐局结果、原始动作归档、源码哈希及重放审计。

本目录保留 `q3/current` 的概率快速版。V3 的目标是改进严格全清版本的
耗时；它不以舍弃失败局来争夺概率快速版的耗时排名。

## 运行

在本目录使用 Python 3.11，依赖版本记录在 requirements.txt：

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B benchmark.py --variants latest,planned_legacy,v3_flow --seed-file configs/validation_seeds.json --workers 4 --label validation
python -B benchmark.py --variants latest,planned_legacy,v3_flow --seed-range 50000 50140 --workers 4 --label confirmation
python -B verify_evidence.py
```

benchmark.py 会真正运行原离线模拟器，在 runs 下生成新目录。
verify_evidence.py 则重放已发布的动作归档并重新计算指标和覆盖证据。
两种操作的含义不同：重放核验不替代重新运行控制器。

控制器接入方式：将 src 加入模块路径后，实例化
`controller.Q3ParticleController(client, tune={'joint_geometry': 1,
'joint_detour_m': 800, 'geometric_route_scan': 1})` 并调用 run()。
client 必须提供 enter、measure、clear、exit、position、receiver_channel、
last_response 和 current_virtual_time_s，响应含明确 accepted 字段。
本轮只执行离线评测，没有连接在线比赛接口。

## 主要文件

| 文件 | 用途 |
|---|---|
| src/coverage_geometry.py | 覆盖缺口检查、独立单元证书、测站投影与约束交换 |
| src/controller.py | 观测更新、定位服务、路线协同、严格完成判据 |
| src/baseline_latest.py | 冻结提交 4be1da2 的快速版，用于对照 |
| src/baseline_planned.py | 历史束搜索严格全清对照及依赖 |
| simulator/jammers_offline_sim.py | 哈希锁定的原离线模拟器 |
| benchmark.py | 子进程超时、离线运行、结果和源码清单 |
| build_report.py | 从已结束的运行生成证据包和结果表 |
| verify_evidence.py | 归档哈希、动作、虚拟时间和覆盖证据重放核验 |

全清证书依赖第三问全向源、1000 m 最小接收半径、1800 m 源区域、互异
频道和至多 16 源等边界。有限运行预算内无法取得证书时明确返回未完成。
离线场景结论不等于官方正式成绩，也不保证在所有场景中都比旧版更快。
