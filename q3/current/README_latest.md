# Q3 iteration 20260913_013237_servroute08

离线模拟器固定验证集 35 例，N=10–16 各 5 例，35/35 全清。

- 总平均：233.9614097465 秒/源（上一最佳 234.1311266301）
- P90：291.1748087400 秒/源
- N10：289.4778319600
- N11：259.8575915636
- N12：241.7033059833
- N13：221.1150505692
- N14：218.5426781429
- N15：206.0305273067
- N16：201.0028827000

核心变化：清除排序不再把待清源视为单个中心点。对高不确定源，将“交会测量站 → 估计中心”视为一个有向服务任务，并以精确动态规划选择任务顺序，使路线代价更贴近真实执行路径。

评测命令：

```powershell
python -B q3_iterations/src/run_local.py --variants alg_servroute08_full --seed-file q3_iterations/configs/validation_seeds.json --workers 4 --label full_service_route_validation
```
