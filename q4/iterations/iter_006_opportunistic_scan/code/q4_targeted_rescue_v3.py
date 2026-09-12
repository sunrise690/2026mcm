"""Posterior-guided Q4 rescue probes for the supplied official-v3 rules."""
from __future__ import annotations

import hashlib
import math
import numpy as np


def _particles(no_signal_points, count=200000, directional_prior=0.55):
    rounded = np.round(np.asarray(no_signal_points, float), 3)
    digest = hashlib.blake2b(rounded.tobytes(), digest_size=8).digest()
    rng = np.random.default_rng(int.from_bytes(digest, "little"))
    radial = 1770.0 * np.sqrt(rng.random(count))
    angle = rng.uniform(0.0, 2.0 * math.pi, count)
    position = np.column_stack([radial * np.cos(angle), radial * np.sin(angle)])
    radius = rng.uniform(1000.0, 1500.0, count)
    heading = rng.uniform(0.0, 2.0 * math.pi, count)
    heading_u = np.column_stack([np.cos(heading), np.sin(heading)])
    directional = rng.random(count) < float(directional_prior)
    keep = np.ones(count, bool)
    for sensor in no_signal_points:
        delta = np.asarray(sensor, float) - position
        in_range = np.linalg.norm(delta, axis=1) <= radius
        visible = in_range & (~directional | (np.sum(delta * heading_u, axis=1) >= 0.0))
        keep &= ~visible
    return position[keep], radius[keep], heading_u[keep], directional[keep]


def select_probe(belief, current, used, travel_penalty=0.00035):
    pos, radius, heading_u, directional = _particles(belief.get("no_signal_points", []))
    if not len(pos):
        return None, 0.0
    current = np.asarray(current, float)
    used = [np.asarray(q, float) for q in used]
    best = None
    candidates = []
    # Global rings preserve the original posterior-coverage search.
    for ring_radius in (0.0, 500.0, 1000.0, 1400.0, 1750.0):
        angle_values = (0.0,) if ring_radius == 0.0 else np.arange(0.0, 360.0, 10.0)
        for angle_deg in angle_values:
            angle = math.radians(float(angle_deg))
            candidates.append(ring_radius * np.asarray([math.cos(angle), math.sin(angle)]))
    # v361: add local moves around the robot.  The old grid can force a long
    # cross-field jump even when a modest 350--900 m move gives almost the same
    # posterior visibility.  Local candidates reduce both mean time and tail
    # variance without changing the observation model.
    for local_radius in (350.0, 650.0, 900.0):
        for angle_deg in np.arange(0.0, 360.0, 20.0):
            angle = math.radians(float(angle_deg))
            point = current + local_radius * np.asarray([math.cos(angle), math.sin(angle)])
            if float(np.linalg.norm(point)) <= 1800.0 + 1e-9:
                candidates.append(point)
    for point in candidates:
        point = np.asarray(point, float)
        if used and min(float(np.linalg.norm(point - q)) for q in used) < 220.0:
            continue
        delta = point - pos
        in_range = np.linalg.norm(delta, axis=1) <= radius
        visible = in_range & (~directional | (np.sum(delta * heading_u, axis=1) >= 0.0))
        probability = float(np.mean(visible))
        travel_s = float(np.linalg.norm(point - current)) / 5.0
        item = (probability - travel_penalty * travel_s, probability, -travel_s, point)
        if best is None or item[:3] > best[:3]:
            best = item
    if best is None:
        return None, 0.0
    return np.asarray(best[3], float), float(best[1])

def _tail_particles(no_signal_points, count=32000):
    rounded=np.round(np.asarray(no_signal_points,float),3)
    digest=hashlib.blake2b(b'v380-tail'+rounded.tobytes(),digest_size=8).digest()
    rng=np.random.default_rng(int.from_bytes(digest,'little'))
    r0,r1=900.0,1770.0
    radial=np.sqrt(r0*r0+(r1*r1-r0*r0)*rng.random(count))
    angle=rng.uniform(0.0,2.0*math.pi,count)
    pos=np.column_stack([radial*np.cos(angle),radial*np.sin(angle)])
    radius=rng.uniform(1000.0,1500.0,count)
    h=rng.uniform(0.0,2.0*math.pi,count);hu=np.column_stack([np.cos(h),np.sin(h)])
    keep=np.ones(count,bool)
    for sensor in no_signal_points:
        d=np.asarray(sensor,float)-pos
        visible=(np.linalg.norm(d,axis=1)<=radius)&(np.sum(d*hu,axis=1)>=0.0)
        keep&=~visible
    return pos[keep],radius[keep],hu[keep]

def select_state_tail_probe(belief,current,mode='mean',ring_radius=1900.0,travel_penalty=0.00008):
    pos,radius,hu=_tail_particles(belief.get('no_signal_points',[]))
    if not len(pos):return None,0.0
    sang=(np.arctan2(pos[:,1],pos[:,0])%(2.0*math.pi));bins=np.floor(sang/(2.0*math.pi/12)).astype(int)
    cur=np.asarray(current,float);best=None
    for deg in np.arange(0.0,360.0,15.0):
        a=math.radians(float(deg));q=ring_radius*np.asarray([math.cos(a),math.sin(a)])
        d=q-pos;vis=(np.linalg.norm(d,axis=1)<=radius)&(np.sum(d*hu,axis=1)>=0.0)
        mean=float(np.mean(vis))
        if mode=='balanced':
            vals=[]
            for k in range(12):
                m=(bins==k)
                if int(np.sum(m))>=20:vals.append(float(np.mean(vis[m])))
            score=(0.70*float(np.mean(vals))+0.30*float(np.quantile(vals,0.25))) if vals else mean
        else:
            score=mean
        travel_s=float(np.linalg.norm(q-cur))/5.0
        item=(score-travel_penalty*travel_s,score,mean,-travel_s,q)
        if best is None or item[:4]>best[:4]:best=item
    return np.asarray(best[4],float),float(best[2])


def point_visibility_probability(belief, point):
    """Conditional visibility from the same public-response prior as tail probes."""
    pos, radius, heading_u, directional = _particles(belief.get("no_signal_points", []))
    if not len(pos):
        return 0.0
    delta = np.asarray(point, float) - pos
    visible = (np.linalg.norm(delta, axis=1) <= radius) & (
        ~directional | (np.sum(delta * heading_u, axis=1) >= 0.0))
    return float(np.mean(visible))
