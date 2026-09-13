from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'base':{},
 'c9':{'route_scan_value_s':550,'commit_min_known':9},
 'c8':{'route_scan_value_s':550,'commit_min_known':8},
 'c9g3k':{'route_scan_value_s':550,'commit_min_known':9,'probe_allow_gain_low':3000.0,'probe_allow_gain_high':1800.0},
 'c8g3k':{'route_scan_value_s':550,'commit_min_known':8,'probe_allow_gain_low':3000.0,'probe_allow_gain_high':1800.0},
 'c9g4k':{'route_scan_value_s':550,'commit_min_known':9,'probe_allow_gain_low':4000.0,'probe_allow_gain_high':2400.0},
 'c8g4k':{'route_scan_value_s':550,'commit_min_known':8,'probe_allow_gain_low':4000.0,'probe_allow_gain_high':2400.0},
 'c9h10':{'route_scan_value_s':550,'commit_min_known':9,'commit_min_hppd':0.10,'probe_allow_gain_low':3000.0,'probe_allow_gain_high':1800.0},
 'c8h10':{'route_scan_value_s':550,'commit_min_known':8,'commit_min_hppd':0.10,'probe_allow_gain_low':3000.0,'probe_allow_gain_high':1800.0},
}
b.main()
