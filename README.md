# fpl-model

Automatizirani FPL model (Monte Carlo + tržišne λ) za mini ligu "Obala split".

## Što radi
- `.github/workflows/fetch.yml` – GitHub Action, svaka 2 sata pokreće `fetch.py`
- `fetch.py` – povlači službene FPL podatke (bootstrap-static, fixtures), tečajeve (The Odds API) i kadrove
  timova iz mini lige (javno nakon roka) te ih sprema u `data/`
- `model/core.py` – jezgra modela (Poisson utakmice, raspodjela golova po xG/xA, Monte Carlo, kalibrirani parametri)
- `model/report.py` – ispis za sljedeće kolo: postava, kapetan, klupa, transferi, čipovi, rivali, iznenađenje kola
- `model/backtest.py` – provjera modela na odigranim kolima (kalibracija)
- `squads.json` – kadrovi (JA ručno prije roka; rivali automatski iz `data/entries/` kad postoje)
- `config.json` – FPL ID-ovi timova, liga, kladionice

## Postavljanje (jednokratno)
1. Napravi **javni** repozitorij na GitHubu (npr. `fpl-model`) i uploadaj sav sadržaj ovog paketa
   (uključujući skrivenu mapu `.github`).
2. U repozitoriju: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `ODDS_API_KEY`, Value: tvoj ključ s the-odds-api.com
3. U `config.json` upiši FPL ID-ove (broj iz adrese `fantasy.premierleague.com/entry/<ID>/...`):
   `"JA": <tvoj ID>, "STIPE": <ID>, "SRBI": <ID>`, i po želji `league_id` (iz adrese mini lige).
4. **Settings → Actions → General → Workflow permissions → "Read and write permissions"** (da bot smije spremati podatke).
5. Kartica **Actions** → `fetch-fpl-data` → **Run workflow** (prvi ručni start). Nakon toga ide samo, svaka 2 sata.

Provjera: nakon prvog pokretanja u mapi `data/` moraju postojati `bootstrap/latest.json`, `fixtures.json`,
`odds/latest.json` i `entries/*.json`.

## Pokretanje modela
    python3 -I model/report.py            # izvještaj za sljedeće kolo (tečajevi ako postoje)
    python3 -I model/report.py --no-odds  # samo xG λ
    python3 -I model/backtest.py          # provjera na svim odigranim kolima od GW3

## Napomene
- The Odds API besplatno daje 500 poziva mjesečno; svaka 2 sata = ~360 mjesečno.
- Snimke `data/bootstrap/YYYYMMDD-HHMM.json` služe za backtest (snimka prije roka svakog kola).
- Priloženi testni podaci u `data/` zamjenjuju se pravima nakon prvog pokretanja Actiona.
