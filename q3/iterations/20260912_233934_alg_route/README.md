# Q3 algorithm iteration 20260912_233934_alg_route

算法改动：在高源数阶段，探索点选择对满足后验完成阈值的候选统一优先最短路线，减少后段无效移动；保留原有全清约束。

完整离线验证集 35 例：35/35 全清，源清除率 100%，总平均 247.1341 秒/源，P90 298.2987 秒/源；15 源 235.4305 秒/源，16 源 203.6388 秒/源。

本地源码：`q3_iterations/src/tunable_controller.py`；结果：`q3_iterations/runs/20260912_233934_068442_alg_route_full/results.json`。
