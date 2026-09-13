from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Focus around the v550 result and restrict the cheaper scanning policy to low-known stages.
b.CANDIDATES={
 'baseline':{},
 'v450':{'route_scan_value_s':450},
 'v500':{'route_scan_value_s':500},
 'v550':{'route_scan_value_s':550},
 'v600':{'route_scan_value_s':600},
 'v650':{'route_scan_value_s':650},
 'v500_max12':{'route_scan_value_s':500,'adaptive_route_scan_max_known':12},
 'v550_max12':{'route_scan_value_s':550,'adaptive_route_scan_max_known':12},
 'v600_max12':{'route_scan_value_s':600,'adaptive_route_scan_max_known':12},
 'v550_max13':{'route_scan_value_s':550,'adaptive_route_scan_max_known':13},
 'v550_max14':{'route_scan_value_s':550,'adaptive_route_scan_max_known':14},
}
b.main()
