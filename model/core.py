"""FPL model v0.3 – jezgra. Podaci: data/bootstrap/*.json (sluzbeni FPL), data/fixtures.json, data/odds/*.json"""
import json, os, random, statistics as st, math, datetime as dt, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')
PAR_DEFAULT = dict(SCALE=0.87, HOME=1.05, AWAY=0.95, K=4, KP=450, GKB=True, SUBP=0.5)  # kalibrirano na GW3-8 (backtest 2.11.2026)

def load_bootstrap(path=None):
    return json.load(open(path or os.path.join(D, 'bootstrap', 'latest.json')))
def snapshots():
    out = []
    for f in sorted(glob.glob(os.path.join(D, 'bootstrap', '[0-9]*.json'))):
        b = os.path.basename(f); t = dt.datetime.strptime(b[:13], '%Y%m%d-%H%M').replace(tzinfo=dt.timezone.utc)
        out.append((t, f))
    return out
def snapshot_before(t):
    c = [p for tt, p in snapshots() if tt < t]
    return c[-1] if c else None
def teams(b):
    T = {t['id']: t['short_name'] for t in b['teams']}; return T, {v: k for k, v in T.items()}
def deadlines(b):
    return {e['id']: dt.datetime.fromisoformat(e['deadline_time'].replace('Z', '+00:00')) for e in b['events']}
def fixtures(gw, b):
    """[(h_short, a_short, hs, as, finished, kickoff)] za kolo gw iz data/fixtures.json"""
    T, _ = teams(b); fx = json.load(open(os.path.join(D, 'fixtures.json')))
    return [(T[f['team_h']], T[f['team_a']], f['team_h_score'], f['team_a_score'], f['finished'], f['kickoff_time']) for f in fx if f['event'] == gw]
def games_played(b):
    """broj odigranih kola prije sljedeceg roka (za normalizaciju xG po utakmici)"""
    return sum(1 for e in b['events'] if e['finished'])

def lam_from_odds(gw, b, path=None):
    """lambda iz tecajeva (Pinnacle ako postoji, inace medijan kladionica). Vraca {short:(lf,la)} ili None."""
    path = path or os.path.join(D, 'odds', 'latest.json')
    if not os.path.exists(path): return None
    o = json.load(open(path))['events']
    NAME = {'Arsenal':'ARS','Aston Villa':'AVL','Bournemouth':'BOU','Brentford':'BRE','Brighton and Hove Albion':'BHA','Chelsea':'CHE',
            'Coventry City':'COV','Crystal Palace':'CRY','Everton':'EVE','Fulham':'FUL','Hull City':'HUL','Ipswich Town':'IPS','Leeds United':'LEE',
            'Liverpool':'LIV','Manchester City':'MCI','Manchester United':'MUN','Newcastle United':'NEW','Nottingham Forest':'NFO','Sunderland':'SUN',
            'Tottenham Hotspur':'TOT','Burnley':'BUR','West Ham United':'WHU','Wolverhampton Wanderers':'WOL','Leicester City':'LEI','Southampton':'SOU'}
    fx = {(h, a) for h, a, *_ in fixtures(gw, b)}
    out = {}
    for ev in o:
        h, a = NAME.get(ev['home_team']), NAME.get(ev['away_team'])
        if (h, a) not in fx: continue
        bk = {x['key']: x for x in ev['bookmakers']}
        src = [bk['pinnacle']] if 'pinnacle' in bk else list(bk.values())
        ph = pd = pa = 0; pov = 0; line = 0; n1 = n2 = 0
        for x in src:
            m = {mm['key']: mm for mm in x['markets']}
            if 'h2h' in m:
                pr = {oc['name']: oc['price'] for oc in m['h2h']['outcomes']}
                inv = {k: 1 / v for k, v in pr.items()}; s = sum(inv.values())
                ph += inv[ev['home_team']] / s; pd += inv['Draw'] / s; pa += inv[ev['away_team']] / s; n1 += 1
            if 'totals' in m:
                oc = {z['name']: z for z in m['totals']['outcomes']}
                if 'Over' in oc and 'Under' in oc:
                    io, iu = 1 / oc['Over']['price'], 1 / oc['Under']['price']; pov += io / (io + iu); line += oc['Over']['point']; n2 += 1
        if not n1: continue
        ph, pd, pa = ph / n1, pd / n1, pa / n1
        if n2: pov, line = pov / n2, line / n2
        else: pov, line = 0.5, 2.5
        lh, la = fit_lambda(ph, pd, pa, line, pov)
        out[h] = (lh, la); out[a] = (la, lh)
    return out or None

def _pois(k, l): return math.exp(-l) * l ** k / math.factorial(k)
def _probs(lh, la):
    ph = pd = pa = 0.0
    for i in range(10):
        for j in range(10):
            p = _pois(i, lh) * _pois(j, la)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    return ph, pd, pa
def _p_over(lh, la, line):
    lt = lh + la
    def half(x): n = int(math.floor(x)); return 1 - sum(_pois(k, lt) for k in range(n + 1))
    def whole(x): n = int(x); po = 1 - sum(_pois(k, lt) for k in range(n + 1)); pp = _pois(n, lt); return po / (1 - pp)
    f = lambda x: whole(x) if abs(x - round(x)) < 1e-9 else half(x)
    if abs(line * 4 - round(line * 4)) < 1e-9 and abs(line * 2 - round(line * 2)) > 1e-9:
        lo = math.floor(line * 2) / 2; return 0.5 * (f(lo) + f(lo + 0.5))
    return f(line)
