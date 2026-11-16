import requests
import pandas as pd
import numpy as np
import io
import time
from datetime import timedelta
from nba_api.stats.static import teams
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.static import players
import matplotlib.pyplot as plt
from nba_api.stats.endpoints import boxscoretraditionalv3
from zoneinfo import ZoneInfo
from dateutil.tz import tzutc
from datetime import datetime
import warnings
import isodate
import math
import player_on_court_kills_by_game
from player_on_court_kills_by_game import *
import player_off_court_kills_by_game
from player_off_court_kills_by_game import *
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

df = pd.read_parquet('2026-27_NBA_regular_season_pbp.parquet')
box_score_full_df = pd.read_parquet('NBA_player_box_scores_2026-27.parquet')

box_score_full_df['Name'] = box_score_full_df['firstName'] + ' ' + box_score_full_df['familyName']
playernames = box_score_full_df['Name'].drop_duplicates()
player_ids = box_score_full_df['personId'].drop_duplicates()

games_df = df[['personId','gameid']][df['personId'] == 1628381].drop_duplicates()
games_df['gameid'] = games_df['gameid'].astype(int)
df['gameid'] = df['gameid'].astype(int)
box_score_full_df['gameId'] = box_score_full_df['gameId'].astype(int)
box_score_full_df = box_score_full_df.drop_duplicates()
games_df['gameid'].tolist()



#KILLS ON COURT

from zoneinfo import ZoneInfo
from dateutil.tz import tzutc
from datetime import datetime
import warnings
from IPython.display import clear_output

def player_on_floor_kills(games,playerid,player,box_score_df):
    error_count = 0
    player_kills_df = []
    for y, newgame in zip(range(1,len(games)+1),games):
        message = f"Processing game {newgame} number {y} of {len(games)+1} "
        print(f"\r{message}", end="", flush=True)

        print(playerid)
        temp_df = pd.DataFrame(player_kills_by_game(df,newgame,playerid,player,box_score_df),index=['gameid','playerid','player','team','team_def_poss','kills','max_stops','opponent','opp_def_poss','opp_kills','opp_max_stops']).T
        player_kills_df.append(temp_df)
    return pd.concat(player_kills_df) if player_kills_df else pd.DataFrame()
df_list1 = []
for  x,player, playerid in zip(range(1,len(playernames)+1),playernames,player_ids):
    print(f"Player {x}/{len(playernames)}: {player}" )

    games_df = df[['personId','gameid']][df['personId'] == playerid].drop_duplicates()
    games_df['gameid'] = games_df['gameid'].astype(int)
    games = games_df['gameid'].tolist()
    # time.sleep(4.0)
    players_games_kills_df = player_on_floor_kills(games,playerid,player,box_score_full_df)
    # print(player_on_floor_kills(games,playerid,player,box_score_full_df))
    df_list1.append(players_games_kills_df)
    clear_output(wait=True)
final_dataframe = pd.concat(df_list1, ignore_index=True)
print("Cell execution complete!")

final_dataframe = final_dataframe[final_dataframe['gameid'] != 0]

player_summary_df = final_dataframe.groupby(['playerid','player','team']).agg({'gameid':'nunique','team_def_poss':'sum','kills':'sum','max_stops':'mean',
                                                           'opp_def_poss':'sum','opp_kills':'sum','opp_max_stops':'mean'}).reset_index()
player_summary_df['kills_per_100_poss'] = (player_summary_df['kills']/player_summary_df['team_def_poss']) * 100
player_summary_df['opp_kills_per_100_poss'] = (player_summary_df['opp_kills']/player_summary_df['opp_def_poss']) * 100
player_summary_df['team_def_poss'] = player_summary_df['team_def_poss'].astype(int)

#OFF COURT

# GET KILLS FOR PLAYER OFF COURT

def player_off_floor_kills(games,playerid,player,box_score_df):
    error_count = 0
    player_off_kills_df = []
    for y, newgame in zip(range(1,len(games)+1),games):
        message = f"Processing game {newgame} number {y} of {len(games)+1} "
        print(f"\r{message}", end="", flush=True)

        print(playerid)
        temp_df = pd.DataFrame(player_off_court_kills_by_game(df,newgame,playerid,player,box_score_df),index=['gameid','playerid','player','team','team_def_poss','kills','max_stops','opponent','opp_def_poss','opp_kills','opp_max_stops']).T
        player_off_kills_df.append(temp_df)
    return pd.concat(player_off_kills_df) if player_off_kills_df else pd.DataFrame()
df_list2 = []
for  x,player, playerid in zip(range(1,len(playernames)+1),playernames,player_ids):
    print(f"Player {x}/{len(playernames)}: {player}" )

    games_df = df[['personId','gameid']][df['personId'] == playerid].drop_duplicates()
    games_df['gameid'] = games_df['gameid'].astype(int)
    games = games_df['gameid'].tolist()
    # time.sleep(4.0)
    players_games_off_kills_df = player_off_floor_kills(games,playerid,player,box_score_full_df)
    # print(player_on_floor_kills(games,playerid,player,box_score_full_df))
    df_list2.append(players_games_off_kills_df)
    clear_output(wait=True)
final_dataframe_off_court = pd.concat(df_list2, ignore_index=True)
print("Cell execution complete!")

final_dataframe_off_court = final_dataframe_off_court[final_dataframe_off_court['gameid'] != 0]

player_off_court_summary_df = final_dataframe_off_court.groupby(['playerid','player','team']).agg({'gameid':'nunique','team_def_poss':'sum','kills':'sum','max_stops':'mean','opp_def_poss':'sum','opp_kills':'sum','opp_max_stops':'mean'}).reset_index()
player_off_court_summary_df['kills_per_100_poss'] = (player_off_court_summary_df['kills']/player_off_court_summary_df['team_def_poss']) * 100
player_off_court_summary_df['opp_kills_per_100_poss'] = (player_off_court_summary_df['opp_kills']/player_off_court_summary_df['opp_def_poss']) * 100

player_final_summary = pd.merge(player_summary_df,player_off_court_summary_df,how='inner'
                                ,left_on=['player','team'],right_on=['player','team']
                                ,suffixes=['_on_court','_off_court'])

player_final_summary['kills_per_100_poss_on_off'] =  player_final_summary['kills_per_100_poss_on_court'] - player_final_summary['kills_per_100_poss_off_court']
player_final_summary['opps_kills_per_100_poss_on_off'] =  player_final_summary['opp_kills_per_100_poss_on_court'] - player_final_summary['opp_kills_per_100_poss_off_court']
player_final_summary['net_kills_per_100_poss'] = player_final_summary['kills_per_100_poss_on_off'] - player_final_summary['opps_kills_per_100_poss_on_off']
player_final_summary = player_final_summary[player_final_summary['team_def_poss_on_court'] > 250].sort_values(by='kills_per_100_poss_on_off',ascending=False)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Initialize the client
supabase: Client = create_client(url, key)

records = player_final_summary.to_dict(orient="records")

# Bulk load to Supabase
response = (
    supabase.table("player_kills_summary")
    .delete()
    .neq("player", -1)
    .execute()
)

response = supabase.table("player_kills_summary").insert(records).execute()