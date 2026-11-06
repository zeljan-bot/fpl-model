"""Izvjestaj modela za sljedece kolo.
Poziv:  python3 -I model/report.py [--gw N] [--n 10000] [--no-odds]
Kadrovi: squads.json (JA rucno; STIPE/SRBI automatski iz data/entries ako postoje, inace iz squads.json)
"""
import json, sys, os, statistics as st, math, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core as M
ap = argparse.ArgumentParser(); ap.add_argument('--gw', type=int); ap.add_argument('--n', type=int, default=10000); ap.add_argument('--no-odds', action='store_true'); ap.add_argument('--seed', type=int, default=11)
A = ap.parse_args()
b = M.load_bootstrap(); E = b['elements']; T, TID = M.teams(b)
gw = A.gw or next(e['id'] for e in b['events'] if e['is_next'])
games = M.games_played(b)
FX = M.fixtures(gw, b); FX2 = M.fixtures(gw + 1, b)
LAM = None if A.no_odds else M.lam_from_odds(gw, b)
LAM2 = None if A.no_odds else M.lam_from_odds(gw + 1, b)
PAR = dict(M.PAR_DEFAULT, N=A.n)
PL, lam, sims, avg = M.run(b, games, FX, LAM=LAM, seed=A.seed, **PAR)
sims2 = M.run(b, games, FX2, LAM=LAM2, seed=A.seed + 1, **{**PAR, 'N': 4000})[2] if FX2 else None
N = len(sims); POS = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
price = {e['id']: e['now_cost'] / 10 for e in E}; own = {e['id']: float(e['selected_by_percent']) for e in E}
byid = {e['id']: e for e in E}
def byname(n, t): return next(e['id'] for e in E if e['web_name'] == n and T[e['team']] == t)
def ep(pid, S=None):
    S = S or sims; v = sorted(s[pid] for s in S); return st.mean(v), v[len(v)//10], v[9*len(v)//10]
def team(xi, bench, cap, s):
    played = [p for p in xi if s[p] != 0]; out = [p for p in xi if s[p] == 0]; ben = list(bench)
    for o in out:
        for q in ben:
            if s[q] == 0: continue
            trial = played + [q]; cnt = {k: sum(1 for p in trial if PL[p]['pos'] == k) for k in (2, 3, 4)}
            if PL[q]['pos'] == 1 or (cnt[2] >= 3 and cnt[3] >= 2 and cnt[4] >= 1) or len(trial) < 10:
                played.append(q); ben.remove(q); break
    return sum(s[p] for p in played) + s[cap]
def best_xi(pool, EPf):
    best = None
    for gk in pool['GK']:
        for nd in (3, 4, 5):
            for nm in (2, 3, 4, 5):
                nf = 10 - nd - nm
                if nf < 1 or nf > 3: continue
                D = sorted(pool['DEF'], key=lambda p: -EPf[p])[:nd]; Mi = sorted(pool['MID'], key=lambda p: -EPf[p])[:nm]; F = sorted(pool['FWD'], key=lambda p: -EPf[p])[:nf]
                if len(D) < nd or len(Mi) < nm or len(F) < nf: continue
                xi = [gk] + D + Mi + F; t = sum(EPf[p] for p in xi)
                if best is None or t > best[0]: best = (t, xi, f"{nd}-{nm}-{nf}")
    return best
# ---------- kadrovi ----------
SQ = json.load(open(os.path.join(M.ROOT, 'squads.json')))
def squad_from_entry(name, gw):
    f = os.path.join(M.D, 'entries', f'{name}.json')
    if not os.path.exists(f): return None, None
    e = json.load(open(f)); picks = e.get('picks', {})
    for g in (gw, gw - 1):
        if str(g) in picks and picks[str(g)]:
            ids = [p['element'] for p in picks[str(g)]['picks']]
            pool = {'GK': [], 'DEF': [], 'MID': [], 'FWD': []}
            for pid in ids:
                if pid in PL: pool[POS[PL[pid]['pos']]].append(pid)
            eh = picks[str(g)].get('entry_history', {})
            return pool, dict(bank=eh.get('bank', 0) / 10, gw=g, chip=picks[str(g)].get('active_chip'))
    return None, None
def squad_from_names(sq):
    return {k: [byname(n, t) for n, t in v] for k, v in sq.items() if k in ('GK', 'DEF', 'MID', 'FWD')}
squads = {}
for name, sq in SQ.items():
    pool, info = (None, None)
    if sq.get('auto', True): pool, info = squad_from_entry(name, gw)
    if pool is None: pool = squad_from_names(sq); info = dict(bank=sq.get('bank', 0), gw=None, chip=None)
    squads[name] = (pool, dict(info, ft=sq.get('ft', 1), bank=sq.get('bank', info['bank'])))
# ---------- izvjestaj ----------
src = 'kladionica' if LAM else 'xG model'
print(f"GW{gw} | snimka {os.path.basename(os.readlink(os.path.join(M.D,'bootstrap','latest.json'))) if os.path.islink(os.path.join(M.D,'bootstrap','latest.json')) else 'latest'} | lambda: {src} | N={N}")
print("lambda:")
for h, a, *_ in FX:
    print(f"  {h}-{a} {lam[TID[h]][0]:.2f}:{lam[TID[a]][0]:.2f}  CS {h} {math.exp(-lam[TID[a]][0]):.0%} / {a} {math.exp(-lam[TID[h]][0]):.0%}")
R = {}
for name, (pool, info) in squads.items():
    allp = sum(pool.values(), []); EP1 = {p: ep(p)[0] for p in allp}
    tot, xi, form = best_xi(pool, EP1); bench = [p for p in allp if p not in xi]
    gkb = [p for p in bench if PL[p]['pos'] == 1]; outf = sorted([p for p in bench if PL[p]['pos'] != 1], key=lambda p: -EP1[p])
    caps = []
    for c in xi:
        v = sorted(team(xi, gkb + outf, c, s) for s in sims); caps.append((st.mean(v), v[N//10], v[9*N//10], st.mean(v[:N//10]), c))
    caps.sort(reverse=True); C = caps[0][4]; VC = caps[1][4]
    src_sq = f"kadar iz GW{info['gw']}" if info.get('gw') else 'kadar iz squads.json'
    print(f"\n##### {name} ({src_sq}, FT={info['ft']}, banka {info['bank']}): {form}, EP bez C {tot:.1f}, s C {caps[0][0]:.1f} [{caps[0][1]}-{caps[0][2]}]")
    for p in xi:
        m, lo, hi = ep(p); tag = ' (C)' if p == C else (' (VC)' if p == VC else '')
        nxt = f" | GW+1 {ep(p, sims2)[0]:.1f}" if sims2 else ''
        flag = '' if PL[p]['p_start'] >= 0.9 else f" P(start)={PL[p]['p_start']:.0%}"
        print(f"  {POS[PL[p]['pos']]:3s} {PL[p]['name']:14s} {T[PL[p]['team']]} vs {T[lam[PL[p]['team']][2]]}  {m:4.1f} [{lo}-{hi}]{flag}{nxt}{tag}")
    print("  klupa:", ', '.join(f"{PL[p]['name']} {EP1[p]:.1f}" + (f" ({PL[p]['p_start']:.0%})" if PL[p]['p_start'] < 0.9 else '') for p in gkb + outf), f"| zbroj {sum(EP1[p] for p in bench):.1f}")
    print("  kapetan:", '; '.join(f"{PL[c]['name']} {m:.1f} [{lo}-{hi}] CVaR {cv:.1f}" for m, lo, hi, cv, c in caps[:4]))
    R[name] = (xi, gkb + outf, C, allp, pool, EP1, info, bench)
me = 'JA'
mine = [team(R[me][0], R[me][1], R[me][2], s) for s in sims]
for nm in R:
    if nm == me: continue
    rv = [team(R[nm][0], R[nm][1], R[nm][2], s) for s in sims]; diff = [a - b_ for a, b_ in zip(mine, rv)]
    print(f"\n{me} - {nm}: {st.mean(diff):+.1f}  P({me}>{nm})={sum(1 for x in diff if x > 0)/N:.0%}")
# transferi
xi, benchl, C, allp, pool, EP1, info, bench = R[me]
ft, bank = info['ft'], info['bank']
print(f"\n##### TRANSFERI (FT={ft}, banka {bank}, kazna {'-4' if ft == 0 else '0'})")
base_tot = st.mean(mine); sell = SQ[me].get('sell', {}); rows = []
for out in allp:
    sp = sell.get(PL[out]['name'], price[out]); budget = bank + sp
    cands = [e for e in E if e['element_type'] == PL[out]['pos'] and e['id'] in PL and e['id'] not in allp and e['minutes'] > 300 and e['status'] == 'a' and price[e['id']] <= budget]
    for e in cands:
        if sum(1 for p in allp if PL[p]['team'] == e['team'] and p != out) >= 3: continue
        newpool = {k: [p for p in v if p != out] + ([e['id']] if k == POS[e['element_type']] else []) for k, v in pool.items()}
        EPn = {p: ep(p)[0] for p in sum(newpool.values(), [])}
        t2, xi2, f2 = best_xi(newpool, EPn); b2 = [p for p in sum(newpool.values(), []) if p not in xi2]
        gkb2 = [p for p in b2 if PL[p]['pos'] == 1]; o2 = sorted([p for p in b2 if PL[p]['pos'] != 1], key=lambda p: -EPn[p])
        cap2 = max(xi2, key=lambda p: EPn[p]); v = [team(xi2, gkb2 + o2, cap2, s) for s in sims]
        g1 = st.mean(v) - base_tot; g2 = (ep(e['id'], sims2)[0] - ep(out, sims2)[0]) if sims2 else 0
        rows.append((g1 + g2 - (4 if ft == 0 else 0), g1, g2, PL[out]['name'], e['web_name'], T[e['team']], price[e['id']]))
rows.sort(reverse=True)
print("  (dobitak u postavi ovo kolo + razlika EP sljedece kolo - kazna)")
for r in rows[:8]: print(f"  {r[3]:14s} -> {r[4]:14s} {r[5]} {r[6]:4.1f}  GW {r[1]:+.1f}  GW+1 {r[2]:+.1f}  neto {r[0]:+.1f}")
print(f"\n##### BENCH BOOST: klupa GW{gw} = {sum(EP1[p] for p in bench):.1f}" + (f" | GW{gw+1} = {sum(ep(p, sims2)[0] for p in bench):.1f}" if sims2 else ''))
# iznenadjenje
def haul(pid):
    v = [s[pid] for s in sims]; n = len(v); return sum(1 for x in v if x >= 10) / n, sum(1 for x in v if x >= 7) / n, sorted(v)[int(n * .9)]
print("\n##### IZNENADJENJE KOLA - liga (vlasnistvo <10%, P(start)>=80%), po P(10+)")
for p in sorted([p for p in PL if own[p] < 10 and PL[p]['p_start'] >= 0.8], key=lambda p: -haul(p)[0])[:8]:
    h10, h7, p90 = haul(p); print(f"  {PL[p]['name']:14s} {T[PL[p]['team']]} vs {T[lam[PL[p]['team']][2]]} {price[p]:4.1f} own {own[p]:4.1f}%  EP {ep(p)[0]:.1f}  P(7+) {h7:.0%}  P(10+) {h10:.0%}  P90 {p90}")
print("\n##### IZNENADJENJE KAO KAPETAN - moja postava, po P(10+)")
for p in sorted(xi, key=lambda p: -haul(p)[0])[:5]:
    h10, h7, p90 = haul(p); v = sorted(team(xi, benchl, p, s) for s in sims)
    print(f"  {PL[p]['name']:14s} EP {EP1[p]:.1f}  P(7+) {h7:.0%}  P(10+) {h10:.0%}  P90 {p90} | tim s njim kao C: {st.mean(v):.1f} [{v[N//10]}-{v[9*N//10]}]")
# upozorenja: zuti kartoni (prag 5 do GW19, 10 do GW32, 15 do GW38)
thr = 5 if gw <= 19 else (10 if gw <= 32 else 15)
warn = [byid[p] for p in allp if byid[p]['yellow_cards'] == thr - 1]
if warn: print("\n##### UPOZORENJE: jedan zuti do suspenzije:", ', '.join(e['web_name'] for e in warn))
