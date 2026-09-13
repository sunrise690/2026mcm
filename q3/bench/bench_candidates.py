from __future__ import annotations
import contextlib, hashlib, importlib.util, io, json, os, statistics, sys, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
SIM = BENCH / 'jammers_offline_sim.py'
CTRL = ROOT / 'q3' / 'current' / 'tunable_controller.py'
BASECFG = ROOT / 'q3' / 'current' / 'alg_sparseboot3.json'


def load_module(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sys.modules[name] = m
    sp.loader.exec_module(m)
    return m


def local_seed_bytes(seed: int) -> bytes:
    return hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()


def select_cases(k: int):
    sim = load_module('sim_select', SIM)
    out = {n: [] for n in range(10, 17)}
    seed = 1000
    while any(len(v) < k for v in out.values()):
        b = local_seed_bytes(seed)
        sc = sim.generate_practice(3, b)
        n = len(sc.jammers)
        if len(out[n]) < k:
            out[n].append(seed)
        seed += 1
    return out


def patch_service_aware_endpoint(ctrl):
    np = ctrl.np
    def service_aware_order(self, items):
        if not items:
            return []
        if len(items) > int(self.g('exact_tsp_limit')):
            target = None
            w = 0.0
            if int(self.g('route_end_explore')) and self.known() < 16 and self.posterior_same_count() < self.stop_threshold():
                target = self.exploration_point()
                w = float(self.g('route_end_explore_weight'))
            return self.exact_order(items, route_target=target, endpoint_weight=w)
        chs = [ch for ch, _ in items]
        pts = np.asarray([p for _, p in items], float)
        n = len(items)
        starts = [np.asarray(self.c.position, float)] + [pts[j] for j in range(n)]
        edge = np.zeros((n + 1, n), float)
        scale = float(self.g('service_aware_uncertainty_scale'))
        for a, cur in enumerate(starts):
            for i, (ch, target) in enumerate(items):
                b = self.B[ch]
                _, rad = b.estimate()
                target = np.asarray(target, float)
                if rad * scale > float(self.g('service_uncertainty_trigger')):
                    q = self.service_measure_point(b, target, current=cur)
                    edge[a, i] = float(np.linalg.norm(q-cur) + np.linalg.norm(target-q))
                else:
                    edge[a, i] = float(np.linalg.norm(target-cur))
        size = 1 << n
        dp = np.full((size, n), np.inf)
        par = np.full((size, n), -1, np.int16)
        for i in range(n):
            dp[1 << i, i] = edge[0, i]
        for mask in range(1, size):
            for i in range(n):
                if not (mask >> i) & 1:
                    continue
                prev = mask ^ (1 << i)
                if prev == 0:
                    continue
                js = [j for j in range(n) if (prev >> j) & 1]
                vals = [dp[prev, j] + edge[j + 1, i] for j in js]
                k = int(np.argmin(vals))
                dp[mask, i] = vals[k]
                par[mask, i] = js[k]
        mask = size - 1
        obj = dp[mask].copy()
        if int(self.g('route_end_explore')) and self.known() < 16 and self.posterior_same_count() < self.stop_threshold():
            target = self.exploration_point()
            if target is not None:
                tail = np.linalg.norm(pts - np.asarray(target, float), axis=1)
                obj = obj + float(self.g('route_end_explore_weight')) * tail
        last = int(np.argmin(obj))
        order = []
        while mask:
            order.append(last)
            q = int(par[mask, last])
            mask ^= 1 << last
            last = q
        return [(chs[i], pts[i]) for i in reversed(order)]
    ctrl.Q3ParticleController.service_aware_order = service_aware_order


CANDIDATES = {
    'baseline': {},
    'tail025': {'route_end_explore': 1, 'route_end_explore_weight': 0.25},
    'tail050': {'route_end_explore': 1, 'route_end_explore_weight': 0.50},
    'tail075': {'route_end_explore': 1, 'route_end_explore_weight': 0.75},
    'tail100': {'route_end_explore': 1, 'route_end_explore_weight': 1.00},
    'tail125': {'route_end_explore': 1, 'route_end_explore_weight': 1.25},
    'tail075_sparse5': {'route_end_explore': 1, 'route_end_explore_weight': 0.75, 'bootstrap_sparse_max_known': 5},
    'tail075_scan1200': {'route_end_explore': 1, 'route_end_explore_weight': 0.75, 'route_scan_value_s': 1200},
    'tail075_risk1': {'route_end_explore': 1, 'route_end_explore_weight': 0.75, 'stop_thr_10': 0.52, 'stop_thr_11': 0.62, 'stop_thr_12': 0.70, 'stop_thr_13': 0.86},
}


def work(arg):
    label, overrides, seed = arg
    sim = load_module(f'sim_{label}_{seed}', SIM)
    base = json.loads(BASECFG.read_text(encoding='utf-8'))['tune']
    tune = dict(base)
    tune.update(overrides)
    os.environ['Q3_TUNE_JSON'] = json.dumps(tune, separators=(',', ':'))
    ctrl = load_module(f'ctrl_{label}_{seed}', CTRL)
    patch_service_aware_endpoint(ctrl)
    import numpy as np
    class Client:
        def __init__(self, e): self.e=e; self.last_response={}
        @property
        def position(self): return np.array([self.e.x, self.e.y], float)
        @property
        def receiver_channel(self): return self.e.receiver_channel
        def enter(self): self.last_response=self.e.enter(); return self.last_response
        def measure(self,x,y,ch): self.last_response=self.e.measure(x,y,ch); return self.last_response
        def clear(self,x,y,ch): self.last_response=self.e.clear(x,y,ch); return self.last_response
        def exit(self): self.last_response=self.e.exit(); return self.last_response
    sc = sim.generate_practice(3, local_seed_bytes(seed))
    e = sim.Engine(sc, record_trace=False)
    c = Client(e)
    err = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ctrl.run_q3_particle(c)
    except Exception:
        err = traceback.format_exc(limit=2)
    n = len(sc.jammers)
    s = e.summary()
    return {'variant':label,'seed':seed,'N':n,'ok':e.cleared_count==n,'cleared':e.cleared_count,
            'avg':e.virtual_time_s/n,'time':e.virtual_time_s,'measures':s['measure_accepted_count'],
            'switches':s['channel_switch_count'],'clear_fail':s['clear_failure_count'],'error':err}


def summarize(rows):
    groups = {}
    for n in range(10,17):
        rr=[r for r in rows if r['N']==n]
        groups[str(n)]={'runs':len(rr),'fullclear':sum(r['ok'] for r in rr),
                        'mean':statistics.mean(r['avg'] for r in rr),
                        'sd':statistics.pstdev(r['avg'] for r in rr) if len(rr)>1 else 0.0}
    means=[groups[str(n)]['mean'] for n in range(10,17)]
    return {'runs':len(rows),'fullclear':sum(r['ok'] for r in rows),
            'mean_of_N_means':statistics.mean(means),'max_run':max(r['avg'] for r in rows),'groups':groups}


def main():
    if not SIM.exists():
        from sim_payload import write_sim
        write_sim(SIM)
    k=int(os.environ.get('Q3_BENCH_K','2'))
    wanted=os.environ.get('Q3_CANDIDATES','').strip()
    names=[x for x in wanted.split(',') if x] if wanted else list(CANDIDATES)
    cases=select_cases(k)
    args=[]
    for label in names:
        ov=CANDIDATES[label]
        for n in range(10,17):
            for seed in cases[n]: args.append((label,ov,seed))
    workers=int(os.environ.get('Q3_WORKERS','7'))
    rows=[]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(work,a) for a in args]
        for f in as_completed(fs):
            r=f.result(); rows.append(r)
            print('ROW',json.dumps(r,ensure_ascii=False),flush=True)
    result={}
    for label in names:
        rr=[r for r in rows if r['variant']==label]
        result[label]=summarize(rr)
    ranking=sorted(result, key=lambda x:(result[x]['fullclear']<7*k,result[x]['mean_of_N_means']))
    print('RESULT_JSON='+json.dumps({'k':k,'ranking':ranking,'summary':result},ensure_ascii=False,sort_keys=True))

if __name__=='__main__': main()