def fit_lambda(ph, pd, pa, line, pov):
    best = None
    for lt in [x / 50 for x in range(75, 225)]:        # ukupno 1.5-4.5, korak 0.02
        for d in [x / 50 for x in range(-100, 101)]:   # razlika -2..2
            lh = (lt + d) / 2; la = (lt - d) / 2
            if lh <= 0.1 or la <= 0.1: continue
            h, dr, a = _probs(lh, la); e = (h - ph) ** 2 + (a - pa) ** 2 + (_p_over(lh, la, line) - pov) ** 2
            if best is None or e < best[0]: best = (e, lh, la)
    return round(best[1], 3), round(best[2], 3)

def poisson(l):
    L = math.exp(-l); k = 0; p = random.random()
    while p > L: p *= random.random(); k += 1
    return k

def run(d, games, fixtures, N=3000, HOME=1.11, AWAY=0.89, K=4, KP=450, SCALE=1.0, GKB=False, SUBP=0.3, LAM=None, seed=None):
    """fixtures: lista (h_short, a_short, ...). Vraca PL, lam, sims, avg."""
    if seed is not None: random.seed(seed)
    T, TID = teams(d)
    E = d['elements']
    att, dfc = {}, {}
    for t in T:
        pl = [e for e in E if e['team'] == t]
        att[t] = sum(float(e['expected_goals']) for e in pl) / games
        dfc[t] = sum(float(e['expected_goals_conceded']) for e in pl if e['element_type'] == 1) / games
    avg = st.mean(att.values()); w = games / (games + K)
    att = {t: w * v + (1 - w) * avg for t, v in att.items()}
    dfc = {t: w * v + (1 - w) * avg for t, v in dfc.items()}
    lam = {}
    for h, a, *_ in fixtures:
        lh = att[TID[h]] * dfc[TID[a]] / avg * HOME * SCALE; la = att[TID[a]] * dfc[TID[h]] / avg * AWAY * SCALE
        if LAM and h in LAM: lh, la = LAM[h][0], LAM[h][1]
        lam[TID[h]] = (lh, la, TID[a]); lam[TID[a]] = (la, lh, TID[h])
    posmean = {}
    for pos in (1, 2, 3, 4):
        pl = [e for e in E if e['element_type'] == pos and e['minutes'] > 90] or [e for e in E if e['element_type'] == pos]
        posmean[pos] = (st.mean(float(e['expected_goals_per_90']) for e in pl), st.mean(float(e['expected_assists_per_90']) for e in pl))
    PL = {}
    for e in E:
        if e['team'] not in lam: continue
        m = e['minutes']; starts = e['starts']
        p_start = min(1.0, starts / games) if games else 0.5
        cop = e['chance_of_playing_next_round']
        if e['status'] in ('i', 's', 'u', 'n'): p_start = 0
        elif cop is not None: p_start *= cop / 100
        wp = m / (m + KP)
        PL[e['id']] = dict(p_start=p_start, mps=min(90, m / starts) if starts else 60, pos=e['element_type'], team=e['team'],
            xg90=wp * float(e['expected_goals_per_90']) + (1 - wp) * posmean[e['element_type']][0],
            xa90=wp * float(e['expected_assists_per_90']) + (1 - wp) * posmean[e['element_type']][1],
            dc90=float(e['defensive_contribution_per_90']), saves90=e['saves'] / max(m, 1) * 90,
            yc=e['yellow_cards'] / max(starts, 1), name=e['web_name'])
    teamw = {}
    for pid, p in PL.items(): teamw.setdefault(p['team'], []).append(pid)
    sims = []
    for _ in range(N):
        on = {}
        for pid, p in PL.items():
            r = random.random()
            on[pid] = p['mps'] if r < p['p_start'] else (20 if r < p['p_start'] + SUBP * (1 - p['p_start']) else 0)
        goals = {t: poisson(lam[t][0]) for t in lam}
        sc, asst = {}, {}
        for t, g in goals.items():
            ids = [i for i in teamw[t] if on[i] > 0]
            if not ids: continue
            wg = [PL[i]['xg90'] * on[i] for i in ids]; wa = [PL[i]['xa90'] * on[i] for i in ids]
            for _ in range(g):
                s = random.choices(ids, wg)[0]; sc[s] = sc.get(s, 0) + 1
                if random.random() < 0.75:
                    a = random.choices(ids, wa)[0]
                    if a != s: asst[a] = asst.get(a, 0) + 1
        pts = {}
        for pid, p in PL.items():
            m = on[pid]
            if m == 0: pts[pid] = 0; continue
            pos = p['pos']; opp = lam[p['team']][2]; gc = goals[opp]
            pt = 2 if m >= 60 else 1
            g = sc.get(pid, 0); a = asst.get(pid, 0)
            pt += g * {1: 6, 2: 6, 3: 5, 4: 4}[pos] + a * 3
            if pos in (1, 2):
                if m >= 60 and gc == 0: pt += 4
                if gc >= 2: pt -= int(gc * m / 90) // 2
            if pos == 3 and m >= 60 and gc == 0: pt += 1
            if pos == 1: pt += poisson(p['saves90'] * m / 90 * lam[opp][0] / avg) // 3
            dc = poisson(p['dc90'] * m / 90)
            if (pos == 2 and dc >= 10) or (pos in (3, 4) and dc >= 12): pt += 2
            if random.random() < p['yc']: pt -= 1
            if g >= 2: pt += 3
            elif g + a > 0: pt += random.choices([0, 1, 2, 3], [0.3, 0.2, 0.2, 0.3])[0]
            elif pos in (1, 2) and gc == 0 and random.random() < 0.15: pt += 1
            if GKB and pos == 1 and m >= 60: pt += random.choices([0,1,2,3],[0.75,0.1,0.08,0.07])[0]
            pts[pid] = pt
        sims.append(pts)
    return PL, lam, sims, avg

