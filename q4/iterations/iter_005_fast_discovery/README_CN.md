# 第五次迭代：缩短普查路径实验（未接纳）

本轮所有实验在本地离线模拟器完成，程序仅使用公开协议响应，不用隐藏源数或源位置选择动作。新留出集未读取、未运行。

## 结论

未找到同时达到逐局平均耗时低于350秒/源与可接受全清率的候选。不得把本目录中的实验版设成默认。旧四次补查版本与两次补查的比对确认，空跑补查是主要可削减成本；但单纯压缩普查前缀、减小外环或缩短连续空测退出阈值，都会放大漏源。

- 固定两圈+完整后验2次补查：35/35，527.16秒/源；比原4次补查592.95快，但仍远离350。
- v371真正早切结构（中心+4个850m点、清源位置级联发现）可接近350，但此前缀未覆盖定向源盲区。
- `v371_ratio` 使用100k完整圆盘粒子、增加2050/2350m候选环，按可见概率/(移动秒+100)选择补查；开发35为26/35、392.12秒/源，旧验证70为41/70、396.80。它只可作为后续结构实验的父候选。
- `v371_outer_full2` 在第一次空补查后停止：开发35为13/35、340.17；旧验证70为29/70、350.03。速度来自漏源，淘汰。
- 清源位置顺路获取第二示向、进一步缩小前缀以及提高测向复测数均未稳定提高速度与全清率。

## 全部实验成绩

|实验|候选|全清|秒/已清源|源级清除率|
|---|---|---:|---:|---:|
|development35_budget2|budget2_base|35/35|527.16|100.00%|
|development35_onsite|ring1800|33/35|528.46|99.56%|
|development35_onsite|route_quick|32/35|541.90|99.34%|
|development35_onsite|route_rescan6|35/35|525.77|100.00%|
|development35_paths|outer1600|31/35|485.31|99.12%|
|development35_paths|compact700_1600|29/35|480.81|98.68%|
|development35_paths|prefix5|31/35|493.52|99.12%|
|development35_prefixes|prefix5_rescan6|32/35|495.97|99.34%|
|development35_prefixes|prefix6_rescan6|28/35|494.39|98.46%|
|development35_prefixes|prefix6_budget3|27/35|456.73|98.02%|
|development35_radii|prefix5_r1200|26/35|434.99|96.70%|
|development35_radii|prefix4_r1200|22/35|424.45|95.82%|
|development35_radii|prefix5_r650|22/35|394.61|95.82%|
|development35_speed350|prefix5_tail1_near|15/35|365.82|92.31%|
|development35_speed350|prefix5_tail2_near|17/35|380.05|94.07%|
|development35_speed350|prefix4_tail2_near|18/35|373.60|92.53%|
|development35_v371|v371_outer_full|15/35|354.05|92.97%|
|development35_v371|v371_outer_gap|20/35|365.15|93.63%|
|development35_v371|v371_outer_full2|13/35|340.17|91.87%|
|development35_v371_cover|v371_cover35|26/35|403.28|97.80%|
|development35_v371_cover|v371_cover65|25/35|380.65|96.92%|
|development35_v371_cover|v371_ratio|26/35|392.12|98.02%|
|development35_v371_crossfree|v371_crossfree|25/35|396.73|97.14%|
|development35_v371_crossfree|v371_crossfree650|23/35|390.28|96.48%|
|development35_v371_crossfree|v371_crossfree_all|26/35|400.63|97.36%|
|development35_v371_shortprefix|v371_tri650|22/35|370.69|95.16%|
|development35_v371_shortprefix|v371_tri400|23/35|380.00|96.48%|
|development35_v371_shortprefix|v371_pair650|25/35|373.32|96.70%|
|old_validation70_frontier|v371_ratio|41/70|396.80|95.38%|
|old_validation70_frontier|v371_outer_full2|29/70|350.03|92.64%|


这些均为开发成绩，不能当独立泛化证据。每次运行保存协议动作、外部评分真值、源码哈希、完整计时对账；代码期间变更与网络访问均由评测器阻止。详细记录见 `iteration_manifest.json` 和 `results/`。
