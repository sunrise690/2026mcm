from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'r700_900_1100':{'bootstrap_sparse_radii':[700,900,1100]},
 'r750_950_1150':{'bootstrap_sparse_radii':[750,950,1150]},
 'r800_1000_1200':{'bootstrap_sparse_radii':[800,1000,1200]},
 'r850_1050_1250':{'bootstrap_sparse_radii':[850,1050,1250]},
 'r600_850_1100':{'bootstrap_sparse_radii':[600,850,1100]},
 'r700_950_1200':{'bootstrap_sparse_radii':[700,950,1200]},
 'r750_1000_1250':{'bootstrap_sparse_radii':[750,1000,1250]},
 'r800_1050_1300':{'bootstrap_sparse_radii':[800,1050,1300]},
 'r750_950_1150_fw02':{'bootstrap_sparse_radii':[750,950,1150],'bootstrap_first_source_w':0.02},
 'r750_950_1150_fw05':{'bootstrap_sparse_radii':[750,950,1150],'bootstrap_first_source_w':0.05},
}
b.main()
