# 第三次迭代：完整区域有限后验补查

冻结版本：v391-full-posterior。父版本：iter_001_outer_route。此版本偏向全清可靠性，待完整开发集与独立留出集统一评测。

原尾部规则在程序观测到13或14源时，只采样半径900..1770m的定向源，并固定去2100m外环。开发案例揭示内侧定向源也可能躲过原两圈普查，此限制不能由题面推出。候选将全部计数状态统一回完整圆盘后验，连续无信号后重新条件化；固定最多4个补查点，不再切到仅看角隙的外环策略。粒子数由20000增到200000，以缓解完整14点后只剩极少尾部粒子的采样问题。

原14点、前六点顺序、外环路径、测向定位和保守清除走廊均保持。此候选不构成全域完备性保证；四个补查点对部分已全清案例会产生额外成本。

在四个已知开发失败案例的局部回放中，候选均全清；这些是用于改程序的案例，不能当独立验证。详细成绩保存在iteration_manifest.json，以及reports/iter002_dense_anomalies4。

策略不读取真值、种子或真实源数。程序分支只基于合法接口响应与题面参数及已记录的练习分布先验。真值只在程序结束后由外部评测器计算成功率。

单案例离线运行示例（从B0目录执行）：

```powershell
python q4_iterations/tools/offline_benchmark.py worker --version "C:/Users/1/Desktop/B0/q4_iterations/iter_003_full_posterior/workspace/code" --seed 1005 --out "q4_iterations/reports/iter003_replay/seed_1005"
```

完整开发与独立留出验证由主任务统一运行，避免对留出结果反复调参。

后续验证及冻结状态以根目录 reports/iteration_report_CN.md 为准。后验1770m边界来自离线练习先验，题面目标区域为1800m。
