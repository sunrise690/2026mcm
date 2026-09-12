"""第三问本地离线评测；独立子进程、真实超时、观测接口及逐局证据。"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'sources' / 'jammers_offline_sim_v3' / 'jammers_offline_sim.py'
CONTROLLERS = {'baseline': ROOT/'src/baseline_commit10.py',
               'tunable': ROOT/'src/tunable_controller.py',
               'complete': ROOT/'src/q3_complete_controller.py',
               'efficient': ROOT/'src/q3_efficient_controller.py',
               'planned': ROOT/'src/q3_planned_controller.py',
               'tuned_legacy': ROOT/'src/q3_tuned_candidate.py'}

def dump(path, obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)

def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

def seed_bytes(seed):
    return hashlib.sha256(f'cumcm-offline-generator-key:{int(seed)}'.encode()).digest()

def config_for(name):
    return json.loads((ROOT/'configs'/f'{name}.json').read_text(encoding='utf-8-sig'))

def offline_guard():
    import socket
    def deny(*args,**kwargs):
        raise RuntimeError('离线评测禁止网络连接')
    socket.socket.connect=deny
    socket.socket.connect_ex=deny
    socket.create_connection=deny
    socket.socket.sendto=deny
    socket.getaddrinfo=deny
    socket.gethostbyname=deny
    socket.gethostbyname_ex=deny
    socket.gethostbyaddr=deny

class ObservationsOnlyClient:
    """仅根据已接受的请求及公开响应维护状态，不向控制器传递场景或引擎。"""
    __slots__=('__dispatch','__position','__channel','last_response')
    def __init__(self,dispatch):
        self.__dispatch=dispatch
        self.__position=(0.0,0.0)
        self.__channel=1
        self.last_response={}
    @property
    def position(self): return self.__position
    @property
    def receiver_channel(self): return self.__channel
    @property
    def current_virtual_time_s(self): return self.last_response.get('virtual_time_s',0.0)
    def enter(self):
        self.last_response=self.__dispatch('enter')
        return dict(self.last_response)
    def _act(self,action,x,y,ch):
        if any(isinstance(v, bool) for v in (x,y,ch)):
            raise ValueError('布尔值不是合法动作参数')
        if not all(isinstance(v,(int,float)) for v in (x,y,ch)):
            raise ValueError('动作参数必须是数值')
        ch_number=float(ch)
        if not math.isfinite(ch_number) or not ch_number.is_integer():
            raise ValueError('频道必须是有限整数')
        x,y,ch=float(x),float(y),int(ch_number)
        if not (math.isfinite(x) and math.isfinite(y) and abs(x)<=2e6 and abs(y)<=2e6 and 1<=ch<=20):
            raise ValueError('非法动作参数')
        self.last_response=self.__dispatch(action,x,y,ch)
        if not self.last_response.get('accepted'):
            raise RuntimeError(f'{action} rejected: {self.last_response}')
        self.__position=(x,y)
        if action=='measure': self.__channel=ch
        return dict(self.last_response)
    def measure(self,x,y,ch): return self._act('measure',x,y,ch)
    def clear(self,x,y,ch): return self._act('clear',x,y,ch)
    def exit(self):
        self.last_response=self.__dispatch('exit')
        return dict(self.last_response)

def run_child(variant,seed,output):
    offline_guard()
    cfg=config_for(variant)
    sim=load_module(SIM,'jammers_offline_sim')
    sc=sim.generate_practice(3,seed_bytes(seed))
    engine=sim.Engine(sc,record_trace=False)
    output=Path(output)
    action_file=output.with_suffix('.actions.jsonl')
    t0=time.perf_counter()
    with action_file.open('w',encoding='utf-8') as log:
        def dispatch(action,*args):
            response=getattr(engine,action)(*args)
            log.write(json.dumps({'action':action,'args':args,'response':response},ensure_ascii=False)+'\n')
            log.flush()
            return response
        client=ObservationsOnlyClient(dispatch)
        controller=None
        error=None
        try:
            mod=load_module(CONTROLLERS[cfg['controller']],'evaluated_controller')
            kwargs={'tune':cfg.get('tune',{})} if cfg['controller']=='tunable' else cfg.get('kwargs',{})
            controller=mod.Q3ParticleController(client,**kwargs)
            controller.run()
        except Exception as ex:
            error=f'{type(ex).__name__}: {ex}'
            traceback.print_exc()
        summary=engine.summary()
        n=summary['jammer_count']; cleared=summary['cleared_count']; vt=summary['virtual_time_s']
        end={}
        if controller is not None:
            for key in ['known','posterior_same_count','stop_threshold','coverage_done']:
                if callable(getattr(controller,key,None)):
                    try: end[key]=getattr(controller,key)()
                    except Exception: pass
            for key in ['completion_reason','completion_certificate','completion_verified','certificate_report']:
                value=getattr(controller,key,None)
                if value is not None and not callable(value):
                    try: json.dumps(value); end[key]=value
                    except (TypeError,ValueError): pass
        row={'variant':variant,'seed':seed,'N':n,'cleared':cleared,'missing':n-cleared,
             'ok':cleared==n and error is None and summary['exited'] and not summary['timed_out'] and getattr(controller,'completion_verified',True),
             'source_clear_rate':cleared/n,'virtual_time_s':vt,
             'avg_clear_time_s':vt/cleared if cleared else None,
             'diagnostic_time_div_total_s':vt/n,
             'measures':summary['measure_accepted_count'],'switches':summary['channel_switch_count'],
             'clear_fail':summary['clear_failure_count'],'wall_s':time.perf_counter()-t0,
             'error':error,'engine_summary':summary,'controller_end':end}
        dump(output,row)
        return row

def execute_job(variant,seed,run_dir,timeout):
    output=run_dir/variant/f'seed_{seed}.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    env.update({'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    env.pop('Q3_TUNE_JSON',None)
    cmd=[sys.executable,str(Path(__file__).resolve()),'--child','--variants',variant,'--seeds',str(seed),'--output',str(output)]
    t0=time.perf_counter()
    with output.with_suffix('.log').open('w',encoding='utf-8') as log:
        try:
            done=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=ROOT,timeout=timeout)
            error=None if done.returncode==0 else f'process_exit_{done.returncode}'
        except subprocess.TimeoutExpired:
            error=f'wall_timeout_{timeout}s'
    if error is None and output.exists():
        return json.loads(output.read_text(encoding='utf-8'))
    row={'variant':variant,'seed':seed,'N':None,'cleared':0,'missing':None,'ok':False,
         'error':error or 'missing_result','wall_s':time.perf_counter()-t0,'avg_clear_time_s':None}
    dump(output,row)
    return row

def aggregate(rows):
    out=[]
    for name in sorted({r['variant'] for r in rows}):
        data=[r for r in rows if r['variant']==name]
        successes=[r for r in data if r['ok']]
        valid=[r for r in data if r.get('N') is not None]
        times=[r['avg_clear_time_s'] for r in successes]
        groups={}
        for n in range(10,17):
            group=[r for r in valid if r['N']==n]
            if group:
                ts=[r['avg_clear_time_s'] for r in group if r['ok']]
                groups[str(n)]={'runs':len(group),'fullclear':sum(r['ok'] for r in group),
                                'mean_fullclear_time_s':statistics.mean(ts) if ts else None}
        out.append({'variant':name,'runs':len(data),'fullclear_runs':len(successes),
                    'fullclear_rate':len(successes)/len(data),
                    'source_clear_rate':sum(r['cleared'] for r in valid)/sum(r['N'] for r in valid) if len(valid)==len(data) else None,
                    'known_cases_source_clear_rate':sum(r['cleared'] for r in valid)/sum(r['N'] for r in valid) if valid else None,
                    'unknown_case_count':len(data)-len(valid),
                    'missing_sources':sum(r['missing'] for r in valid) if len(valid)==len(data) else None,
                    'errors':sum(bool(r.get('error')) for r in data),
                    'mean_fullclear_time_s':statistics.mean(times) if times else None,
                    'mean_time_per_true_source_s':statistics.mean(r.get('diagnostic_time_div_total_s',r.get('virtual_time_s',r.get('avg_clear_time_s',0.0)*r.get('cleared',0))/r['N']) for r in valid) if valid else None,
                    'weighted_time_per_cleared_source_s':sum(r.get('virtual_time_s',r.get('avg_clear_time_s',0.0)*r.get('cleared',0)) for r in valid)/sum(r['cleared'] for r in valid) if valid and sum(r['cleared'] for r in valid)>0 else None,
                    'max_fullclear_time_s':max(times) if times else None,
                    'p90_fullclear_time_s':float(__import__('numpy').percentile(times,90)) if times else None,
                    'mean_wall_s':statistics.mean(r['wall_s'] for r in data),'groups':groups})
    return out

def print_key_summary(summary):
    print("\n"+"="*78,flush=True)
    print("第三问离线评测关键指标（目标：总体平均 < 200 秒/源）",flush=True)
    print("="*78,flush=True)
    for rec in summary:
        def fmt(v):return "--" if v is None else f"{float(v):.2f}"
        print(f"方案 {rec['variant']} | 全清 {rec['fullclear_runs']}/{rec['runs']} | 源清除率 {100.0*rec['source_clear_rate']:.2f}%",flush=True)
        print(f"  全清局平均的平均: {fmt(rec['mean_fullclear_time_s'])} 秒/源 | 按真实源数总体平均: {fmt(rec['mean_time_per_true_source_s'])} 秒/源 | P90: {fmt(rec['p90_fullclear_time_s'])}",flush=True)
        print(f"  清除源加权平均: {fmt(rec['weighted_time_per_cleared_source_s'])} 秒/源 | 最慢全清局: {fmt(rec['max_fullclear_time_s'])} 秒/源",flush=True)
        parts=[]
        for n in range(10,17):
            g=rec['groups'].get(str(n))
            if g:parts.append(f"N{n}={fmt(g['mean_fullclear_time_s'])}({g['fullclear']}/{g['runs']})")
        print("  分组: "+"  ".join(parts),flush=True)
        target=rec['fullclear_runs']==rec['runs'] and rec['mean_fullclear_time_s'] is not None and rec['mean_fullclear_time_s']<200.0
        print("  目标判定: "+("PASS" if target else "未达到"),flush=True)
    print("="*78,flush=True)

def fingerprints(variants):
    files={SIM,Path(__file__).resolve(),ROOT/'src/baseline_commit10.py'}
    for name in variants:
        cfg=config_for(name)
        files.update({ROOT/'configs'/f'{name}.json',CONTROLLERS[cfg['controller']]})
        if cfg['controller'] in ('complete','efficient','planned'):
            files.add(ROOT/'src/q3_complete_controller.py')
            if cfg['controller']=='planned': files.add(ROOT/'src/q3_efficient_controller.py')
            certificate=ROOT/'src/coverage_certificate.py'
            if certificate.exists(): files.add(certificate)
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError,ValueError):
        pass
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variants',default='baseline')
    ap.add_argument('--seeds',default='0,1,6,7,10,17,34')
    ap.add_argument('--seed-file')
    ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--timeout',type=float,default=120)
    ap.add_argument('--label',default='local')
    ap.add_argument('--child',action='store_true')
    ap.add_argument('--output')
    a=ap.parse_args()
    variants=a.variants.split(',')
    seeds=json.loads(Path(a.seed_file).read_text(encoding='utf-8'))['seeds'] if a.seed_file else [int(x) for x in a.seeds.split(',')]
    if a.child:
        run_child(variants[0],seeds[0],a.output)
        return
    if len(seeds)!=len(set(seeds)): raise ValueError('重复seed不计作独立样本')
    for variant in variants:
        cfg=config_for(variant)
        if not CONTROLLERS[cfg['controller']].exists(): raise FileNotFoundError(CONTROLLERS[cfg['controller']])
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run_dir=ROOT/'runs'/f'{stamp}_{a.label}'
    run_dir.mkdir(parents=True,exist_ok=False)
    manifest={'created_at':datetime.now().isoformat(),'offline':True,'problem':3,
              'variants':{v:config_for(v) for v in variants},'seeds':seeds,'workers':a.workers,
              'timeout_s':a.timeout,'python':sys.version,'hashes':fingerprints(variants),
              'seed_mapping':'sha256(cumcm-offline-generator-key:{integer_seed})',
              'metric':'virtual_time_s / cleared_count; full-clear is a hard ranking gate'}
    dump(run_dir/'manifest.json',manifest)
    rows=[]
    jobs=[(variant,seed) for seed in seeds for variant in variants]
    print(f'RUN_DIR={run_dir}',flush=True)
    with ThreadPoolExecutor(max_workers=max(1,a.workers)) as pool:
        futures=[pool.submit(execute_job,v,s,run_dir,a.timeout) for v,s in jobs]
        for future in as_completed(futures):
            row=future.result(); rows.append(row)
            avg=row.get('avg_clear_time_s')
            avg_text='--' if avg is None else f'{avg:.2f}'
            print(f"[{len(rows)}/{len(jobs)}] {row['variant']} seed={row['seed']} clear={row['cleared']}/{row['N']} avg={avg_text}s {'OK' if row['ok'] else 'FAIL'} wall={row['wall_s']:.1f}s",flush=True)
            with (run_dir/'progress.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(row,ensure_ascii=False)+'\n')
    rows.sort(key=lambda r:(r['variant'],r['seed']))
    result={'run_dir':str(run_dir),'summary':aggregate(rows),'rows':rows,
            'fingerprints_unchanged':fingerprints(variants)==manifest['hashes']}
    dump(run_dir/'results.json',result)
    dump(ROOT/'reports/latest_run.json',{'run_dir':str(run_dir),'results':str(run_dir/'results.json')})
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2),flush=True)
    print_key_summary(result['summary'])
    if not result['fingerprints_unchanged']: print('NOTICE: files added/changed during run; inspect manifest before reuse',flush=True)

if __name__=='__main__': main()

