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
headers  = {
    'Connection': 'keep-alive',
    'Accept': 'application/json, text/plain, */*',
    'x-nba-stats-token': 'true',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
    'x-nba-stats-origin': 'stats',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Referer': 'https://stats.nba.com/',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
}
warnings.filterwarnings('ignore')

def player_off_court_kills_by_game(df,gameid,playerid,player,box_score_full_df):
    try:

        games_df = df[['personId','gameid']][df['personId'] == gameid].drop_duplicates()

        gameids = games_df['gameid']

        # box_score_trad = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=gameid)
        # box_score_full_df = box_score_trad.get_data_frames()[0]
        box_score_df = box_score_full_df[box_score_full_df['gameId'] == gameid]

        box_score_df['starter'] =np.where((box_score_df['position'].astype(str) == 'F') | (box_score_df['position'].astype(str) == 'G') |(box_score_df['position'].astype(str) == 'C'), 1, 0)

        starters_df = box_score_df[box_score_df['starter'] == 1].sort_values(by='teamTricode')
        starters_df['full_name'] = starters_df['firstName'] + ' ' + starters_df['familyName']
        starters_df = starters_df[['gameId','teamTricode','personId','full_name']]
        box_score_df['Player'] = box_score_df['firstName'] + ' ' + box_score_df['familyName']
        box_score_df['Team'] = box_score_df['teamTricode']
        player_team_df = box_score_df[['Player', 'Team']].drop_duplicates()

        #filter for game
        game_df = df[df['gameid'] == gameid]
        game_df.reset_index(inplace=True,drop=True)
        # game_df['clockconvert'] = pd.to_datetime(1490195805, unit='s')
        # for i, idx in enumerate(game_df['clock'], 0):
        #     game_df.loc[i,'clockconvert'] = isodate.parse_duration(idx)
        game_df = game_df.sort_values(by='orderNumber',ascending=True).reset_index(drop=True)
        game_df['sub_out'] = np.where( game_df['subType'] == 'out', 1, 0)
        game_df['sub_in'] = np.where( game_df['subType'] == 'in', 1, 0)
        game_df['substitution'] = np.where( game_df['actionType'] == 'substitution', 1, 0)
        # # periods = game_df.groupby('period').agg({'clockconvert':'max'})
        # time_remaining = periods['clockconvert'].sum()
        # game_df['time_remaining'] = np.nan
        # game_df.loc[0,'time_remaining'] = time_remaining
        # # game_df['clockseconds'] = game_df['clockconvert'].dt.total_seconds()
        # game_df['time_remaining'].fillna(method='Ffill', inplace=True)
        # game_df['time_remaining_seconds'] = game_df['time_remaining'].dt.total_seconds()
        # game_df['time_elapsed'] = game_df['clockseconds'].diff()
        # game_df.loc[game_df['time_elapsed'] > 0 , 'time_elapsed'] = 0
        # x = game_df.loc[0,'time_remaining_seconds']
        # game_df.loc[0,'time_elapsed'] = 0
        # for idx,y in enumerate(game_df['time_elapsed'],0):
        #     x += y
        #     game_df.loc[idx,'time_remaining_seconds'] = x
        #
        # game_df['time_remaining_seconds'] = game_df['time_remaining_seconds'].astype(float).round(2)
        # game_df.head(3)


        # In[68]:


        #identify and mark stints
        s = game_df['substitution']

        a = np.r_[ s.values]
        v = np.diff(a)
        new_stint = np.where(v == -1)[0]
        game_df['stint']= np.nan
        list_ = []
        for i, idx in enumerate(new_stint, 1):
            list_.append(i)
        for i, idx in enumerate(new_stint, 1):
            game_df.loc[idx, 'stint'] = i
        game_df.loc[game_df.index[-1], 'stint'] = list_[-1] + 1
        game_df['stint'] = game_df['stint'].bfill()
        game_df.head(3)

        player_df = pd.DataFrame({
            'id': box_score_df['personId'],
            'full_name': box_score_df['Player'],
        })


        stint_sub_out = game_df[['actionType','subType','personId','playerName','stint']][game_df['sub_out'] == 1].groupby('stint').agg({'personId':'unique','playerName':'unique'})
        stint_sub_out = pd.DataFrame(stint_sub_out['personId'].tolist()).assign(stint=stint_sub_out.index.tolist())
        stint_sub_out.columns = stint_sub_out.columns.astype(str)


        stint_sub_in = game_df[['actionType','subType','personId','playerName','stint']][game_df['sub_in'] == 1].groupby('stint').agg({'personId':'unique','playerName':'unique'})
        stint_sub_in = pd.DataFrame(stint_sub_in['personId'].tolist()).assign(stint=stint_sub_in.index.tolist())
        stint_sub_in.columns = stint_sub_in.columns.astype(str)


        #add columns iff need be so we always have 5
        if len(stint_sub_out.columns) == 3:
            stint_sub_out['2'] = np.nan
            stint_sub_out['3'] = np.nan
            stint_sub_out['4'] = np.nan

        elif len(stint_sub_out.columns) == 4:
            stint_sub_out['3'] = np.nan
            stint_sub_out['4'] = np.nan
        elif len(stint_sub_out.columns) == 5:
            stint_sub_out['4'] = np.nan
        else:
            pass

        #add columns iff need be so we always have 5
        if len(stint_sub_in.columns) == 3:
            stint_sub_in['2'] = np.nan
            stint_sub_in['3'] = np.nan
            stint_sub_in['4'] = np.nan

        elif len(stint_sub_in.columns) == 4:
            stint_sub_in['3'] = np.nan
            stint_sub_in['4'] = np.nan
        elif len(stint_sub_in.columns) == 5:
            stint_sub_in['4'] = np.nan
        else:
            pass


        #join names?
        stint_sub_out = pd.merge(stint_sub_out,player_df[['id','full_name']],how='left',left_on='0',right_on='id')
        stint_sub_out = pd.merge(stint_sub_out,player_df[['id','full_name']],how='left',left_on='1',right_on='id')
        stint_sub_out = pd.merge(stint_sub_out,player_df[['id','full_name']],how='left',left_on='2',right_on='id',suffixes=(None,'_z'))
        stint_sub_out = pd.merge(stint_sub_out,player_df[['id','full_name']],how='left',left_on='3',right_on='id',suffixes=(None,'_z'))
        stint_sub_out = pd.merge(stint_sub_out,player_df[['id','full_name']],how='left',left_on='4',right_on='id',suffixes=(None,'_a'))
        stint_sub_out = stint_sub_out[['stint','full_name_x','full_name_y','full_name','full_name_z','full_name_a']]

        stint_sub_in = pd.merge(stint_sub_in,player_df[['id','full_name']],how='left',left_on='0',right_on='id')
        stint_sub_in = pd.merge(stint_sub_in,player_df[['id','full_name']],how='left',left_on='1',right_on='id')
        stint_sub_in = pd.merge(stint_sub_in,player_df[['id','full_name']],how='left',left_on='2',right_on='id',suffixes=(None,'_z'))
        stint_sub_in = pd.merge(stint_sub_in,player_df[['id','full_name']],how='left',left_on='3',right_on='id',suffixes=(None,'_z'))
        stint_sub_in = pd.merge(stint_sub_in,player_df[['id','full_name']],how='left',left_on='4',right_on='id',suffixes=(None,'_a'))
        stint_sub_in = stint_sub_in[['stint','full_name_x','full_name_y','full_name','full_name_z','full_name_a']]


        stint_sub_out_t = stint_sub_out.T
        stint_sub_in_t = stint_sub_in.T


        # find players on floor for each stint by starting with starters then subtracting sub outs and adding sub ins for each subsequent stint
        stints = []
        setx = set(starters_df['full_name'])
        setx.discard('nan')
        setx.discard('None')
        stints.append(setx)
        for colx, coly in zip(range(len(stint_sub_in_t.columns )),range(len(stint_sub_out_t.columns))):
            set1 = setx
            set2 = set(stint_sub_in_t.iloc[1:,colx])
            set3 = set(stint_sub_out_t.iloc[1:,coly])
            minus_subs = set1.difference(set3)

            setx = minus_subs | set2
            # setx = minus_subs.union(only_in_list2)
            setx.discard('NaN')
            setx.discard(np.nan)
            setx.discard('None')
            stints.append(setx)

        on_floor_df = pd.DataFrame(stints)
        on_floor_df.reset_index(inplace=True)
        on_floor_df['index'] = on_floor_df['index'] + 1
        on_floor_df = on_floor_df.rename(columns={'index':'stint'})

        on_floor_df.head(3)

        # Build a lookup from player name to team for this game: drop repeated names, index by name, keep the 'Team' column
        team_lookup = player_team_df.set_index('Player')['Team']

        # Loop over the player slot columns (0, 1, ... 9); [1:] skips 'stint'
        for x in on_floor_df.columns[1:]:
            # Rename the slot column (e.g. 3) to 'Player3' so its name says what it holds
            on_floor_df = on_floor_df.rename(columns={x: f'Player{x}'})
            # Look up each name in 'Player{x}' and put that player's team in a new 'Team{x}' column (NaN if not found)
            on_floor_df[f'Team{x}'] = on_floor_df[f'Player{x}'].map(team_lookup)

        # Build the final column order: 'stint', then Player0, Team0, Player1, Team1, ... Player9, Team9
        keep = ['stint'] + [f'{c}{i}' for i in range(10) for c in ('Player', 'Team')]
        # Keep only those columns in that order; any slot that doesn't exist (fewer than 10 players) is added as an empty column
        on_floor_df = on_floor_df.reindex(columns=keep)
        # Attach the lineup to every play: each row of game_df gets the 10 players and teams for its stint
        game_df = pd.merge(game_df, on_floor_df, how='left', on='stint')

        # Home team = the team on plays where scoreHome increases; away team = the other team in the game
        home_scored = game_df['scoreHome'].astype(int).diff() > 0
        home_tricode = game_df.loc[home_scored, 'teamTricode'].mode()[0]
        away_tricode = [t for t in game_df['teamTricode'].dropna().unique() if t != home_tricode][0]
        game_df['Home Tricode'] = home_tricode
        game_df['Visitor Tricode'] = away_tricode
        game_df['gameid'] = game_df['gameid'].astype(int)
        game_df = game_df.loc[:,~game_df.columns.duplicated()].copy()

        game_df['gameid'] = game_df['gameid'].astype(int)



        # In[71]:


        # MARK POSSESSIONS

        s = game_df['possession']
        v = np.diff(s)
        new_poss = np.where(v != 0)[0]

        game_df['possession_no']= np.nan

        for i, idx in enumerate(new_poss, 1):
            game_df.loc[idx+1, 'possession_no'] = i
        game_df['possession_no'] = game_df['possession_no'].ffill()

        team_ids = df[['teamId','teamTricode']].drop_duplicates().dropna()
        # game_df.rename(columns={'gamedate_x':'gamedate','teamTricode_y':'teamTricode'},inplace=True)
        # team_games = game_df[['teamTricode','gameid','gamedate']].drop_duplicates().dropna()

        new_game_df = pd.merge(game_df,team_ids,how='left',left_on='possession',right_on='teamId')
        new_game_df.rename(columns={'teamTricode_y':'possTricode'},inplace=True)

        new_game_df.head(3)


        # In[73]:


        
        
        # Get player's team BEFORE filtering for off-court stints
        mask = (new_game_df == player)
        cols_with_value_bool = mask.any(axis=0)
        column_names = new_game_df.columns[cols_with_value_bool].tolist()
        
        # if not column_names:
        #     print(f"Player {player} not found in game {gameid}")
        #     return [gameid,playerid,player,None,0,0,0,None,0,0,0]
        
        player_team_df_temp = new_game_df[[column_names[0],'Team' + column_names[0][-1]]][new_game_df[column_names[0]] == player].drop_duplicates()
        player_team = player_team_df_temp.iloc[0,-1]
        
        if player_team == game_df['Home Tricode'].iloc[0]:
            player_home_away = 'Home'
        else:
            player_home_away = 'Away'
        
        player_stints = new_game_df[new_game_df[['Player1','Player2','Player3','Player4','Player5','Player6','Player7','Player8','Player9','Player0']].ne(player).all(axis=1)]

        new_test_df = player_stints.copy()

        team_poss_score = new_test_df.groupby(
            ['stint', 'possTricode', 'Home Tricode', 'Visitor Tricode', 'possession_no']).agg(
            {'scoreHome': 'max', 'scoreAway': 'max'})

        team_poss_score = team_poss_score.reset_index()

        team_poss_score.rename(columns={'Home Tricode': 'Home Team', 'Visitor Tricode': 'Away Team'}, inplace=True)

        team_poss_score['Team'] = player_team

        if team_poss_score['Team'][0] == team_poss_score['Home Team'][0]:
            team_poss_score['Opponent'] = team_poss_score['Away Team'][0]

        else:
            team_poss_score['Opponent'] = team_poss_score['Home Team'][0]

        if player_home_away == 'Home':
            player_stints_opp_poss = team_poss_score[team_poss_score['possTricode'] != team_poss_score['Home Team']]
            player_stints_poss = team_poss_score[team_poss_score['possTricode'] == team_poss_score['Home Team']]
        else:
            player_stints_opp_poss = team_poss_score[team_poss_score['possTricode'] != team_poss_score['Away Team']]
            player_stints_poss = team_poss_score[team_poss_score['possTricode'] == team_poss_score['Away Team']]

            player_stints_poss

        # In[138]:

        # GET Player TEAM KILLS

        def count_unique_groups_of_three_zeros(data):

            s = pd.Series(data)

            is_start_of_three_zeros = (s == 0) & (s.shift(-1) == 0) & (s.shift(-2) == 0)
            x = pd.Series(np.diff(np.where(is_start_of_three_zeros == True)).flatten())
            one_kill = (x != 1) & (x.shift(-1) != 1) & ~x.shift(1).isna()
            two_kills = (x != 1) & (x.shift(-1) != 1) & x.shift(1).isna()
            is_four = (x == 1) & (x.shift(-1) != 1) & (x.shift(1) != 1)
            is_five = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) != 1) & (x.shift(1) != 1)
            is_six = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) != 1) & (x.shift(1) != 1)
            is_seven = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) != 1) & (
                        x.shift(1) != 1)
            is_eight = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) == 1) & (
                        x.shift(-5) != 1) & (x.shift(1) != 1)
            is_nine = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) == 1) & (
                        x.shift(-5) == 1) & (x.shift(-6) != 1) & (x.shift(1) != 1)

            is_ten = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) == 1) & (
                        x.shift(-5) == 1) & (x.shift(-6) == 1) & (x.shift(-7) != 1) & (x.shift(1) != 1)
            is_eleven = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) == 1) & (
                        x.shift(-5) == 1) & (x.shift(-6) == 1) & (x.shift(-7) == 1) & (x.shift(-8) != 1) & (
                                    x.shift(1) != 1)
            is_twelve = (x == 1) & (x.shift(-1) == 1) & (x.shift(-2) == 1) & (x.shift(-3) == 1) & (x.shift(-4) == 1) & (
                        x.shift(-5) == 1) & (x.shift(-6) == 1) & (x.shift(-7) == 1) & (x.shift(-8) == 1) & (
                                    x.shift(-9) != 1) & (x.shift(1) != 1)
            count = one_kill.sum() + (two_kills.sum() * 2) + (is_four.sum() * 1.33) + (is_five.sum() * 1.66) + (
                        is_six.sum() * 2) + (is_seven.sum() * 2.33) + (is_eight.sum() * 2.66) + (is_nine.sum() * 3) + (
                                is_ten.sum() * 3.33) + (is_eleven.sum() * 3.66) + (is_twelve.sum() * 4)
            max_stops = 2
            if two_kills.any():
                max_stops = 3
            if one_kill.any():
                max_stops = 3
            if is_four.any():
                max_stops = 4
            if is_five.any():
                max_stops = 5
            if is_six.any():
                max_stops = 6
            if is_seven.any():
                max_stops = 7
            if is_eight.any():
                max_stops = 8
            if is_nine.any():
                max_stops = 9
            if is_ten.any():
                max_stops = 10
            if is_eleven.any():
                max_stops = 11
            if is_twelve.any():
                max_stops = 12

            if count == 0 and is_start_of_three_zeros.any():
                count = 1
                max_stops = 3

            return count, max_stops

        kill_log = []
        opp_kill_log = []
        max_stops_log = []
        opp_max_stop_log = []
        condition = team_poss_score['stint'].diff() > 1

        # 2. Create a group key using cumsum()
        # Each time the condition is True, it increments the group number
        group_key = condition.cumsum()

        # START WITH OPPONENTS POSS:

        # 3. Split the DataFrame into a list of DataFrames
        split_dfs = [group for _, group in player_stints_opp_poss.groupby(group_key)]

        # Print the resulting DataFrames
        for i, sub_df in enumerate(split_dfs):
            # print(f"--- DataFrame {i+1} ---")
            # print(sub_df)

            if team_poss_score['Team'][0] == team_poss_score['Home Team'][0]:
                player_team_opp_scores = sub_df['scoreAway'].astype(int)
            else:
                player_team_opp_scores = sub_df['scoreHome'].astype(int)
            kills, max_stops = count_unique_groups_of_three_zeros(np.diff(player_team_opp_scores))
            # print(np.diff(player_team_opp_scores))
            kill_log.append(kills)
            max_stops_log.append(max_stops)

        # NOW FOR TEAM POSS

        split_dfs = [group for _, group in player_stints_poss.groupby(group_key)]
        for i, sub_df in enumerate(split_dfs):
            # print(f"--- DataFrame {i+1} ---")
            # print(sub_df)

            if team_poss_score['Team'][0] == team_poss_score['Home Team'][0]:
                player_team_scores = sub_df['scoreHome'].astype(int)
            else:
                player_team_scores = sub_df['scoreAway'].astype(int)

            kills, max_stops = count_unique_groups_of_three_zeros(np.diff(player_team_scores))
            opp_kill_log.append(kills)
            opp_max_stop_log.append(max_stops)
        player_team_def_poss = player_stints_opp_poss['possession_no'].nunique()
        player_opp_def_poss = player_stints_poss['possession_no'].nunique()

        return [gameid, playerid, player, team_poss_score['Team'][0], player_team_def_poss, pd.Series(kill_log).sum(),
                pd.Series(max_stops_log).max(), team_poss_score['Opponent'][0], player_opp_def_poss,
                pd.Series(opp_kill_log).sum(), pd.Series(opp_max_stop_log).max()]

    except AttributeError as e:
        print(f"\n⚠️ Skipping game {gameid} - Error")
        # Return empty dataframe with expected structure
        return pd.DataFrame({'gameid': [0], 'playerid': [0], 'Player': [0], 'Team': [0], 'Def Poss': [0], 'Kills': [0],
                             'Max Stops': [0], 'Opponent': [0], 'Opp Def Poss': [0], 'Opp Kills': [0],
                             'Opp Max Stops': [0]})

    except Exception as e:
        print(f"\n⚠️ Skipping game {gameid} - error: {type(e).__name__}:{e}")
        return pd.DataFrame({'gameid': [0], 'playerid': [0], 'Player': [0], 'Team': [0], 'Def Poss': [0], 'Kills': [0],
                             'Max Stops': [0], 'Opponent': [0], 'Opp Def Poss': [0], 'Opp Kills': [0],
                             'Opp Max Stops': [0]})
