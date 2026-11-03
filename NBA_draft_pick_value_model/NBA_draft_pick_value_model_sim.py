import pandas as pd
import numpy as np
import time
import json
import statsmodels.api as sm
import pandas as pd
import numpy as np
from typing import Callable, Any
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler
import requests
from requests import Response
from bs4 import BeautifulSoup
import joblib
import requests
from datetime import date
clf = joblib.load("NBA_draft_pick_value_model/win_pred_model.joblib")
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

import re
import unicodedata

SUFFIX_RE = re.compile(r'[\s,]+(jr|sr|ii|iii|iv|v)\.?$', re.IGNORECASE)

def clean_name(s):
    if not isinstance(s, str):
        return s
    try:
        s = s.encode('latin1').decode('utf-8')  # fix mojibake, if present
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    normalized = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in normalized if not unicodedata.combining(c))
    s = SUFFIX_RE.sub('', s.strip())
    return s.strip()
#LOAD TEAM DIM
team_dim = pd.read_csv('NBA_draft_pick_value_model/team_dim.csv')

#LOAD ADVANCED STATS TO GET PLAYER EXP
advanced_historical_df = pd.read_csv('NBA_draft_pick_value_model/NBA_advanced_stats_2000-2026.csv')
player_exp = advanced_historical_df.groupby('name_display').agg(first_season=('season','min')).reset_index()
player_exp['exp'] = 2027 - player_exp['first_season']
player_exp['name_display'] = player_exp['name_display'].apply(clean_name).str.lower().str.replace(".", "", regex=False)
player_exp

#LIVE EPM CALL

api_key: str = os.environ.get("DNT_API_KEY")
def get_epm(date):
    resp = requests.get( "https://dunksandthrees.com/api/v2/epm",
    params = {
        "date":date},
                  headers = {
    "Authorization":api_key,
    "Accept":"application/json"
                  }
    )
    return pd.json_normalize(resp.json())

epm = get_epm(str(date.today()))
epm = epm[['season', 'team_alias', 'player_name', 'oepm', 'depm', 'epm']]
epm['player_name'] = epm['player_name'].apply(clean_name).str.lower().str.replace(".", "", regex=False)
epm[epm['player_name'].str.contains('green')]
#CONCAT HISTORICAL EPM WITH CURRENT
epm_historical = pd.read_csv('NBA_draft_pick_value_model/player_season_epm_2010-26')
epm_historical = epm_historical[['season', 'team_alias', 'player_name', 'off', 'def', 'tot']]
epm_historical = epm_historical.rename(columns={'off':'oepm','def':'depm','tot':'epm'})
epm = pd.concat([epm,epm_historical[epm_historical['season'].astype(int) >= 2024]],ignore_index=True)
epm[epm['player_name'].str.contains('green')]
#CLEAN EPM NAMES
# epm['player_name'] = epm['player_name'].apply(clean_name)
epm.loc[epm['player_name'] == 'ronald holland','player_name'] = 'ron holland'
epm.loc[epm['player_name'] == 'tristan da silva','player_name'] = 'tristan da silva'
# epm.loc[epm['player_name'] == 'aj green','player_name'] = 'A.J. Green'
epm[epm['player_name'].str.contains('green')]
#DEFINE BBREF SCRAPER
class HTMLScraper:
    """Class for scraping the web"""

    proxy: str | None = None
    timeout: int = 10  # seconds to wait before giving up on a request
    max_retries: int = 3
    retry_backoff: int = 15  # base seconds to wait before retrying

    def scrape(self, url: str, parser_fun: Callable) -> Any:
        page = self.get_page(url)
        soup = BeautifulSoup(page.text, "html.parser")
        return parser_fun(soup)

    def get_page(self, url: str) -> Response:
        """
        Sends a GET request with a timeout, and retries with backoff
        if rate-limited or blocked (429/403) or the connection fails.
        """

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                with requests.Session() as session:
                    page = session.get(
                        url,
                        proxies=self._proxies(),
                        headers=headers,
                        timeout=self.timeout,
                    )

                if page.status_code in (429, 403):
                    wait = int(
                        page.headers.get("Retry-After", self.retry_backoff * attempt)
                    )
                    print(f"Blocked ({page.status_code}) on {url}, waiting {wait}s (attempt {attempt})")
                    time.sleep(wait)
                    continue

                page.raise_for_status()
                return page

            except requests.exceptions.RequestException as e:
                print(f"Request failed for {url}: {e} (attempt {attempt})")
                if attempt == self.max_retries:
                    raise
                time.sleep(self.retry_backoff * attempt)

        raise RuntimeError(f"Exhausted retries fetching {url}")

    def _proxies(self) -> dict | None:
        """If the object is initialized with a proxy then use it"""
        if self.proxy:
            return {"https": self.proxy, "http": self.proxy}
        return None

#SCRAPE ADVANCED

from dataclasses import dataclass
from bs4 import BeautifulSoup, Comment


@dataclass
class BaskRefPlayerStatsScraper(HTMLScraper):
    """Scrapes league-wide per-player stat tables (advanced, shooting, etc.)."""

    base_url: str = "https://www.basketball-reference.com"

    STAT_TYPE_CONFIG = {
        "advanced": {
            "url_suffix": "advanced",
            "table_ids": ["advanced", "advanced_stats"],
        },
        "shooting": {
            "url_suffix": "shooting",
            "table_ids": ["shooting", "shooting_stats"],
        },
        "per_game": {
            "url_suffix": "per_game",
            "table_ids": ["per_game_stats", "per_game"],
        },
    }

    def get_stats(self, season_year: int, stat_type: str) -> list[dict]:
        config = self.STAT_TYPE_CONFIG[stat_type]
        url = f"{self.base_url}/leagues/NBA_{season_year}_{config['url_suffix']}.html"
        return self.scrape(url, lambda page: self._parse_stats_table(page, config["table_ids"]))

    def debug_list_tables(self, season_year: int, stat_type: str) -> dict:
        config = self.STAT_TYPE_CONFIG[stat_type]
        url = f"{self.base_url}/leagues/NBA_{season_year}_{config['url_suffix']}.html"

        def _list_ids(page: BeautifulSoup) -> dict:
            direct_ids = [t.get("id") for t in page.find_all("table")]
            comment_ids = []
            for comment in page.find_all(string=lambda t: isinstance(t, Comment)):
                if "<table" in comment:
                    inner = BeautifulSoup(comment, "html.parser")
                    comment_ids.extend(t.get("id") for t in inner.find_all("table"))
            return {"direct": direct_ids, "in_comments": comment_ids}

        return self.scrape(url, _list_ids)

    def _parse_stats_table(self, page: BeautifulSoup, table_ids: list[str]) -> list[dict]:
        table = None
        for tid in table_ids:
            table = page.select_one(f"#{tid}")
            if table is not None:
                break

        if table is None:
            for tid in table_ids:
                table = self._find_table_in_comments(page, tid)
                if table is not None:
                    break

        if table is None:
            raise ValueError(
                f"Could not locate a stats table with any of ids {table_ids}. "
                "Run debug_list_tables() to see available table ids."
            )

        rows = []
        for tr in table.select("tbody tr"):
            if tr.get("class") and "thead" in tr.get("class"):
                continue
            row = {}
            for cell in tr.select("td, th"):
                stat = cell.get("data-stat")
                if stat:
                    row[stat] = cell.text.strip()
            if row:
                rows.append(row)
        return rows

    @staticmethod
    def _find_table_in_comments(page: BeautifulSoup, id_substring: str):
        for comment in page.find_all(string=lambda t: isinstance(t, Comment)):
            if "<table" in comment and id_substring in comment:
                inner = BeautifulSoup(comment, "html.parser")
                found = inner.select_one(f"table[id*={id_substring}]")
                if found is not None:
                    return found
        return None

import time
import random
import pandas as pd

stats_scraper = BaskRefPlayerStatsScraper()  # from earlier in this conversation

seasons = [2027]  # 2017 through 2026 inclusive

