#NBA.COM TEAM PAGES
from dataclasses import dataclass
import json
import time
import random
import pandas as pd
from bs4 import BeautifulSoup


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
    nba_roster_df["player_clean"] = (
        nba_roster_df["PLAYER"].apply(clean_name).str.lower().str.replace(".", "", regex=False)
    )

print(f"\n\nRoster rows: {len(nba_roster_df)} | Coaches: {len(nba_coaches_df)} | Teams: {len(nba_team_info_df)}")
if failed:
    print(f"{len(failed)} teams failed: {failed}")

nba_roster_df.to_csv("NBA_com_rosters_2026-27.csv", index=False)
nba_coaches_df.to_csv("NBA_com_coaches_2026-27.csv", index=False)
nba_team_info_df.to_csv("NBA_com_team_info_2026-27.csv", index=False)
nba_roster_df.head()
