import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from dateutil.parser import isoparse
from .common import setup_logger, create_app, fetch_data

logger = setup_logger("NFLDATA")
app = create_app("nfldata_proxy")
BASE_URL = "https://api.sportsdata.io/v3/nfl/scores/json/"

LOGO_DIR = Path("/app/nfl_logos")
app.mount("/nfldata/logo", StaticFiles(directory=LOGO_DIR), name="nfl_logos")

# Cache configuration
CACHE_LIFE_MINUTES = int(os.getenv("NFLDATA_PROXY_CACHE_LIFE", "5"))
nfl_cache: Dict[str, dict] = {}
cache_expiry: Dict[str, datetime] = {}

# SportsDataIO API key
SPORTS_DATA_API_KEY = os.getenv("SPORTS_DATA_API_KEY")
if not SPORTS_DATA_API_KEY:
    logger.error("SPORTS_DATA_API_KEY environment variable not set")
    raise RuntimeError("SPORTS_DATA_API_KEY is required")

# Load team data
TEAMS_DATA_FILE = Path(__file__).parent / "nfl_teams.json"
try:
    with open(TEAMS_DATA_FILE) as f:
        TEAMS_DATA = json.load(f)
    TEAM_IDS = {alias.lower(): team["id"] for team in TEAMS_DATA for alias in team["aliases"]}
    TEAM_COLORS = {team["id"]: team["colors"] for team in TEAMS_DATA}
    TEAM_LOGO_FILENAMES = {team["id"]: team["logoImageFileName"] for team in TEAMS_DATA}
    TEAM_LOGO_BG_COLORS = {team["id"]: team["logoBackgroundColor"] for team in TEAMS_DATA}
    TEAM_CONFERENCES = {team["id"]: team["conference"] for team in TEAMS_DATA}
    TEAM_DIVISIONS = {team["id"]: team["division"] for team in TEAMS_DATA}
    TEAM_ABBREV_TO_ID = {team["abbreviation"].lower(): team["id"] for team in TEAMS_DATA}
except Exception as e:
    logger.error(f"Failed to load team data: {str(e)}")
    raise RuntimeError("Could not initialize team data")

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'NFL Data Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Teams loaded: {len(TEAMS_DATA)}")
    logger.info(f"→ Abbreviations loaded: {len(TEAM_ABBREV_TO_ID)}")
    logger.info(f"→ Rate limiting: {os.getenv('NFLDATA_PROXY_REQUESTS_PER_MINUTE', '15')}/minute")
    logger.info(f"→ Cache lifetime: {CACHE_LIFE_MINUTES} minutes ({'enabled' if CACHE_LIFE_MINUTES > 0 else 'disabled'})")
    logger.info("="*50 + "\n")

async def get_schedule(team_id: str, season: str) -> list:
    url = f"{BASE_URL}Schedules/{season}?key={SPORTS_DATA_API_KEY}"
    logger.info(f"Fetching schedule from: {url}")
    schedule_data = await fetch_data(url, logger, app_name="nfldata")
    if not schedule_data:
        logger.warning("No schedule data returned")
        return []
    
    logger.debug(f"Schedule response sample: {json.dumps(schedule_data[:2], indent=2)}")
    
    try:
        team_abbrev = next((t["abbreviation"].lower() for t in TEAMS_DATA if t["id"] == team_id), None)
        if not team_abbrev:
            logger.error(f"No abbreviation found for team_id {team_id}")
            return []
        
        games = [g for g in schedule_data if g.get("HomeTeam", "").lower() == team_abbrev or g.get("AwayTeam", "").lower() == team_abbrev]
        logger.info(f"Schedule data summary: Total games found: {len(games)}")
        for game in games:
            logger.info(f"Game date: {game.get('Date')}, Status: {game.get('Status')}, HomeScore: {game.get('HomeScore')}, AwayScore: {game.get('AwayScore')}, HomeTeamScore: {game.get('HomeTeamScore')}, AwayTeamScore: {game.get('AwayTeamScore')}, ScoreHome: {game.get('ScoreHome')}, ScoreAway: {game.get('ScoreAway')}")
        return games
    except Exception as e:
        logger.error(f"Error in get_schedule: {str(e)}")
        return []

