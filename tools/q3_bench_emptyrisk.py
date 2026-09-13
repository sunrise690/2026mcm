from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'r1_12':{'risk_empty_probe_stop':1,'risk_empty_probe_limit':1,'risk_empty_probe_max_known':12},
 'r2_12':{'risk_empty_probe_stop':1,'risk_empty_probe_limit':2,'risk_empty_probe_max_known':12},
 'r1_11':{'risk_empty_probe_stop':1,'risk_empty_probe_limit':1,'risk_empty_probe_max_known':11},
 'r2_11':{'risk_empty_probe_stop':1,'risk_empty_probe_limit':2,'risk_empty_probe_max_known':11},
 'v550_r1_12':{'route_scan_value_s':550,'risk_empty_probe_stop':1,'risk_empty_probe_limit':1,'risk_empty_probe_max_known':12},
 'v550_r2_12':{'route_scan_value_s':550,'risk_empty_probe_stop':1,'risk_empty_probe_limit':2,'risk_empty_probe_max_known':12},
}
b.main()