advanced_data_list = []
failed_pulls = []

for i, season in enumerate(seasons, 1):
    print(f"\r{i}/{len(seasons)}: {season} advanced stats", end="", flush=True)
    try:
        rows = stats_scraper.get_stats(season, 'advanced')
        for row in rows:
            row['season'] = season
        advanced_data_list.extend(rows)
    except Exception as e:
        print(f"\n⚠️ Failed {season}: {type(e).__name__}: {e}")
        failed_pulls.append((season, str(e)))
    time.sleep(random.uniform(3, 5))

advanced_stats_df = pd.DataFrame(advanced_data_list)
print(f"\n\nTotal rows: {len(advanced_stats_df)}")
if failed_pulls:
    print(f"{len(failed_pulls)} seasons failed: {failed_pulls}")

advanced_stats_df
#NBA . COM SCRAPER
# nba.com slugs that aren't just the last word of the team name, lowercased
SLUG_OVERRIDES = {
    "Portland Trail Blazers": "blazers",
    "Philadelphia 76ers": "sixers",
}

# defunct franchise rows in team_dim
DEFUNCT_ALIASES = {"NOH", "NJN"}


@dataclass
class NBATeamPageScraper(HTMLScraper):
    """
    Scrapes nba.com/team/{team_id}/{slug}. The page is a Next.js app, so the
    data lives in the __NEXT_DATA__ JSON blob rather than the visible HTML.
    """

    base_url: str = "https://www.nba.com"

    def get_page_data(self, team_id: int, slug: str) -> dict:
        """Returns props.pageProps, the part of __NEXT_DATA__ holding the content."""
        url = f"{self.base_url}/team/{team_id}/{slug}"
        return self.scrape(url, self._parse_next_data)

    def debug_keys(self, team_id: int, slug: str, max_depth: int = 2) -> None:
        """Prints the JSON structure so you can see what's available."""
        data = self.get_page_data(team_id, slug)

        def _walk(obj, path="pageProps", depth=0):
            if depth > max_depth:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kind = type(v).__name__
                    size = f"[{len(v)}]" if isinstance(v, (list, dict)) else ""
                    print("  " * depth + f"{path}.{k}: {kind}{size}")
                    _walk(v, f"{path}.{k}", depth + 1)

        _walk(data)

    def get_team(self, team_id: int, slug: str) -> dict:
        """Returns {'roster': [...], 'coaches': [...], 'team_info': {...}}."""
        data = self.get_page_data(team_id, slug)

        roster = self._find_record_list(data, "PLAYER_ID")
        coaches = self._find_record_list(data, "COACH_ID") or self._find_record_list(data, "COACH_NAME")
        team_info = data.get("team") if isinstance(data.get("team"), dict) else {}

        for rec in roster:
            rec["team_id"] = team_id
        for rec in coaches:
            rec["team_id"] = team_id

        # keep only flat (scalar) fields from team_info so it fits in a row
        flat_info = {k: v for k, v in team_info.items() if not isinstance(v, (dict, list))}
        flat_info["team_id"] = team_id

        return {"roster": roster, "coaches": coaches, "team_info": flat_info}

    # private functions

    @staticmethod
    def _parse_next_data(page: BeautifulSoup) -> dict:
        script = page.find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            raise ValueError(
                "No __NEXT_DATA__ script found. nba.com may have blocked the "
                "request or served a different page."
            )
        return json.loads(script.string).get("props", {}).get("pageProps", {})

    @classmethod
    def _find_record_list(cls, obj, marker_key: str) -> list[dict]:
        """
        Recursively finds the first list of dicts whose records contain
        marker_key (e.g. PLAYER_ID for the roster), so it doesn't break if
        nba.com moves things around in the JSON.
        """
        if isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj) and marker_key in obj[0]:
                return [dict(x) for x in obj]
            for item in obj:
                found = cls._find_record_list(item, marker_key)
                if found:
                    return found
        elif isinstance(obj, dict):
            for v in obj.values():
                found = cls._find_record_list(v, marker_key)
                if found:
                    return found
        return []


def team_slug(team_name: str) -> str:
    return SLUG_OVERRIDES.get(team_name, team_name.split(" ")[-1].lower())


# ============================================================
# RUN IT FOR ALL 30 TEAMS
# ============================================================

team_page_scraper = NBATeamPageScraper()
current_teams = team_dim[~team_dim["team_alias"].isin(DEFUNCT_ALIASES)]

all_roster, all_coaches, all_info, failed = [], [], [], []

for i, t in enumerate(current_teams.itertuples(), 1):
    slug = team_slug(t.team)
    print(f"\r{i}/{len(current_teams)}: {t.team_alias}", end="", flush=True)
    try:
        result = team_page_scraper.get_team(t.team_id, slug)
        all_roster.extend(result["roster"])
        all_coaches.extend(result["coaches"])
        all_info.append(result["team_info"])
        if not result["roster"]:
            print(f"\n⚠️ No roster found for {t.team_alias} — run debug_keys({t.team_id}, '{slug}')")
    except Exception as e:
        print(f"\n⚠️ Failed {t.team_alias}: {type(e).__name__}: {e}")
        failed.append((t.team_alias, str(e)))
    time.sleep(random.uniform(3, 5))

nba_roster_df = pd.DataFrame(all_roster)
nba_coaches_df = pd.DataFrame(all_coaches)
nba_team_info_df = pd.DataFrame(all_info)

# join keys matching the rest of the notebook
nba_roster_df = pd.merge(nba_roster_df, team_dim[["team_id", "team_alias"]], how="left", on="team_id")
if "PLAYER" in nba_roster_df:
    nba_roster_df["player"] = (
        nba_roster_df["PLAYER"].apply(clean_name).str.lower().str.replace(".", "", regex=False)
    )

print(f"\n\nRoster rows: {len(nba_roster_df)} | Coaches: {len(nba_coaches_df)} | Teams: {len(nba_team_info_df)}")
if failed:
    print(f"{len(failed)} teams failed: {failed}")

# nba_roster_df.to_csv("NBA_com_rosters_2026-27.csv", index=False)
nba_roster_df['season'] = 2027
nba_roster_df.head()
#GET ROSTER AND MPG
stats_scraper = BaskRefPlayerStatsScraper()

per_game_df = pd.DataFrame(stats_scraper.get_stats(2027, 'per_game'))
per_game_df['season'] = 2027

# drop the League Average row
per_game_df = per_game_df[per_game_df['name_display'] != 'League Average']

# traded players: keep the 2TM/3TM total row, drop the individual team rows
multi_team_labels = {'2TM', '3TM', '4TM', '5TM'}
has_agg = per_game_df.groupby('name_display')['team_name_abbr'].transform(
    lambda s: s.isin(multi_team_labels).any()
)
per_game_df = per_game_df[~(has_agg & ~per_game_df['team_name_abbr'].isin(multi_team_labels))].copy()

# numeric columns
non_numeric = {'name_display', 'team_name_abbr', 'pos', 'awards'}
for col in per_game_df.columns.difference(non_numeric):
    per_game_df[col] = pd.to_numeric(per_game_df[col], errors='coerce')

per_game_df['name_display'] = (
    per_game_df['name_display'].apply(clean_name).str.lower().str.replace('.', '', regex=False)
)

nba_roster_df['player'] = (
    nba_roster_df['player'].apply(clean_name).str.lower().str.replace('.', '', regex=False)
)
# per_game_df.to_csv('NBA_per_game_2027.csv', index=False)
per_game_df.loc[per_game_df['team_name_abbr'] == 'BRK', 'team_name_abbr'] = 'BKN'
per_game_df.loc[per_game_df['team_name_abbr'] == 'CHO', 'team_name_abbr'] = 'CHA'
per_game_df.loc[per_game_df['team_name_abbr'] == 'PHO', 'team_name_abbr'] = 'PHX'
nba_roster_df.loc[nba_roster_df['team_alias'] == 'BRK', 'team_alias'] = 'BKN'
nba_roster_df.loc[nba_roster_df['team_alias'] == 'CHO', 'team_alias'] = 'CHA'
nba_roster_df.loc[nba_roster_df['team_alias'] == 'PHO', 'team_alias'] = 'PHX'
nba_roster_df.loc[nba_roster_df['player'] == 'ronald holland','player'] = 'ron holland'

