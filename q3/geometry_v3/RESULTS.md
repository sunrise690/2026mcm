# 离线仿真结果

数值由 build_report.py 从每局结果自动生成。秒/源均值仅覆盖成功局；有失败的版本不进入全清耗时排名。

| 数据集 | 版本 | 全清且满足该版本完成条件 | 秒/源 |
|---|---|---:|---:|
| train | planned_legacy | 35/35 | 358.2085 |
| train | v3_flow | 35/35 | 331.6299 |
| validation | latest | 35/35 | 233.9378 |
| validation | planned_legacy | 35/35 | 358.3370 |
| validation | v3_flow | 35/35 | 323.4777 |
| development | v3_flow | 300/300 | 316.2284 |
| regression | v3_flow | 70/70 | 313.9141 |
| confirmation | latest | 129/140 | 239.8032 |
| confirmation | planned_legacy | 140/140 | 348.1366 |
| confirmation | v3_flow | 140/140 | 323.5891 |

## 同场景配对比较

正值表示新方案更快。区间为固定种子的 10000 次场景配对自举 95% 区间。

- train: v3_flow 相对 planned_legacy 平均节省 26.5786 s/源（7.42%），区间 [11.2648, 41.9220]；快/平/慢=26/0/9，共同全清 35/35。
- validation: v3_flow 相对 planned_legacy 平均节省 34.8594 s/源（9.73%），区间 [13.3211, 56.0311]；快/平/慢=24/0/11，共同全清 35/35。
- confirmation: v3_flow 相对 planned_legacy 平均节省 24.5475 s/源（7.05%），区间 [16.3247, 32.7021]；快/平/慢=101/0/39，共同全清 140/140。

latest 是冻结提交 4be1da2 的概率软停止版，通常更快，但不提供连续域完整性证书。
本目录提供独立严格全清方案，不替换 q3/current，也不声称击败其成功子集的耗时。

所有正式数值须结合 evidence/audit.json 的动作重放与独立覆盖检查结果使用。
