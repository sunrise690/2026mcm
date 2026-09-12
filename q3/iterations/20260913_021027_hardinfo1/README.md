# Q3 iteration 20260913_021027_hardinfo1

离线模拟器固定验证集 35 例，N=10–16 各 5 例，35/35 全清。

- 总平均：233.9378363376 秒/源（上一最佳 233.9614097465）
- P90：291.1748087400 秒/源
- N10：289.4778319600
- N11：259.8575915636
- N12：241.7033059833
- N13：221.1150505692
- N14：218.5426781429
- N15：206.0305273067
- N16：200.8378688375

核心变化：当 16 个源已经全部发现时，将每次清除后的定位补测预算从最多 4 次降到 1 次。此时不存在继续发现未知源的需要，保留一次高价值交会补测即可；完整验证中 N16 平均降低 0.1650138625 秒/源，其他 N 不受影响。

评测命令：

```powershell
python -B q3_iterations/src/run_local.py --variants alg_hardinfo1 --seed-file q3_iterations/configs/validation_seeds.json --workers 4 --label hardinfo1_full_validation
```