roster_mpg = pd.merge(nba_roster_df[['player','team_alias','season']],per_game_df[['name_display','mp_per_g','team_name_abbr']],how='left',left_on=['player','team_alias'],right_on=['name_display','team_name_abbr'])
roster_mpg['team_mpg_rk'] = roster_mpg.groupby('team_alias')['mp_per_g'].rank(method='first',ascending=False)
roster_mpg.loc[roster_mpg['player'] == 'ronald holland','player'] = 'ron holland'

roster_mpg

roster_mpg['player'] = roster_mpg['player'].apply(clean_name)
player_totals = pd.read_csv('NBA_draft_pick_value_model/NBA_player_totals_2000-2026.csv')
player_totals['name_display'] = (
    player_totals['name_display'].apply(clean_name).str.lower().str.replace('.', '', regex=False)
)
multi_team_labels = {'2TM', '3TM', '4TM', '5TM'}

has_agg = player_totals.groupby(['name_display', 'season'])['team_name_abbr'].transform(
    lambda s: s.isin(multi_team_labels).any()
)
is_individual_team_row = ~player_totals['team_name_abbr'].isin(multi_team_labels)
drop_mask = has_agg & is_individual_team_row
player_totals = player_totals[~drop_mask].copy()
player_totals['szn_ago'] = player_totals.groupby('name_display')['season'].rank(ascending=False, method='dense')

player_missed_game_pct = player_totals[player_totals['szn_ago'] <= 3].copy()
player_missed_game_pct['gp_pct'] = player_missed_game_pct['games'] / 82
player_missed_game_pct = player_missed_game_pct.groupby('name_display').agg({'gp_pct': 'median'}).reset_index()

gp_pct_df = pd.merge(roster_mpg, player_missed_game_pct[['name_display', 'gp_pct']], how='left', left_on='player', right_on='name_display')
gp_pct_df['gp_pct'] = gp_pct_df['gp_pct'].fillna(0.75)
gp_pct_df = gp_pct_df[['player', 'team_alias','gp_pct']]
gp_pct_df['gp_pct'] = gp_pct_df['gp_pct'].clip(upper=0.99)# gp_pct_df['player'] = gp_pct_df['player'].replace('.', '')
gp_pct_df['player'] = gp_pct_df['player'].str.lower()
last = player_totals.sort_values('season').groupby('name_display').tail(1)
last = last.assign(mpg_last=last['mp'] / last['games'].replace(0, np.nan))[['name_display', 'mpg_last']]
roster_mpg = roster_mpg.merge(last.rename(columns={'name_display': 'nd_last'}),
                              how='left', left_on='player', right_on='nd_last')
roster_mpg['mp_per_g'] = roster_mpg['mp_per_g'].fillna(roster_mpg['mpg_last'])
roster_mpg = roster_mpg.drop(columns=['nd_last', 'mpg_last'])
gp_pct_df
#CALCULATE ADVANCED STAT SCORE
multi_team_labels = {'2TM', '3TM', '4TM', '5TM'}

has_agg = advanced_stats_df.groupby(['name_display', 'season'])['team_name_abbr'].transform(
    lambda s: s.isin(multi_team_labels).any()
)
is_individual_team_row = ~advanced_stats_df['team_name_abbr'].isin(multi_team_labels)
drop_mask = has_agg & is_individual_team_row
advanced_stats_df = advanced_stats_df[~drop_mask].copy()

advanced_stats_df = advanced_stats_df[~(advanced_stats_df['name_display'] == 'League Average')]
advanced_stats_df.loc[advanced_stats_df['team_name_abbr'] == 'BRK', 'team_name_abbr'] = 'BKN'
advanced_stats_df.loc[advanced_stats_df['team_name_abbr'] == 'CHO', 'team_name_abbr'] = 'CHA'
advanced_stats_df.loc[advanced_stats_df['team_name_abbr'] == 'PHO', 'team_name_abbr'] = 'PHX'

advanced_stats_df['name_display'] = advanced_stats_df['name_display'].apply(clean_name).str.lower().str.replace(".", "", regex=False)
advanced_stats_df = advanced_stats_df.drop(columns='season')
int_df = pd.merge(roster_mpg,advanced_stats_df,how='left',left_on='player',right_on='name_display')
final_stats_df = pd.merge(int_df,epm[['player_name','epm','season']],how='left',left_on=['player','season'],right_on=['player_name','season'])
final_stats_df = final_stats_df[final_stats_df['per']!= '']
final_stats_df['per'] = final_stats_df['per'].astype(float)
final_stats_df['ws'] = final_stats_df['ws'].astype(float)
final_stats_df['epm'] = final_stats_df['epm'].astype(float)
final_stats_df['bpm'] = final_stats_df['bpm'].astype(float)

final_stats_df['zs_bpm'] = final_stats_df.groupby('season')['bpm'].transform(lambda x: (x - x.min()) * 10 /(x.max() - x.min()))
final_stats_df['zs_per'] = final_stats_df.groupby('season')['per'].transform(lambda x: (x - x.min()) * 10 /(x.max() - x.min()))
final_stats_df['zs_ws'] = final_stats_df.groupby('season')['ws'].transform(lambda x: (x - x.min()) * 10 /(x.max() - x.min()))
final_stats_df['zs_epm'] = final_stats_df.groupby('season')['epm'].transform(lambda x: (x - x.min()) * 10 /(x.max() - x.min()))
final_stats_df['mp'] = final_stats_df['mp'].fillna(0)
# final_stats_df = pd.merge(final_stats_df,player_exp,how='left',left_on='player_name',right_on='name_display')
# final_stats_df['exp'] = final_stats_df['season'] + 1 - final_stats_df['first_season']
# final_stats_df.loc[final_stats_df['exp'].isna(),'exp'] = 1
final_stats_df = final_stats_df[final_stats_df['season'] == 2027]
adv_stat_weights = [final_stats_df['zs_epm'],
(0.65 * final_stats_df['zs_epm']) + (0.05 * final_stats_df['zs_bpm']) + (0.05 * final_stats_df['zs_per']) + (0.25 * final_stats_df['zs_ws'])  ,
    (0.25 * final_stats_df['zs_epm']) + (0.15 * final_stats_df['zs_bpm']) + (0.30 * final_stats_df['zs_per']) + (0.30 * final_stats_df['zs_ws'])
]
conditions = [
    final_stats_df['zs_ws'].isna(),
    final_stats_df['mp'].astype(int) <= 200,
    final_stats_df['season'] == 2027
]
final_stats_df['advanced_stat_score'] = np.select(conditions,adv_stat_weights)
final_stats_df['advanced_stat_score'] = final_stats_df['advanced_stat_score'].fillna(
    final_stats_df['advanced_stat_score'].quantile(0.10)
)
final_stats_df = final_stats_df.drop(columns=['team_name_abbr_x','team_name_abbr_y'])
final_stats_df = final_stats_df.rename(columns={'team_alias':'team_name_abbr'})
final_stats_df.loc[final_stats_df['team_name_abbr'] == 'BRK', 'team_name_abbr'] = 'BKN'
final_stats_df.loc[final_stats_df['team_name_abbr'] == 'CHO', 'team_name_abbr'] = 'CHA'
final_stats_df.loc[final_stats_df['team_name_abbr'] == 'PHO', 'team_name_abbr'] = 'PHX'
final_stats_df = final_stats_df[[ 'player', 'age', 'team_name_abbr', 'pos', 'games',
       'games_started', 'mp', 'per', 'ts_pct', 'fg3a_per_fga_pct',
       'fta_per_fga_pct', 'orb_pct', 'drb_pct', 'trb_pct', 'ast_pct',
       'stl_pct', 'blk_pct', 'tov_pct', 'usg_pct', 'ows', 'dws', 'ws',
       'ws_per_48', 'obpm', 'dbpm', 'bpm', 'vorp', 'awards', 'season','player_name'
        , 'epm', 'zs_bpm', 'zs_per', 'zs_ws', 'zs_epm', 'advanced_stat_score']]
