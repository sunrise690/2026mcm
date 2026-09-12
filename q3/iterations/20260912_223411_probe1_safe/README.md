# Q3 iteration 20260912_223411_probe1_safe

离线模拟器迭代，控制器在概率停止后增加 1 次独立后验热点复查，并使用 particle_n=32000 / particle_rebuild_n=64000 / service_iters=2。

验证集 35 例：34/35 全清，源清除率 99.7802%，全清案例平均 271.2593 秒/源；N=16 五例全清，平均 205.5731 秒/源。该候选未达到全清与总平均目标，保留用于后续分析。

本地源码：q3_iterations/src/tunable_controller.py；配置：q3_iterations/configs/t_probe1_safe.json；结果：q3_iterations/runs/20260912_223411_497162_probe1_safe/results.json。
