from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'cover1':{'bootstrap_info_w':180.0,'bootstrap_gain_w':0.035,'bootstrap_move_w':0.07},
 'cover2':{'bootstrap_info_w':140.0,'bootstrap_gain_w':0.045,'bootstrap_move_w':0.06},
 'cover3':{'bootstrap_info_w':100.0,'bootstrap_gain_w':0.055,'bootstrap_move_w':0.05},
 'info1':{'bootstrap_info_w':280.0,'bootstrap_gain_w':0.025,'bootstrap_move_w':0.08},
 'move1':{'bootstrap_info_w':200.0,'bootstrap_gain_w':0.030,'bootstrap_move_w':0.12},
 'move2':{'bootstrap_info_w':180.0,'bootstrap_gain_w':0.035,'bootstrap_move_w':0.16},
 'farcover':{'bootstrap_radii':[750,1000,1250],'bootstrap_info_w':140.0,'bootstrap_gain_w':0.045,'bootstrap_move_w':0.06},
 'nearcover':{'bootstrap_radii':[600,800,1000],'bootstrap_info_w':140.0,'bootstrap_gain_w':0.045,'bootstrap_move_w':0.06},
}
b.main()