final_stats_df = final_stats_df.rename(columns={'name_display_x':'name_display'})
# final_stats_df[final_stats_df['name_display'].str.contains('harper')]
final_stats_df
#SCHEDULE SCRAPER
#SCHEDULE / GAMES
from dataclasses import dataclass
import re
import time
import random
import pandas as pd
from bs4 import BeautifulSoup, Comment


@dataclass
class BaskRefScheduleScraper(HTMLScraper):
    """
    Scrapes a season's schedule/results from /leagues/NBA_{year}_games.html.

    Note: the base page only shows the FIRST month (October). Every other month
    lives on its own page (NBA_{year}_games-november.html, etc.), so this class
    reads the month links off the base page and scrapes each one.
    """

    base_url: str = "https://www.basketball-reference.com"

    # fallback if the month filter links can't be found
    DEFAULT_MONTHS = [
        "october", "november", "december", "january",
        "february", "march", "april", "may", "june",
    ]

    def get_season_schedule(self, season_year: int, pause: tuple = (3, 5)) -> list[dict]:
        """Scrape every month of the season. Returns a flat list of game dicts."""
        month_urls = self.get_month_urls(season_year)

        all_games = []
        for i, (month, url) in enumerate(month_urls, 1):
            print(f"\r{i}/{len(month_urls)}: {month}", end="", flush=True)
            try:
                rows = self.scrape(url, self._parse_schedule_table)
                for row in rows:
                    row["season"] = season_year
                    row["month"] = month
                all_games.extend(rows)
            except Exception as e:
                # months with no games yet (or playoffs not scheduled) can 404
                print(f"\n⚠️ Skipped {month}: {type(e).__name__}: {e}")
            time.sleep(random.uniform(*pause))
        print()
        return all_games

    def get_month(self, season_year: int, month: str | None = None) -> list[dict]:
        """Scrape a single month. month=None scrapes the base page (first month)."""
        suffix = f"-{month.lower()}" if month else ""
        url = f"{self.base_url}/leagues/NBA_{season_year}_games{suffix}.html"
        rows = self.scrape(url, self._parse_schedule_table)
        for row in rows:
            row["season"] = season_year
            row["month"] = month
        return rows

    def get_month_urls(self, season_year: int) -> list[tuple[str, str]]:
        """Reads the month filter links from the base page."""
        url = f"{self.base_url}/leagues/NBA_{season_year}_games.html"

        def _parse_links(page: BeautifulSoup) -> list[tuple[str, str]]:
            pattern = re.compile(rf"/leagues/NBA_{season_year}_games-(\w+)\.html")
            seen, links = set(), []
            for a in page.select("div.filter a, a[href]"):
                m = pattern.search(a.get("href", ""))
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    links.append((m.group(1), self.base_url + m.group(0)))
            return links

        links = self.scrape(url, _parse_links)
        if not links:
            links = [
                (m, f"{self.base_url}/leagues/NBA_{season_year}_games-{m}.html")
                for m in self.DEFAULT_MONTHS
            ]
        return links

    def debug_list_tables(self, season_year: int, month: str | None = None) -> dict:
        suffix = f"-{month.lower()}" if month else ""
        url = f"{self.base_url}/leagues/NBA_{season_year}_games{suffix}.html"

        def _list_ids(page: BeautifulSoup) -> dict:
            direct_ids = [t.get("id") for t in page.find_all("table")]
            comment_ids = []
            for comment in page.find_all(string=lambda t: isinstance(t, Comment)):
                if "<table" in comment:
                    inner = BeautifulSoup(comment, "html.parser")
                    comment_ids.extend(t.get("id") for t in inner.find_all("table"))
            return {"direct": direct_ids, "in_comments": comment_ids}

        return self.scrape(url, _list_ids)

    # private functions

    def _parse_schedule_table(self, page: BeautifulSoup) -> list[dict]:
        table = page.select_one("#schedule")
        if table is None:
            table = self._find_table_in_comments(page, "schedule")
        if table is None:
            raise ValueError(
                "Could not locate the schedule table. "
                "Run debug_list_tables() to see available table ids."
            )

        rows = []
        for tr in table.select("tbody tr"):
            # skip repeated header rows and the "Playoffs" divider row
            classes = tr.get("class") or []
            if "thead" in classes:
                continue

            row = {}
            for cell in tr.select("td, th"):
                stat = cell.get("data-stat")
                if not stat:
                    continue
                row[stat] = cell.text.strip()

                # pull tricodes / ids out of the links (more reliable than names for joins)
                link = cell.find("a")
                href = link.get("href", "") if link else ""
                if stat == "visitor_team_name" and href:
                    row["visitor_abbr"] = href.split("/")[2]
                elif stat == "home_team_name" and href:
                    row["home_abbr"] = href.split("/")[2]
                elif stat == "box_score_text" and href:
                    row["game_id"] = href.split("/")[-1].replace(".html", "")

            if row:
                rows.append(row)
        return rows

    @staticmethod
    def _find_table_in_comments(page: BeautifulSoup, id_substring: str):
        for comment in page.find_all(string=lambda t: isinstance(t, Comment)):
            if "<table" in comment and id_substring in comment:
                inner = BeautifulSoup(comment, "html.parser")
                found = inner.select_one(f"table[id*={id_substring}]")
                if found is not None:
                    return found
        return None


# ============================================================
# RUN IT
# ============================================================

schedule_scraper = BaskRefScheduleScraper()
games_df = pd.DataFrame(schedule_scraper.get_season_schedule(2027))

# light cleanup
games_df["game_date"] = pd.to_datetime(games_df["date_game"], format="%a, %b %d, %Y", errors="coerce")
for col in ["visitor_pts", "home_pts"]:
    games_df[col] = pd.to_numeric(games_df[col], errors="coerce")
if "attendance" in games_df:
    games_df["attendance"] = pd.to_numeric(games_df["attendance"].str.replace(",", ""), errors="coerce")
games_df["played"] = games_df["home_pts"].notna()

print(f"Total games: {len(games_df)}  |  played: {games_df['played'].sum()}")
home_teams = games_df[['game_date','season','home_team_name','home_abbr','visitor_team_name','visitor_abbr','home_pts','visitor_pts']]
home_teams = home_teams.rename(columns={'home_team_name':'team_name','home_abbr':'team_abbr','visitor_team_name':'team_name_opponent','visitor_abbr':'team_abbr_opponent',
                           'home_pts':'pts','visitor_pts':'pts_opponent'})
home_teams['is_home'] = 1
away_teams = games_df[['game_date','season','visitor_team_name','visitor_abbr','home_team_name','home_abbr','visitor_pts','home_pts']]
away_teams = away_teams.rename(columns={'home_team_name':'team_name_opponent','home_abbr':'team_abbr_opponent','visitor_team_name':'team_name','visitor_abbr':'team_abbr',
                           'home_pts':'pts_opponent','visitor_pts':'pts'})
away_teams['is_home'] = 0
full_games_df = pd.concat([home_teams,away_teams])
full_games_df['win'] = np.where(full_games_df['pts'] > full_games_df['pts_opponent'],1,0)

season_team = pd.merge(full_games_df['season'].drop_duplicates(), full_games_df['team_abbr'].drop_duplicates(), how='cross')

new_full_box = []
for season, team in zip(season_team['season'], season_team['team_abbr']):
    temp_df = full_games_df[(full_games_df['season'] == season) & (full_games_df['team_abbr'] == team)]
    temp_df = temp_df.sort_values(by='game_date',ascending=True)
    temp_df['days_between'] = temp_df.groupby(['season', 'team_abbr'])['game_date'].diff()
    temp_df['two_games_ago'] = temp_df['game_date'] - temp_df['game_date'].shift(2)
    temp_df['three_games_ago'] = temp_df['game_date'] - temp_df['game_date'].shift(3)
    is_target = (temp_df["is_home"] == True).astype(int)
    temp_df["rows_ago"] = (
        is_target.groupby((is_target == 1).cumsum()).cumcount()
    )
    new_full_box.append(temp_df)
