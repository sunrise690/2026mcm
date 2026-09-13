from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Main bootstrap geometry (used whenever origin scan finds > sparse_max_known).
b.CANDIDATES={
 'baseline':{},
 'b550_750_950':{'bootstrap_radii':[550,750,950]},
 'b600_800_1000':{'bootstrap_radii':[600,800,1000]},
 'b650_850_1050':{'bootstrap_radii':[650,850,1050]},
 'b700_900_1100':{'bootstrap_radii':[700,900,1100]},
 'b750_950_1150':{'bootstrap_radii':[750,950,1150]},
 'b800_1000_1200':{'bootstrap_radii':[800,1000,1200]},
 'b850_1050_1250':{'bootstrap_radii':[850,1050,1250]},
 'b900_1100_1300':{'bootstrap_radii':[900,1100,1300]},
 'b650_900_1150':{'bootstrap_radii':[650,900,1150]},
 'b700_950_1200':{'bootstrap_radii':[700,950,1200]},
}
b.main()