async def get_standings(season: str) -> list:
    url = f"{BASE_URL}Standings/{season}?key={SPORTS_DATA_API_KEY}"
    logger.info(f"Fetching standings from: {url}")
    standings_data = await fetch_data(url, logger, app_name="nfldata")
    if not standings_data:
        logger.warning("No standings data returned")
        return []
    logger.debug(f"Standings response sample: {json.dumps(standings_data[:2], indent=2)}")
    return standings_data

async def get_division_teams(team_id: str) -> list:
    try:
        division = TEAM_DIVISIONS.get(team_id)
        if not division:
            logger.warning(f"No division found for team_id {team_id}")
            return []
        return [t["id"] for t in TEAMS_DATA if t["division"] == division]
    except Exception as e:
        logger.error(f"Error in get_division_teams: {str(e)}")
        return []

def calculate_standings_from_schedule(schedule: list, team_id: str, as_of_date: Optional[datetime] = None) -> dict:
    try:
        team_abbrev = next((t["abbreviation"].lower() for t in TEAMS_DATA if t["id"] == team_id), None)
        if not team_abbrev:
            logger.error(f"No abbreviation found for team_id {team_id}")
            return {"wins": 0, "losses": 0, "ties": 0, "games_played": 0, "winning_percentage": 0.0}

        wins = losses = ties = points_for = points_against = 0
        for game in schedule:
            if not game.get("Date") or game.get("Status") != "Final":
                logger.debug(f"Skipping game {game.get('GameKey')}: Date={game.get('Date')}, Status={game.get('Status')}")
                continue
            
            try:
                game_date = isoparse(game["Date"]).replace(tzinfo=timezone.utc)
                if as_of_date and game_date > as_of_date:
                    logger.debug(f"Skipping game {game.get('GameKey')}: game_date={game_date} > as_of_date={as_of_date}")
                    continue
            except ValueError as e:
                logger.error(f"Error parsing game date {game.get('Date')} for game {game.get('GameKey')}: {str(e)}")
                continue

            home_team = game.get("HomeTeam", "").lower()
            away_team = game.get("AwayTeam", "").lower()
            home_score = game.get("HomeScore", game.get("HomeTeamScore", game.get("ScoreHome")))
            away_score = game.get("AwayScore", game.get("AwayTeamScore", game.get("ScoreAway")))

            logger.debug(f"Processing game {game.get('GameKey')}: Home={home_team}, Away={away_team}, Score={home_score}-{away_score}, TeamAbbrev={team_abbrev}")

            if home_score is None or away_score is None:
                logger.warning(f"Skipping game {game.get('GameKey')}: Missing scores (HomeScore={game.get('HomeScore')}, AwayScore={game.get('AwayScore')}, HomeTeamScore={game.get('HomeTeamScore')}, AwayTeamScore={game.get('AwayTeamScore')}, ScoreHome={game.get('ScoreHome')}, ScoreAway={game.get('ScoreAway')})")
                continue
            if home_team != team_abbrev and away_team != team_abbrev:
                logger.debug(f"Skipping game {game.get('GameKey')}: Team {team_abbrev} not involved")
                continue

            if home_team == team_abbrev:
                points_for += home_score
                points_against += away_score
                if home_score > away_score:
                    wins += 1
                elif home_score < away_score:
                    losses += 1
                else:
                    ties += 1
            elif away_team == team_abbrev:
                points_for += away_score
                points_against += home_score
                if away_score > home_score:
                    wins += 1
                elif away_score < home_score:
                    losses += 1
                else:
                    ties += 1

        games_played = wins + losses + ties
        winning_percentage = (wins + 0.5 * ties) / games_played if games_played > 0 else 0.0
        logger.info(f"Standings calculated for team {team_id}: Wins={wins}, Losses={losses}, Ties={ties}")
        return {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "games_played": games_played,
            "winning_percentage": round(winning_percentage, 3),
            "points_for": points_for,
            "points_against": points_against
        }
    except Exception as e:
        logger.error(f"Error calculating standings for team {team_id}: {str(e)}")
        return {"wins": 0, "losses": 0, "ties": 0, "games_played": 0, "winning_percentage": 0.0}