new_full_box_df = pd.concat(new_full_box)
new_full_box_df['is_b2b'] = np.where(new_full_box_df['days_between'] <= pd.to_timedelta(1, unit='D'), 1, 0)
new_full_box_df['is_home'] = new_full_box_df['is_home'].astype(int)
new_full_box_df = pd.merge(new_full_box_df, new_full_box_df[['team_abbr','game_date', 'is_b2b']], how='left', left_on=['game_date', 'team_abbr_opponent'], right_on=['game_date', 'team_abbr'], suffixes=[None, '_opp'])
new_full_box_df.loc[new_full_box_df['team_abbr'] == 'BRK', 'team_abbr'] = 'BKN'
new_full_box_df.loc[new_full_box_df['team_abbr'] == 'CHO', 'team_abbr'] = 'CHA'
new_full_box_df.loc[new_full_box_df['team_abbr'] == 'PHO', 'team_abbr'] = 'PHX'
new_full_box_df.loc[new_full_box_df['team_abbr_opponent'] == 'BRK', 'team_abbr_opponent'] = 'BKN'
new_full_box_df.loc[new_full_box_df['team_abbr_opponent'] == 'CHO', 'team_abbr_opponent'] = 'CHA'
new_full_box_df.loc[new_full_box_df['team_abbr_opponent'] == 'PHO', 'team_abbr_opponent'] = 'PHX'
new_full_box_df['is_played'] = np.where(~new_full_box_df['pts'].isna(),1,0)
new_full_box_df['season_game_no'] = new_full_box_df.groupby('team_abbr')['game_date'].rank(method='first',ascending=True)
new_full_box_df
#INJURY SCRAPER

#INJURIES (ESPN) - JSON API version
from dataclasses import dataclass
from datetime import date
import re
import pandas as pd


@dataclass
class ESPNInjuryScraper(HTMLScraper):
    """
    Pulls the league-wide injury report from ESPN's site API, the same data
    that populates espn.com/nba/injuries. Far more stable than parsing the HTML.
    """

    api_url: str = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

    def get_raw(self) -> dict:
        """Raw JSON, useful for poking at the structure if anything looks off."""
        return self.get_page(self.api_url).json()

    def get_injuries(self) -> list[dict]:
        data = self.get_raw()
        teams = data.get("injuries", [])
        if not teams:
            raise ValueError(
                f"No 'injuries' key in response. Top-level keys: {list(data.keys())}"
            )

        rows = []
        for team in teams:
            team_name = team.get("displayName")
            for inj in team.get("injuries", []):
                athlete = inj.get("athlete", {}) or {}
                details = inj.get("details", {}) or {}
                rows.append({
                    "team": team_name,
                    "player": athlete.get("displayName"),
                    "espn_player_id": self._athlete_id(athlete),
                    "pos": (athlete.get("position") or {}).get("abbreviation"),
                    "status": inj.get("status"),
                    "injury_type": details.get("type"),
                    "injury_detail": details.get("detail"),
                    "side": details.get("side"),
                    "est_return": details.get("returnDate"),
                    "report_date": inj.get("date"),
                    "short_comment": inj.get("shortComment"),
                    "long_comment": inj.get("longComment"),
                })
        return rows

    @staticmethod
    def _athlete_id(athlete: dict) -> str | None:
        if athlete.get("id"):
            return str(athlete["id"])
        # otherwise dig it out of a profile link
        for link in athlete.get("links", []) or []:
            m = re.search(r"/id/(\d+)", link.get("href", ""))
            if m:
                return m.group(1)
        return None


# ============================================================
# RUN IT
# ============================================================

injury_scraper = ESPNInjuryScraper()
injuries_df = pd.DataFrame(injury_scraper.get_injuries())

injuries_df["scraped_date"] = date.today().isoformat()
injuries_df["report_date"] = pd.to_datetime(injuries_df["report_date"], errors="coerce").dt.date
injuries_df["est_return"] = pd.to_datetime(injuries_df["est_return"], errors="coerce").dt.date

# match the name cleaning used for the bbref / EPM tables so they join
injuries_df["player_clean"] = (
    injuries_df["player"].apply(clean_name).str.lower().str.replace(".", "", regex=False)
)

# ESPN calls them "LA Clippers"; team_dim says "Los Angeles Clippers"
injuries_df["team"] = injuries_df["team"].replace({"LA Clippers": "Los Angeles Clippers"})
injuries_df = pd.merge(injuries_df, team_dim[["team", "team_alias"]], how="left", on="team")

unmatched = injuries_df.loc[injuries_df["team_alias"].isna(), "team"].unique()
if len(unmatched):
    print(f"⚠️ Teams with no team_dim match: {list(unmatched)}")

print(f"{len(injuries_df)} injured players across {injuries_df['team'].nunique()} teams")
injuries_df.to_csv(f"NBA_injuries_{date.today().isoformat()}.csv", index=False)
injuries_df = injuries_df[injuries_df['est_return'] > date.today()]
injuries_df
#ROSTER
player_advanced_df = final_stats_df.copy()
injuries_df['player'] = injuries_df['player'].apply(clean_name)
injuries_df['player'] = (
    injuries_df['player'].apply(clean_name).str.lower().str.replace('.', '', regex=False)
)
player_advanced_df['player_name'] = (
    player_advanced_df['player_name'].apply(clean_name).str.lower().str.replace('.', '', regex=False)
)
nba_game_roster_27 = pd.merge(new_full_box_df,player_advanced_df,how='left',left_on='team_abbr',right_on='team_name_abbr')
nba_game_roster_27['player_name'] = nba_game_roster_27['player_name'].str.lower()
nba_game_roster_27 = pd.merge(nba_game_roster_27,gp_pct_df[['player','gp_pct']],how='left',left_on='player',right_on='player')
nba_game_roster_27 = pd.merge(nba_game_roster_27,injuries_df[['player','est_return','report_date']],how='left',left_on='player',right_on='player')
nba_game_roster_27['available'] = np.where(nba_game_roster_27['est_return'] > nba_game_roster_27['game_date'],0,1)
nba_game_roster_27 = pd.merge(nba_game_roster_27,roster_mpg,how='left',left_on='player',right_on='player')
nba_game_roster_27['est_pct_season_missed'] = 1 - nba_game_roster_27['gp_pct']
nba_game_roster_27
#CALCULATE CURRENT RECORDS
played_games = new_full_box_df[~new_full_box_df['pts'].isna()]
current_records = played_games.groupby('team_abbr').agg(w=('win','sum'),games=('game_date','nunique')).reset_index()
current_records['l'] = current_records['games'] - current_records['w']
current_records['games_remaining'] = 82 - current_records['games']
teams_done_w_season = current_records[current_records['games'] == 82][['team_abbr','w','l']]
teams_done_w_season['sim_no'] = np.nan
teams_done_w_season = teams_done_w_season[['team_abbr','sim_no','w','l']]
teams_done_w_season = teams_done_w_season.rename(columns={'w':'wins','l':'losses'})
current_records
draft_pick_value = pd.read_csv('NBA_draft_pick_value_model/draft_pick_no_value.csv')
team_rating_data_new = pd.read_csv('NBA_draft_pick_value_model/NBA_team_rating_data_2000-2026.csv')
nba_drafts = pd.read_csv('NBA_draft_pick_value_model/NBA_draft_classes_2016-2026.csv')
nba_drafts = nba_drafts[nba_drafts['draft_year'] >= 2025]
nba_draft_history = nba_drafts[['team_id','pick_overall','draft_year']].drop_duplicates()
nba_draft_history.loc[nba_draft_history['team_id'] == 'BRK', 'team_id'] = 'BKN'
nba_draft_history.loc[nba_draft_history['team_id'] == 'CHO', 'team_id'] = 'CHA'
nba_draft_history.loc[nba_draft_history['team_id'] == 'PHO', 'team_id'] = 'PHX'
first_pick_26 = nba_draft_history[(nba_draft_history['draft_year'] == 2026) & (nba_draft_history['pick_overall'] == 1)]['team_id']
top_five_25_26 = pd.merge(nba_draft_history[(nba_draft_history['draft_year'] == 2026) & (nba_draft_history['pick_overall'] <= 5)],nba_draft_history[(nba_draft_history['draft_year'] == 2025) & (nba_draft_history['pick_overall'] <= 5)], how='inner',on='team_id')['team_id']
draft_pick_value
lottery_balls = pd.read_csv('NBA_draft_pick_value_model/NBA Draft Lottery Pick Value - New Lottery Balls.csv')
lottery_balls.head()
# ============================================================
# SEASON SIMULATION
# ============================================================
rng = np.random.default_rng()

