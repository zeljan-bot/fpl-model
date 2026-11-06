"""Prikupljanje podataka (radi u GitHub Actions). Sprema u data/."""
import json, os, urllib.request, datetime as dt, time
BASE = 'https://fantasy.premierleague.com/api/'
H = {'User-Agent': 'Mozilla/5.0 (fpl-model data fetcher)'}
def get(url, retries=3):
    for i in range(retries):
        try:
            r = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(r, timeout=30) as f: return json.load(f)
        except Exception as e:
            print('WARN', url, e); time.sleep(3)
    return None
def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, 'w'), separators=(',', ':'))
cfg = json.load(open('config.json'))
now = dt.datetime.now(dt.timezone.utc); stamp = now.strftime('%Y%m%d-%H%M')
# 1. bootstrap (službeni FPL)
b = get(BASE + 'bootstrap-static/')
if b:
    save('data/bootstrap/latest.json', b)
    save(f'data/bootstrap/{stamp}.json', b)
    # zadrži najviše 4 snimke dnevno: obriši one unutar istog sata
    files = sorted(f for f in os.listdir('data/bootstrap') if f[0].isdigit())
    keep = {}
    for f in files:
        key = f[:11]  # YYYYMMDD-HH
        keep.setdefault(key, []).append(f)
    for key, fs in keep.items():
        for f in fs[:-1]: os.remove('data/bootstrap/' + f)
    cur = next((e for e in b['events'] if e['is_current']), None)
    nxt = next((e for e in b['events'] if e['is_next']), None)
else:
    cur = nxt = None
# 2. fixtures (rezultati + raspored, službeno)
fx = get(BASE + 'fixtures/')
if fx: save('data/fixtures.json', fx)
# 3. tečajevi (The Odds API) – samo ako postoji ključ
key = os.environ.get('ODDS_API_KEY', '').strip()
if key:
    url = (f'https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={key}&regions={cfg["odds_regions"]}'
           f'&markets=h2h,totals&oddsFormat=decimal&bookmakers={",".join(cfg["odds_bookmakers"])}')
    o = get(url)
    if o is not None:
        save('data/odds/latest.json', {'fetched': now.isoformat(), 'events': o})
        save(f'data/odds/{stamp}.json', {'fetched': now.isoformat(), 'events': o})
# 4. timovi u mini ligi (javno nakon roka)
gws = [g for g in [cur and cur['id'], nxt and nxt['id']] if g]
for name, eid in cfg['entries'].items():
    if not eid: continue
    out = {'summary': get(BASE + f'entry/{eid}/'), 'history': get(BASE + f'entry/{eid}/history/'), 'picks': {}}
    for g in range(max(1, (gws[0] if gws else 1) - 2), (gws[-1] if gws else 1) + 1):
        p = get(BASE + f'entry/{eid}/event/{g}/picks/')
        if p: out['picks'][str(g)] = p
    out['transfers'] = get(BASE + f'entry/{eid}/transfers/')
    save(f'data/entries/{name}.json', out)
if cfg.get('league_id'):
    save('data/league.json', get(BASE + f'leagues-classic/{cfg["league_id"]}/standings/'))
print('done', stamp)