async def proxy_endpoint(request: Request):
    try:
        team_name = request.query_params.get("teamName", "").lower()
        as_of_date_str = request.query_params.get("asOfDate")
        force_refresh = request.query_params.get("force", "").lower() == "true"
        
        if not team_name:
            raise HTTPException(status_code=400, detail="teamName parameter is required")
        
        team_id = TEAM_IDS.get(team_name)
        if not team_id:
            raise HTTPException(status_code=404, detail=f"Team {team_name} not found")
        
        logger.info(f"Resolved '{team_name}' to team ID: {team_id}")
        
        as_of_date = None
        if as_of_date_str:
            try:
                as_of_date = datetime.strptime(as_of_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                logger.info(f"Using reference date: {as_of_date.isoformat()}")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid asOfDate format, expected YYYY-MM-DD")
        
        cache_key = f"{team_id}:{as_of_date_str}"
        if not force_refresh and cache_key in nfl_cache and cache_expiry.get(cache_key, datetime.now(timezone.utc)) > datetime.now(timezone.utc):
            logger.info(f"Returning cached response for {cache_key}")
            return nfl_cache[cache_key]
        
        logger.info(f"Fetching live data for team {team_id} (forced refresh: {force_refresh})")
        
        team_data = next((t for t in TEAMS_DATA if t["id"] == team_id), {})
        if not team_data:
            raise HTTPException(status_code=404, detail="Team data not found")
        
        season = "2024"
        standings_data = await get_standings(season)
        schedule = await get_schedule(team_id, season)
        
        standings = None
        for s in standings_data:
            if str(s.get("TeamID")) == team_id:
                standings = {
                    "wins": s.get("Wins", 0),
                    "losses": s.get("Losses", 0),
                    "ties": s.get("Ties", 0),
                    "games_played": s.get("Wins", 0) + s.get("Losses", 0) + s.get("Ties", 0),
                    "winning_percentage": round(s.get("Percentage", 0.0), 3),
                    "points_for": s.get("PointsFor", 0),
                    "points_against": s.get("PointsAgainst", 0),
                    "conference": s.get("Conference", "N/A"),
                    "division": s.get("Division", "N/A"),
                    "record": f"{s.get('Wins', 0)}-{s.get('Losses', 0)}-{s.get('Ties', 0)}"
                }
                break
        
        if not standings:
            logger.warning(f"No standings data for team {team_id}, using zeroed standings")
            standings = {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "games_played": 0,
                "winning_percentage": 0.0,
                "points_for": 0,
                "points_against": 0,
                "conference": TEAM_CONFERENCES.get(team_id, "N/A"),
                "division": TEAM_DIVISIONS.get(team_id, "N/A"),
                "record": "0-0-0"
            }
        
        # Adjust standings for as_of_date by subtracting games after the date
        if as_of_date and standings["games_played"] > 0:
            logger.info(f"Adjusting standings for team {team_id} to as_of_date {as_of_date}")
            adjusted_standings = calculate_standings_from_schedule(schedule, team_id, as_of_date)
            if adjusted_standings["games_played"] > 0:
                standings = {
                    "wins": adjusted_standings["wins"],
                    "losses": adjusted_standings["losses"],
                    "ties": adjusted_standings["ties"],
                    "games_played": adjusted_standings["games_played"],
                    "winning_percentage": adjusted_standings["winning_percentage"],
                    "points_for": adjusted_standings["points_for"],
                    "points_against": adjusted_standings["points_against"],
                    "conference": standings["conference"],
                    "division": standings["division"],
                    "record": f"{adjusted_standings['wins']}-{adjusted_standings['losses']}-{adjusted_standings['ties']}"
                }
            else:
                logger.warning(f"No valid games found before {as_of_date} for team {team_id}, using zeroed standings")
                standings = {
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "games_played": 0,
                    "winning_percentage": 0.0,
                    "points_for": 0,
                    "points_against": 0,
                    "conference": standings["conference"],
                    "division": standings["division"],
                    "record": "0-0-0"
                }
        
        last_game = None
        next_games = []
        if schedule:
            sorted_schedule = sorted(
                [g for g in schedule if g.get("Date") and g.get("Status") == "Final"],
                key=lambda x: isoparse(x["Date"]).replace(tzinfo=timezone.utc),
                reverse=True
            )
            for game in sorted_schedule:
                game_date = isoparse(game["Date"]).replace(tzinfo=timezone.utc)
                if as_of_date and game_date > as_of_date:
                    continue
                home_team = game.get("HomeTeam", "").lower()
                away_team = game.get("AwayTeam", "").lower()
                home_score = game.get("HomeScore", game.get("HomeTeamScore", game.get("ScoreHome", 0)))
                away_score = game.get("AwayScore", game.get("AwayTeamScore", game.get("ScoreAway", 0)))
                if home_team != team_data["abbreviation"].lower() and away_team != team_data["abbreviation"].lower():
                    continue
                if last_game is None:
                    result = "Tied"
                    if home_score > away_score:
                        result = "Won" if home_team == team_data["abbreviation"].lower() else "Lost"
                    elif home_score < away_score:
                        result = "Lost" if home_team == team_data["abbreviation"].lower() else "Won"
                    last_game = {
                        "date": game_date.strftime("%b %d"),
                        "day": game_date.strftime("%a"),
                        "opponent": game.get("AwayTeam") if home_team == team_data["abbreviation"].lower() else game.get("HomeTeam"),
                        "score": f"{home_score}-{away_score}",
                        "result": result,
                        "gameTime": game_date.strftime("%I:%M %p"),
                        "gameId": game.get("GameKey", "N/A")
                    }
                break
            
            future_schedule = sorted(
                [g for g in schedule if g.get("Date") and g.get("Status") != "Final"],
                key=lambda x: isoparse(x["Date"]).replace(tzinfo=timezone.utc)
            )
            for game in future_schedule:
                game_date = isoparse(game["Date"]).replace(tzinfo=timezone.utc)
                if as_of_date and game_date <= as_of_date:
                    continue
                home_team = game.get("HomeTeam", "").lower()
                away_team = game.get("AwayTeam", "").lower()
                if home_team != team_data["abbreviation"].lower() and away_team != team_data["abbreviation"].lower():
                    continue
                next_games.append({
                    "date": game_date.strftime("%b %d"),
                    "day": game_date.strftime("%a"),
                    "opponent": game.get("AwayTeam") if home_team == team_data["abbreviation"].lower() else game.get("HomeTeam"),
                    "gameTime": game_date.strftime("%I:%M %p"),
                    "gameId": game.get("GameKey", "N/A")
                })
                if len(next_games) >= 3:
                    break
        
        response = {
            "teamId": team_id,
            "season": season,
            "team": {
                "fullName": team_data.get("name", ""),
                "shortName": team_data.get("abbreviation", ""),
                "colors": team_data.get("colors", ""),
                "logoUrl": f"/nfldata/logo/{team_data.get('logoImageFileName', '')}",
                "logoImageFileName": team_data.get("logoImageFileName", ""),
                "logoBackgroundColor": team_data.get("logoBackgroundColor", ""),
                "abbreviation": team_data.get("abbreviation", ""),
                "standingSummary": standings.get("record", "0-0-0"),
                "conference": team_data.get("conference", ""),
                "division": team_data.get("division", "")
            },
            "standings": standings,
            "lastGame": last_game,
            "nextGames": next_games,
            "proxy-info": {
                "cachedResponse": False,
                "status_code": 200,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
        if CACHE_LIFE_MINUTES > 0:
            nfl_cache[cache_key] = response
            cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(minutes=CACHE_LIFE_MINUTES)
        
        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in proxy_endpoint for team {team_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.api_route("/proxy", methods=["GET"])
@app.state.limiter.limit(os.getenv("NFLDATA_PROXY_REQUESTS_PER_MINUTE", "15") + "/minute")
async def nfldata_proxy(request: Request):
    logger.info(f"{datetime.now().isoformat()} Received request for team: {request.query_params.get('teamName')}")
    return await proxy_endpoint(request)
    
@app.get("/health")
async def health():
    return {"status": "OK"}    