sims = []
for i in range(1, 5001):
    print(f"\rsim {i}/{5000}", end="", flush=True)
    sim = []

    #SIM MISSED GAMES
    #FOR EACH TEAM
    for team in new_full_box_df[~new_full_box_df['team_abbr'].isin(teams_done_w_season['team_abbr'])]['team_abbr'].drop_duplicates():
    #FILTER FOR THE TEAM AND GAMES THAT HAVENT BEEN PLAYED
        team_games = nba_game_roster_27[(nba_game_roster_27['team_abbr'] == team) & (nba_game_roster_27['is_played'] == 0)]
    #COUNT NUMBER OF REMAINING GAMES
        games_remaining = len(team_games['game_date'].drop_duplicates())
        played_games = int(current_records.loc[current_records['team_abbr'] == team, 'games'].iat[0])
    #CREATE LIST FOR PLAYERS GAMES PLAYED AFTER INJURY SIM
        team_players_gp = []
    #FOR EACH PLAYER ON THE TEAM
        for player in team_games['player'].dropna().drop_duplicates():
    #FILTER FOR THAT PLAYER
            game_player = team_games[team_games['player'] == player][['player', 'team_abbr', 'est_pct_season_missed', 'gp_pct']].drop_duplicates()
    #IF THEY HAVE A KNOWN NON SEASON-ENDING INJURY FOR ANY REMAINING GAMES THEN PASS
            if ((team_games.loc[team_games['player'] == player,'available'] == 0).any()) & ((team_games.loc[team_games['player'] == player,'available'] == 1).any()):
                injury_start = team_games[(team_games['player'] == player)]['season_game_no'].min()
                player_missed_games = team_games[(team_games['player'] == player) & (team_games['available'] == 1)]['season_game_no'].min() - injury_start
    #SEASON ENDING INJURY
            elif (team_games.loc[team_games['player'] == player,'available'] == 0).any():
                injury_start = team_games[(team_games['player'] == player)]['season_game_no'].min()
                player_missed_games = games_remaining
    #IF THEY ARE STARTING SEASON INJURED AND ESTIMATED TO MISS SOME PORTION OF THE SEASON
    #         elif game_player[['est_pct_season_missed']].drop_duplicates().iat[0, 0] > 0:
    # #FOR PLAYERS STARTING SEASON INJURED USE THEIR MISSED GM PCT AS % FOR RNG SIMULATION OF HOW MANY GAMES THEY WILL MISS
    #             player_games_played = rng.binomial(1, (1 - game_player['est_pct_season_missed'].drop_duplicates()), 82)
    #             player_missed_games = ((82-sum(player_games_played)) - played_games).round(0)
    #             injury_start = team_games[(team_games['player'] == player)]['season_game_no'].min()
    #ELSE WE USE GP PCT TO SIMULATE HOW MANY OF GAMES REMAINING A PLAYER WILL MISS
            else:
                player_games_played = rng.binomial(1, game_player['gp_pct'].drop_duplicates(), games_remaining)
                player_missed_games = (games_remaining - sum(player_games_played)).round(0)
    #IF THEY ARE EXPECTED TO MISS THE WHOLE SEASON THEN START ON 1 AND SET EQUAL TO REMAINING GAMES
                if player_missed_games >= games_remaining:
                    injury_start = team_games[(team_games['player'] == player)]['season_game_no'].min()
                    player_missed_games = games_remaining
    #IF THEY ARE EXPECTED TO MISS NONE THEN SET BOTH TO 0
                elif player_missed_games == 0:
                    injury_start = 0
                    player_missed_games = 0
    #OTHERWISE PICK A RANDOM ELIGIBLE GAME TO START INJURY THAT HAS MISSED GAMES LESS THAN OR EQUAL TO REMAINING
                else:
                    injury_start = rng.integers(team_games[(team_games['player'] == player)]['season_game_no'].min(), games_remaining - player_missed_games + played_games + 2)
    #MARK THE INDICES OF WHICH GAMES THEY WILL MISS
            missed_game_indices = range(int(injury_start), int(injury_start) + int(player_missed_games))
    #LOG TEAM, PLAYER, MISSED GAME NO, AND INDICES
            team_players_gp.append([team, player, player_missed_games, missed_game_indices])
    #MAKE IT A DF
        team_player_gp = pd.DataFrame(team_players_gp, columns=['team', 'player', 'player_missed_games', 'missed_game_no'])
    #EXPLODE INDICES
        team_player_gp = team_player_gp.explode('missed_game_no', ignore_index=True)
    #MERGE BACK ONTO REMAINING GAMES
        team_games = pd.merge(team_games, team_player_gp, how='left', left_on=['player', 'season_game_no'], right_on=['player', 'missed_game_no'])
    #MARK WHICH GAMES THEY ARE PLAYING BASED ON SIM
        team_games['is_playing'] = np.where(team_games['missed_game_no'].isna() , 1, 0)
    #LOG SIM NO
        team_games['sim_no'] = i
    #LOG THIS SIM
        sim.append(team_games)
    #CONCAT THE SIM
    sim_season_game_roster = pd.concat(sim)
    #CREATE COPY FOR SORTING
    sim_season_game_roster_sorted = sim_season_game_roster.copy()
    #CREATE SORT KEY SO WE CAN ALWAYS CHOOSE HIGHEST MPG RANK AVAILABLE PLAYERS
    sim_season_game_roster_sorted['sort_key'] = np.where(
        sim_season_game_roster_sorted['is_playing'] == 1,
        sim_season_game_roster_sorted['mp_per_g'],
        -sim_season_game_roster_sorted['mp_per_g']
    )
    #SORT BY SORT KEY
    sim_season_game_roster_sorted = sim_season_game_roster_sorted.sort_values(
        ['game_date', 'team_abbr', 'is_playing', 'sort_key'],
        ascending=[True, True, False, False]
    )
    #REGISTER MPG RK FOR EACH GAME BASED ON SORT
    sim_season_game_roster_sorted['adj_team_mpg_rank'] = (
        sim_season_game_roster_sorted.groupby(['game_date', 'team_abbr']).cumcount() + 1
    )
    #FOR EACH GAME GET TOP 8 AND GROUP BY NECESSARY FIELDS TO SUM ADVANCED STAT SCORE
    sim_season_game = sim_season_game_roster_sorted[sim_season_game_roster_sorted['adj_team_mpg_rank'] <= 8].groupby(
        ['game_date', 'team_abbr', 'team_abbr_opponent', 'is_home', 'is_b2b', 'season_game_no', 'sim_no']
    ).agg({ 'advanced_stat_score': 'sum'}).reset_index()
    #MERGE OPPONENT INFO FOR EACH GAME
    sim_season_game = pd.merge(sim_season_game, sim_season_game[['game_date', 'team_abbr', 'is_b2b', 'advanced_stat_score']], how='left', left_on=['game_date', 'team_abbr_opponent'], right_on=['game_date', 'team_abbr'], suffixes=[None, '_opp'])
    #GET ADVANCED STAT DIFF
    sim_season_game['top_8_adv_diff'] = sim_season_game['advanced_stat_score'] - sim_season_game['advanced_stat_score_opp']
    #GET WIN PROB BASED ON MODEL
    sim_season_game['w_prob'] = clf.predict_proba(sim_season_game[['is_home', 'is_b2b_opp', 'is_b2b', 'top_8_adv_diff']])[:, 1]
    sim_season_home_game = sim_season_game[sim_season_game['is_home'] == 1]

    #SIM WIN WITH W PROB
    sim_season_home_game['win'] = rng.binomial(1, sim_season_home_game['w_prob'])
    #SUM HOME WINS
    home_wins = sim_season_home_game.groupby(['team_abbr', 'sim_no']).agg(home_wins=('win', 'sum')).reset_index()
    road_wins = sim_season_home_game.groupby(['team_abbr_opponent', 'sim_no']).agg(road_wins=('win', 'sum')).reset_index()
    road_wins = pd.merge(road_wins,sim_season_game[sim_season_game['is_home'] == 0].groupby('team_abbr').agg(road_games_remaining=('game_date','nunique')).reset_index(),how='left',left_on='team_abbr_opponent',right_on='team_abbr')
    road_wins = road_wins.drop(columns='team_abbr')
    road_wins['road_wins'] = road_wins['road_games_remaining'] - road_wins['road_wins']

    league_records = pd.merge(home_wins, road_wins, how='left', left_on=['team_abbr', 'sim_no'], right_on=['team_abbr_opponent', 'sim_no'])

    league_records = league_records.drop(columns='team_abbr_opponent')


    league_records['wins'] = league_records['home_wins'] + league_records['road_wins']
    league_records = pd.merge(league_records,current_records[['team_abbr','w']],how='left',left_on='team_abbr',right_on='team_abbr',suffixes=[None,'_drop'])
    league_records['wins'] = league_records['wins'] + league_records['w']
    league_records['losses'] = 82 - league_records['wins']

    league_records = pd.concat([league_records,teams_done_w_season])
    league_records['w/l'] = league_records['wins'] / (league_records['wins'] + league_records['losses'])

    league_records['league_draft_rk'] = league_records['w/l'].rank(ascending=True, method="first")
    league_records = league_records[['team_abbr','w/l','league_draft_rk']]
    league_records = league_records.sort_values(by='league_draft_rk').reset_index(drop=True)
    sim_season_lottery_balls = pd.merge(league_records,lottery_balls,how='left',left_on='league_draft_rk',right_on='Worst Record').reset_index()
    lottery_results = []
    for j,draw_no in enumerate(sorted(league_records[league_records['league_draft_rk'] <= 16]['league_draft_rk'])):
        if (draw_no == 10) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 3):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 11) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 2):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 12) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 1):
            selected = sim_season_lottery_balls['league_draft_rk'].idxmin()
        else:
            if draw_no == 1:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16) & (~sim_season_lottery_balls['team_abbr'].isin(first_pick_26)) & (~sim_season_lottery_balls['team_abbr'].isin(top_five_25_26))].index)
            elif draw_no <= 5:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)  & (~sim_season_lottery_balls['team_abbr'].isin(top_five_25_26))].index)
            else:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)].index)
        selected_team = sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]
        lottery_results.append([draw_no, sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]])
        sim_season_lottery_balls = sim_season_lottery_balls[sim_season_lottery_balls['team_abbr'] != selected_team]
    lottery_results = pd.DataFrame(lottery_results,columns=['pick_no','team_abbr'])
    draft_order = pd.concat([lottery_results,league_records[league_records['league_draft_rk'] > 16][['league_draft_rk','team_abbr']].rename(columns={'league_draft_rk':'pick_no'}).sort_values(by='pick_no')])
    league_records_27 = pd.merge(league_records,draft_order,how='left',on='team_abbr')
    league_records_27['season'] = 2027
    #2028
    league_records_28 = league_records_27.copy()
    league_records_28['season'] = 2028
    league_records_28['w/l'] = league_records_28['w/l'] + (0.1986  +  -0.3970  * league_records_28['w/l'])
    league_records_28 = league_records_28[['team_abbr','w/l','league_draft_rk','season']]

    first_pick_27 = league_records_27[ (league_records_27['pick_no'] == 1)]['team_abbr']
    top_five_26_27 = pd.merge(nba_draft_history[(nba_draft_history['draft_year'] == 2026) & (nba_draft_history['pick_overall'] <= 5)],league_records_27[ (league_records_27['pick_no'] <= 5)], how='inner',left_on='team_id',right_on = 'team_abbr')['team_abbr']

    sim_28_df = league_records_28.copy()

    sim_28_df['sim_w/l'] = rng.binomial(82,sim_28_df['w/l']) / 82

    sim_28_df['league_draft_rk'] = sim_28_df['sim_w/l'].rank(ascending=True, method="first")
    sim_season_lottery_balls = pd.merge(sim_28_df,lottery_balls,how='left',left_on='league_draft_rk',right_on='Worst Record').reset_index()
    lottery_results = []
    for j,draw_no in enumerate(sorted(sim_28_df[sim_28_df['league_draft_rk'] <= 16]['league_draft_rk'])):
        if (draw_no == 10) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 3):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 11) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 2):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 12) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 1):
            selected = sim_season_lottery_balls['league_draft_rk'].idxmin()
        else:
            if draw_no == 1:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16) & (~sim_season_lottery_balls['team_abbr'].isin(first_pick_27)) & (~sim_season_lottery_balls['team_abbr'].isin(top_five_26_27))].index)
            elif draw_no <= 5:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)  & (~sim_season_lottery_balls['team_abbr'].isin(top_five_26_27))].index)
            else:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)].index)
        selected_team = sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]
        lottery_results.append([draw_no, sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]])
        sim_season_lottery_balls = sim_season_lottery_balls[sim_season_lottery_balls['team_abbr'] != selected_team]
    lottery_results = pd.DataFrame(lottery_results,columns=['pick_no','team_abbr'])
    draft_order = pd.concat([lottery_results,sim_28_df[sim_28_df['league_draft_rk'] > 16][['league_draft_rk','team_abbr']].rename(columns={'league_draft_rk':'pick_no'}).sort_values(by='pick_no')])
    sim_28_df = pd.merge(sim_28_df,draft_order,how='left',on='team_abbr')
    sim_28_df['w/l'] = sim_28_df['sim_w/l']
    sim_28_df = sim_28_df.drop(columns='sim_w/l')

    #2029
    league_records_29 = sim_28_df.copy()
    league_records_29['season'] = 2029
    league_records_29['w/l'] = league_records_29['w/l'] + (0.1986  +  -0.3970  * league_records_29['w/l'])
    league_records_29 = league_records_29[['team_abbr','w/l','league_draft_rk','season']]

    first_pick_28 = sim_28_df[ (sim_28_df['pick_no'] == 1)]['team_abbr']
    top_five_27_28 = pd.merge(sim_28_df[ (sim_28_df['pick_no'] <= 5)],league_records_27[ (league_records_27['pick_no'] <= 5)], how='inner',left_on='team_abbr',right_on = 'team_abbr')['team_abbr']

    sim_29_df = league_records_29.copy()

    sim_29_df['sim_w/l'] = rng.binomial(82,sim_29_df['w/l']) / 82

    sim_29_df['league_draft_rk'] = sim_29_df['sim_w/l'].rank(ascending=True, method="first")
    sim_season_lottery_balls = pd.merge(sim_29_df,lottery_balls,how='left',left_on='league_draft_rk',right_on='Worst Record').reset_index()
    lottery_results = []
    for j,draw_no in enumerate(sorted(sim_29_df[sim_29_df['league_draft_rk'] <= 16]['league_draft_rk'])):
        if (draw_no == 10) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 3):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 11) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 2):
            selected = rng.choice(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3].index)
        elif (draw_no == 12) & (len(sim_season_lottery_balls[sim_season_lottery_balls['league_draft_rk'] <= 3]['team_abbr'].drop_duplicates()) == 1):
            selected = sim_season_lottery_balls['league_draft_rk'].idxmin()
        else:
            if draw_no == 1:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16) & (~sim_season_lottery_balls['team_abbr'].isin(first_pick_28)) & (~sim_season_lottery_balls['team_abbr'].isin(top_five_27_28))].index)
            elif draw_no <= 5:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)  & (~sim_season_lottery_balls['team_abbr'].isin(top_five_27_28))].index)
            else:
                selected = rng.choice(sim_season_lottery_balls[(sim_season_lottery_balls['league_draft_rk'] <= 16)].index)
        selected_team = sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]
        lottery_results.append([draw_no, sim_season_lottery_balls[sim_season_lottery_balls.index == selected]['team_abbr'][selected]])
        sim_season_lottery_balls = sim_season_lottery_balls[sim_season_lottery_balls['team_abbr'] != selected_team]
    lottery_results = pd.DataFrame(lottery_results,columns=['pick_no','team_abbr'])
    draft_order = pd.concat([lottery_results,sim_29_df[sim_29_df['league_draft_rk'] > 16][['league_draft_rk','team_abbr']].rename(columns={'league_draft_rk':'pick_no'}).sort_values(by='pick_no')])
    sim_29_df = pd.merge(sim_29_df,draft_order,how='left',on='team_abbr')
    sim_29_df['w/l'] = sim_29_df['sim_w/l']
    sim_29_df = sim_29_df.drop(columns='sim_w/l')

    final_sim_df = pd.concat([league_records_27,sim_28_df,sim_29_df]).reset_index(drop=True)
    rd_2_27_1 = final_sim_df[(final_sim_df['season'] == 2027) & (final_sim_df['pick_no'] <= 16)]
    rd_2_27_1['pick_no'] = rd_2_27_1['pick_no'].rank(ascending=False) + 30
    rd_2_27_2 = final_sim_df[(final_sim_df['season'] == 2027) & (final_sim_df['pick_no'] > 16)]
    rd_2_27_2['pick_no'] = rd_2_27_2['w/l'].rank(ascending=True,method="first") + 30 + 16

    rd_2_28_1 = final_sim_df[(final_sim_df['season'] == 2028) & (final_sim_df['pick_no'] <= 16)]
    rd_2_28_1['pick_no'] = rd_2_28_1['pick_no'].rank(ascending=False) + 30
    rd_2_28_2 = final_sim_df[(final_sim_df['season'] == 2028) & (final_sim_df['pick_no'] > 16)]
    rd_2_28_2['pick_no'] = rd_2_28_2['w/l'].rank(ascending=True,method="first") + 30 + 16

    rd_2_29_1 = final_sim_df[(final_sim_df['season'] == 2029) & (final_sim_df['pick_no'] <= 16)]
    rd_2_29_1['pick_no'] = rd_2_29_1['pick_no'].rank(ascending=False) + 30
    rd_2_29_2 = final_sim_df[(final_sim_df['season'] == 2029) & (final_sim_df['pick_no'] > 16)]
    rd_2_29_2['pick_no'] = rd_2_29_2['w/l'].rank(ascending=True,method="first") + 30 + 16

    final_full_draft_results = pd.concat([final_sim_df,rd_2_27_1,rd_2_27_2,rd_2_28_1,rd_2_28_2,rd_2_29_1,rd_2_29_2])

    # #CLIPPERS PICK DOCKED
    # final_full_draft_results.loc[(final_full_draft_results['season'] == 2029) & (final_full_draft_results['pick_no'] <= 30) & (final_full_draft_results['team_abbr'] != 'LAC') & (final_full_draft_results['pick_no'] >
    #                                                                                                                                                                                  (final_full_draft_results.loc[(final_full_draft_results['season'] == 2029) & (final_full_draft_results['pick_no'] <= 30) & (final_full_draft_results['team_abbr'] == 'LAC'),'pick_no'].iloc[0])),'pick_no' ] -= 1
    # final_full_draft_results = final_full_draft_results[~((final_full_draft_results['season'] == 2029) & (final_full_draft_results['pick_no'] <= 30) & (final_full_draft_results['team_abbr'] == 'LAC'))]

    final_full_draft_results['sim_no'] = i
    final_full_draft_results = pd.merge(final_full_draft_results,draft_pick_value[['pick_overall','value']],how='left',left_on='pick_no',right_on='pick_overall')
    sims.append(final_full_draft_results)

