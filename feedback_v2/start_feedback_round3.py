from pathlib import Path
import subprocess,os,json,time
r=Path('/root/autodl-tmp/b0_iteration_20260912')
env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONUNBUFFERED='1')
jobs=[
 ('feedback_q3_v2',r/'feedback_v2_q3',['/root/miniconda3/bin/python','-m','optimizer.autotune','--generations','1000','--population','20','--workers','10','--fast-per-n','1','--medium-per-n','2','--final-per-n','5','--keep-fast','6','--keep-medium','2','--device','cpu','--timeout','120']),
 ('feedback_q4_v2',r/'feedback_v2_q4',['/root/miniconda3/bin/python','feedback_tune_q4.py','--generations','1000','--population','24','--workers','12','--screen-per-n','2','--validate-per-n','10'])]
for name,cwd,cmd in jobs:
 log=open(r/(name+'.log'),'ab',buffering=0)
 p=subprocess.Popen(cmd,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
 (r/(name+'.pid')).write_text(str(p.pid)); print(name,p.pid,cmd)
