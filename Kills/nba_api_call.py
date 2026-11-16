import pandas as pd
import numpy as np
import requests
from nba_api.stats.endpoints import boxscoretraditionalv3
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.static import players
import warnings
import isodate
import random
import math
warnings.filterwarnings('ignore')
from curl_cffi import requests as cffi_requests
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.library.http import NBAHTTP
from identity_rotation import *

import time
# Create session
session = cffi_requests.Session(impersonate='chrome120')

# Monkey-patch nba_api
NBAHTTP.session = session

stats_headers = {
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
'Referer': 'https://stats.nba.com/',
'Origin': 'https://stats.nba.com',
'Accept': 'application/json, text/plain, */*',
'Accept-Language': 'en-US,en;q=0.9',
'x-nba-stats-origin': 'stats',
'x-nba-stats-token': 'true',
}
cdn_headers = {
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
'Referer': 'https://www.nba.com/',
'Origin': 'https://www.nba.com',
'Accept': 'application/json, text/plain, */*',
'Accept-Language': 'en-US,en;q=0.9',
}

r2 = session.get(
'https://stats.nba.com/stats/leaguegamefinder',
params = {
    'PlayerOrTeam': 'T',
    'Season': '2026-27',
    'SeasonType': 'Regular Season',
    'LeagueID': '00'
},
headers = stats_headers
)

#PBP

# GET ALL GAMES 2026-27
gamefinder = leaguegamefinder.LeagueGameFinder(season_nullable='2026-27', league_id_nullable='00',
                                              season_type_nullable='Regular Season')
games_2526 = gamefinder.get_data_frames()[0]
game_ids = [str(g).zfill(10) for g in games_2526['GAME_ID'].unique()]
print(f"Found {len(game_ids)} games for 2026-27 regular season")

def get_data(game_id, session, headers, max_retries=2):
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    for attempt in range(1, max_retries + 1):
        resp = session.get(url=url, headers=headers, timeout=15)
        if resp.status_code == 200:
            try:
                data = resp.json()
                actions = data['game']['actions']
                df = pd.DataFrame(actions)
                df['gameid'] = game_id
                return df
            except (KeyError, ValueError) as e:
                raise RuntimeError(f"Malformed response for {game_id}: {e}")
        elif resp.status_code in (429, 403):
            wait = 20 * attempt
            print(f"Blocked ({resp.status_code}) on {game_id}, waiting {wait}s (attempt {attempt})")
            time.sleep(wait)
            continue
        else:
            resp.raise_for_status()
    raise RuntimeError(f"Exhausted retries for {game_id}")

# --- resume support: pick up where a prior run left off ---
try:
    pbpdata = load_checkpoint('pbpdata_checkpoint_2627.pkl', [])
    failed_games = load_checkpoint('failed_games_checkpoint_2627.pkl', [])
    print(f"Resumed: {len(pbpdata)} successes, {len(failed_games)} prior failures already loaded")
except NameError:
    # load_checkpoint not defined in this session yet — start fresh
    pbpdata = []
    failed_games = []

completed_ids = {str(d['gameid'].iloc[0]) for d in pbpdata} if pbpdata else set()
remaining_ids = [g for g in game_ids if g not in completed_ids]
print(f"{len(remaining_ids)} games remaining out of {len(game_ids)}")

session, cdn_headers_active = new_identity(cdn_headers)

for i, game_id in enumerate(remaining_ids, 1):
    print(f"\rFetching game {i}/{len(remaining_ids)}: {game_id}", end="", flush=True)

    if should_rotate(i, every=50):
        session, cdn_headers_active = new_identity(cdn_headers)
        jitter_sleep(4, 8)

    try:
        game_data = get_data(game_id, session, cdn_headers_active)
        pbpdata.append(game_data)
        jitter_sleep(2, 4)
    except Exception as e:
        print(f"\n⚠️ Failed {game_id} - {type(e).__name__}: {e}")
        failed_games.append((game_id, str(e)))
        jitter_sleep(3, 6)

    if i % 25 == 0:
        save_checkpoint(pbpdata, 'pbpdata_checkpoint_2627.pkl')
        save_checkpoint(failed_games, 'failed_games_checkpoint_2627.pkl')

if pbpdata:
    pbp_full_df_2627 = pd.concat(pbpdata, ignore_index=True)
    print(f"\n✅ Fetched play-by-play for {len(pbpdata)} games!")
else:
    pbp_full_df_2627 = pd.DataFrame()
    print("\n❌ No play-by-play data collected.")

if failed_games:
    print(f"\n{len(failed_games)} games failed. First few:")
    for gid, err in failed_games[:10]:
        print(f"  {gid}: {err}")

print(f"\nDistinct games in final dataset: {pbp_full_df_2627['gameid'].nunique()}")

pbp_full_df_2627.to_parquet('2026-27_NBA_regular_season_pbp.parquet')

#PLAYER BOX SCORES
import time
import random
import pandas as pd

# GET ALL GAMES 2023-24
gamefinder = leaguegamefinder.LeagueGameFinder(season_nullable='2026-27', league_id_nullable='00',
                                              season_type_nullable='Regular Season')
games_2324 = gamefinder.get_data_frames()[0]
season_games = [str(g).zfill(10) for g in games_2324['GAME_ID'].unique()]
print(f"Found {len(season_games)} games for 2026-27 regular season")

# --- resume support ---
try:
    all_box_scores = load_checkpoint('boxscore_checkpoint_2627.pkl', [])
    failed_boxscores = load_checkpoint('boxscore_failed_checkpoint_2627.pkl', [])
    print(f"Resumed: {len(all_box_scores)} successes, {len(failed_boxscores)} prior failures already loaded")
except NameError:
    all_box_scores = []
    failed_boxscores = []

completed_ids = {str(d['gameId'].iloc[0]) for d in all_box_scores} if all_box_scores else set()
remaining_games = [g for g in season_games if g not in completed_ids]
print(f"{len(remaining_games)} games remaining out of {len(season_games)}")

session, _ = new_identity(stats_headers)
NBAHTTP.session = session

for i, gameid in enumerate(remaining_games, 1):
    print(f"\rFetching game {i}/{len(remaining_games)}: {gameid}", end="", flush=True)

    if should_rotate(i, every=50):
        session, _ = new_identity(stats_headers)
        NBAHTTP.session = session
        jitter_sleep(40, 60)

    try:
        box_score_trad = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=gameid)
        box_score_df = box_score_trad.get_data_frames()[0]
        all_box_scores.append(box_score_df)
        jitter_sleep(2, 3.5)
    except Exception as e:
        print(f"\n⚠️ Failed {gameid} - {type(e).__name__}: {e}")
        failed_boxscores.append((gameid, str(e)))
        jitter_sleep(3, 6)

    if i % 25 == 0:
        save_checkpoint(all_box_scores, 'boxscore_checkpoint_2627.pkl')
        save_checkpoint(failed_boxscores, 'boxscore_failed_checkpoint_2627.pkl')

if all_box_scores:
    box_score_full_df_2627 = pd.concat(all_box_scores, ignore_index=True)
    print(f"\n✅ Fetched box scores for {len(all_box_scores)} games!")
else:
    box_score_full_df_2627 = pd.DataFrame()
    print("\n❌ No box scores collected.")

if failed_boxscores:
    print(f"\n{len(failed_boxscores)} games failed. First few:")
    for gid, err in failed_boxscores[:10]:
        print(f"  {gid}: {err}")

print(f"\nDistinct games: {box_score_full_df_2627['gameId'].nunique()}")

box_score_full_df_2627.to_parquet('NBA_player_box_scores_2026-27.parquet')