all_sim_df = pd.concat(sims)
all_sim_df['round'] = np.where(all_sim_df['pick_no'] <= 30, 1, 2)
combo_counts = all_sim_df.groupby(['team_abbr', 'season', 'pick_no', 'round', 'value']).size().reset_index(name='count')
most_common_pick_value = combo_counts[['team_abbr', 'season','round', 'pick_no', 'value','count']]
most_common_pick_value['weight'] = most_common_pick_value['count'] / len(sims)
most_common_pick_value['weighted_value'] = most_common_pick_value['value'] * most_common_pick_value['weight']
mean_simmed_record = most_common_pick_value.groupby(['team_abbr','season','round']).agg({'weighted_value':'sum'}).reset_index()
# mean_simmed_record['league_rk'] = mean_simmed_record.groupby('season')['w/l'].rank(ascending=False, method="first")
# mean_simmed_record['league_draft_rk'] = mean_simmed_record.groupby('season')['w/l'].rank(ascending=True, method="first")
mean_simmed_record
team_draft_picks = pd.read_csv('NBA_draft_pick_value_model/NBA Draft Lottery Pick Value - NBA_team_draft_picks.csv')
owned_draft_pick_value = pd.merge(team_draft_picks,mean_simmed_record,how='left',right_on=['team_abbr','season','round'],left_on=['originating_team','year','round'])
owned_draft_pick_value.loc[(owned_draft_pick_value['year'] >= 2030) & (owned_draft_pick_value['round'] == 1),'weighted_value'] = 3.382987
owned_draft_pick_value.loc[(owned_draft_pick_value['year'] >= 2030) & (owned_draft_pick_value['round'] == 2),'weighted_value'] = 3.108334
owned_draft_pick_value.loc[(owned_draft_pick_value['originating_team'] == 'IND') & (owned_draft_pick_value['round'] == 1) & (owned_draft_pick_value['rights_holder'] == 'LAC'),'notes'] = 'In question RE: Salary Cap Circumvention'
owned_draft_pick_value.loc[(owned_draft_pick_value['year'] >= 2030) & (owned_draft_pick_value['originating_team'] == 'LAC') & (owned_draft_pick_value['round'] == 1),'notes'] = 'In question RE: Salary Cap Circumvention'
owned_draft_pick_value = owned_draft_pick_value.dropna(subset='weighted_value')
owned_draft_pick_value = owned_draft_pick_value[[ 'originating_team',
       'year', 'round', 'rights_holder', 'notes','weighted_value']]
owned_draft_pick_value.loc[owned_draft_pick_value['notes'].isna(), 'notes'] = '-'
owned_draft_pick_value.rename(columns={'weighted_value':'value'},inplace=True)
owned_draft_pick_value['value'] = owned_draft_pick_value['value'].round(2)
owned_draft_pick_value['% of league value'] = (owned_draft_pick_value['value'] * 1.000 / owned_draft_pick_value['value'].sum()) * 100
owned_draft_pick_value = owned_draft_pick_value.rename(columns={'originating_team':'originating team','rights_holder':'rights holder'})
owned_draft_pick_value.to_csv('NBA_modeled_draft_pick_value.csv')
owned_draft_pick_value
# LOAD DATA TO SUPABASE

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Initialize the client
supabase: Client = create_client(url, key)

records = owned_draft_pick_value.to_dict(orient="records")

# Bulk load to Supabase
response = (
    supabase.table("nba_draft_pick_value")
    .delete()
    .neq("originating team", -1)
    .execute()
)

response = supabase.table("nba_draft_pick_value").insert(records).execute()
