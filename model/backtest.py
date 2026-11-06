"""Backtest / provjera modela na odigranim kolima.
Poziv: python3 -I model/backtest.py [--gws 3,4,5] [--n 3000] [--par '{"SCALE":0.87}'] [--odds]
Za svako kolo uzima snimku bootstrapa prije roka (data/bootstrap/YYYYMMDD-HHMM.json) i stvarne bodove iz snimke prije sljedeceg roka.
"""
import json, sys, os, math, statistics as st, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core as M
ap = argparse.ArgumentParser(); ap.add_argument('--gws'); ap.add_argument('--n', type=int, default=3000); ap.add_argument('--par', default='{}'); ap.add_argument('--odds', action='store_true'); ap.add_argument('--out')
A = ap.parse_args()
latest = M.load_bootstrap(); EV = M.deadlines(latest); T, TID = M.teams(latest)
fin = [e['id'] for e in latest['events'] if e['finished']]
GWS = [int(x) for x in A.gws.split(',')] if A.gws else [g for g in fin if g >= 3]
PAR = dict(M.PAR_DEFAULT, **json.loads(A.par)); PAR['N'] = A.n
rows, trows = [], []
for g in GWS:
    s0 = M.snapshot_before(EV[g]); s1 = M.snapshot_before(EV[g + 1]) if g + 1 in EV else None
    if not s0 or not s1: print(f'GW{g}: nema snimke', file=sys.stderr); continue
    d0 = json.load(open(s0)); d1 = json.load(open(s1))
    fx = [f for f in M.fixtures(g, latest) if f[2] is not None]
    LAM = None
    if A.odds:
        cands = sorted(p for p in os.listdir(os.path.join(M.D, 'odds')) if p[0].isdigit() and p[:13] < EV[g].strftime('%Y%m%d-%H%M'))
        if cands: LAM = M.lam_from_odds(g, latest, os.path.join(M.D, 'odds', cands[-1]))
    PL, lam, sims, avg = M.run(d0, g - 1, fx, LAM=LAM, seed=g, **PAR)
    tp0 = {e['id']: (e['total_points'], e['minutes']) for e in d0['elements']}; tp1 = {e['id']: (e['total_points'], e['minutes']) for e in d1['elements']}
    for h, a, hs, as_, *_ in fx: trows.append((g, h, a, lam[TID[h]][0], lam[TID[a]][0], hs, as_))
    for pid, p in PL.items():
        if pid not in tp1 or pid not in tp0: continue
        v = sorted(s[pid] for s in sims)
        rows.append(dict(gw=g, name=p['name'], pos=p['pos'], team=T[p['team']], ep=st.mean(v), p10=v[len(v)//10], p90=v[9*len(v)//10],
                         act=tp1[pid][0] - tp0[pid][0], played=tp1[pid][1] - tp0[pid][1] > 0, p_start=p['p_start']))
    print(f'GW{g}: {len(fx)} utakmica, {len(PL)} igraca, lambda {"kladionica" if LAM else "xG"}', file=sys.stderr)
# ---- metrike ----
err = []; ll = ll0 = bs = bs0 = 0; n = 0; avgg = st.mean([r[5] + r[6] for r in trows]) / 2
for g, h, a, lh, la, hs, as_ in trows:
    for l, act in ((lh, hs), (la, as_)):
        err.append(l - act); n += 1
        ll += -l + act * math.log(l) - math.lgamma(act + 1); ll0 += -avgg + act * math.log(avgg) - math.lgamma(act + 1)
        bs += (math.exp(-l) - (act == 0)) ** 2; bs0 += (math.exp(-avgg) - (act == 0)) ** 2
print(f"\nMOMCADI n={n}: bias lambda {st.mean(err):+.2f}  RMSE {math.sqrt(st.mean(e*e for e in err)):.2f}  LL/utak {ll/n:.4f} (naivni {ll0/n:.4f})  Brier CS {bs/n:.3f} (naivni {bs0/n:.3f})")
def stats(rs, lab):
    if not rs: return
    e = [r['ep'] - r['act'] for r in rs]; cov = st.mean(1 if r['p10'] <= r['act'] <= r['p90'] else 0 for r in rs)
    print(f"{lab:26s} n={len(rs):5d} EP={st.mean(r['ep'] for r in rs):4.2f} stv={st.mean(r['act'] for r in rs):4.2f} bias={st.mean(e):+.2f} MAE={st.mean(abs(x) for x in e):.2f} pokr.P10-P90={cov:.0%}")
S = [r for r in rows if r['p_start'] >= 0.8]
stats(rows, 'svi'); stats(S, 'starteri (P>=80%)')
for pos, l in ((1, 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')): stats([r for r in S if r['pos'] == pos], '  ' + l)
for g in GWS: stats([r for r in S if r['gw'] == g], f'  GW{g}')
S.sort(key=lambda r: r['ep']); k = max(1, len(S) // 5)
print("kvintili EP -> stvarno:", ', '.join(f"{st.mean(r['ep'] for r in S[i*k:(i+1)*k]):.2f}->{st.mean(r['act'] for r in S[i*k:(i+1)*k]):.2f}" for i in range(5)))
xs = [r['ep'] for r in S]; ys = [r['act'] for r in S]; mx, my = st.mean(xs), st.mean(ys)
print(f"Pearson r (starteri) = {sum((x-mx)*(y-my) for x, y in zip(xs, ys))/math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys)):.3f}")
if A.out: json.dump(dict(players=rows, teams=trows, par=PAR), open(A.out, 'w'))
