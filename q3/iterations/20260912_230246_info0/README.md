# Q3 iteration 20260912_230246_info0

离线模拟器参数实验：减少清除后的重复信息测量，`route_info_limit_low=0`、`route_info_limit_high=1`、`scan_info_score_thr=0.28`，其余沿用 t_p32。

验证集 35 例：35/35 全清，平均 263.5913 秒/源，P90 319.8331 秒/源；N=16 平均 213.4417 秒/源。结果劣于当前最佳，已排除该方向。

本地结果：q3_iterations/runs/20260912_230246_443682_info0/results.json。
