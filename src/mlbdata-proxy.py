import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
import json
from pathlib import Path
from fastapi import HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from .common import setup_logger, create_app, fetch_data

logger = setup_logger("MLBDATA")
app = create_app("mlbdata_proxy")
BASE_URL = "https://statsapi.mlb.com/api/v1/"

# Cache configuration
CACHE_LIFE_MINUTES = int(os.getenv("MLBDATA_PROXY_CACHE_LIFE", "5"))  # 0 disables caching
mlb_cache: Dict[str, dict] = {}
cache_expiry: Dict[str, datetime] = {}

# Load team data from external JSON file
TEAMS_DATA_FILE = Path(__file__).parent / "mlb_teams.json"

try:
    with open(TEAMS_DATA_FILE) as f:
        TEAMS_DATA = json.load(f)
    # Create lookup dictionaries
    TEAM_IDS = {alias.lower(): team["id"] for team in TEAMS_DATA for alias in team["aliases"]}
    TEAM_COLORS = {team["id"]: team["colors"] for team in TEAMS_DATA}
except Exception as e:
    logger.error(f"Failed to load team data: {str(e)}")
    raise RuntimeError("Could not initialize team data")

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'MLB Data Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Teams loaded: {len(TEAMS_DATA)}")
    logger.info(f"→ Rate limiting: {os.getenv('MLBDATA_PROXY_REQUESTS_PER_MINUTE', '15')} requests/minute per IP")
    logger.info(f"→ Cache lifetime: {CACHE_LIFE_MINUTES} minutes ({'enabled' if CACHE_LIFE_MINUTES > 0 else 'disabled'})")
    logger.info("→ Force refresh: supported via &force=true parameter")
    logger.info("="*50 + "\n")

class MLBRequest(BaseModel):
    teamName: str

def get_current_season() -> str:
    """Get current season year based on today's date"""
    today = datetime.now()
    return str(today.year if today.month >= 3 else today.year - 1)

def format_division_rank(rank: str) -> str:
    """Convert numeric rank to ordinal string (1 -> 1st, 2 -> 2nd, etc.)"""
    try:
        num = int(rank)
        if 11 <= (num % 100) <= 13:
            return f"{num}th"
        return {
            1: f"{num}st",
            2: f"{num}nd",
            3: f"{num}rd"
        }.get(num % 10, f"{num}th")
    except (ValueError, TypeError):
        return rank

def parse_colors(color_str: str) -> List[Dict[str, str]]:
    """Parse color string into structured objects"""
    if not color_str or color_str == "N/A":
        return []
    
    colors = []
    for color_part in color_str.split(","):
        color_part = color_part.strip()
        if "(" in color_part and ")" in color_part:
            name_part, code_part = color_part.split("(", 1)
            colors.append({
                "name": name_part.strip(),
                "code": code_part.split(")")[0].strip()
            })
        else:
            colors.append({
                "name": color_part,
                "code": "#000000"  # Default black if no code provided
            })
    return colors

def format_game_date(date_str: str) -> str:
    """Format date as 'Apr 2'"""
    if not date_str or date_str == "N/A":
        return "N/A"
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%b %-d")
    except ValueError:
        return date_str

def transform_data(data: dict, cached: bool = False) -> dict:
    """Add proxy-info to the MLB data response"""
    if not data:
        raise HTTPException(status_code=502, detail="Empty API response")
    
    transformed = dict(data)
    transformed["proxy-info"] = {
        "cachedResponse": cached,
        "status_code": 200,
        "timestamp": datetime.utcnow().isoformat()
    }
    return transformed

def get_short_team_name(full_name: str) -> str:
    """Extract short team name by removing city"""
    if not full_name:
        return "N/A"
    return full_name.split()[-1].strip()

def get_day_of_week(date_str: str) -> str:
    """Get day of week from date string (YYYY-MM-DD)"""
    if not date_str or date_str == "N/A":
        return "N/A"
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%A")
    except ValueError:
        return "N/A"

def format_game_time(time_str: str) -> str:
    """Convert 24-hour time to 12-hour format"""
    if not time_str or time_str == "N/A":
        return "N/A"
    try:
        time_obj = datetime.strptime(time_str, "%H:%M")
        return time_obj.strftime("%I:%M %p").lstrip('0')
    except ValueError:
        return time_str

def get_cache_key(params: dict) -> str:
    """Generate a unique cache key from request parameters"""
    cache_params = params.copy()
    cache_params.pop('force', None)
    return json.dumps(cache_params, sort_keys=True)

async def get_team_id(team_identifier: str) -> int:
    """Convert team name or ID string to numeric ID"""
    if team_identifier.isdigit():
        return int(team_identifier)
    
    lower_team = team_identifier.lower().replace(" ", "")
    if lower_team in TEAM_IDS:
        return TEAM_IDS[lower_team]
    
    raise HTTPException(status_code=400, detail=f"Unknown team: {team_identifier}")

async def get_team_details(team_id: str) -> dict:
    """Fetch team details from MLB API"""
    team_url = f"{BASE_URL}teams/{team_id}?hydrate=division,league,sport"
    team_data = await fetch_data(team_url, logger, app_name="mlbdata")
    if not team_data or "teams" not in team_data:
        raise HTTPException(status_code=502, detail="Failed to fetch team data")
    
    team_info = team_data["teams"][0]
    division_short = team_info.get("division", {}).get("nameShort", "N/A")
    
    return {
        "team_info": team_info,
        "division_short": division_short
    }

async def get_standings(league_id: str, season: str, team_id: str) -> Optional[dict]:
    """Fetch standings for a specific team"""
    standings_url = f"{BASE_URL}standings?leagueId={league_id}&season={season}"
    standings_data = await fetch_data(standings_url, logger, app_name="mlbdata")
    if standings_data and "records" in standings_data:
        for record in standings_data["records"]:
            for team_record in record["teamRecords"]:
                if team_record["team"]["id"] == int(team_id):
                    # Format division rank to ordinal
                    if "divisionRank" in team_record:
                        team_record["formattedDivisionRank"] = format_division_rank(team_record["divisionRank"])
                    return team_record
    return None

async def get_schedule(team_id: str, season: str) -> list:
    """Fetch schedule for a specific team"""
    schedule_url = f"{BASE_URL}schedule?sportId=1&teamId={team_id}&season={season}"
    schedule_data = await fetch_data(schedule_url, logger, app_name="mlbdata")
    if not schedule_data or "dates" not in schedule_data:
        raise HTTPException(status_code=502, detail="Failed to fetch schedule data")
    return [game for date in schedule_data["dates"] for game in date["games"]]

async def proxy_endpoint(request: Request):
    # Get query parameters
    team_identifier = request.query_params.get("teamName")
    if not team_identifier:
        raise HTTPException(status_code=400, detail="teamName parameter is required")

    try:
        team_id = await get_team_id(team_identifier)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid team identifier")

    season = get_current_season()
    force_refresh = request.query_params.get("force", "").lower() == "true"

    params = {
        "teamId": str(team_id),
        "season": season
    }
    cache_key = get_cache_key(params)
    
    # Check cache if enabled and not forcing refresh
    if CACHE_LIFE_MINUTES > 0 and not force_refresh:
        cached_data = mlb_cache.get(cache_key)
        cache_valid = cache_expiry.get(cache_key, datetime.min) > datetime.utcnow()
        
        if cached_data and cache_valid:
            logger.info(f"Returning cached data for team {team_id}")
            return transform_data(cached_data, cached=True)

    # Fetch fresh data
    logger.info(f"Fetching live data for team {team_id}{' (forced refresh)' if force_refresh else ''}")
    try:
        result = {
            "teamId": team_id,
            "season": season
        }

        # Team Details
        team_data = await get_team_details(team_id)
        team_info = team_data["team_info"]
        full_team_name = team_info.get("name", "Unknown Team")
        
        result["team"] = {
            "fullName": full_team_name,
            "shortName": get_short_team_name(full_team_name),
            "colors": parse_colors(TEAM_COLORS.get(team_id, "")),
            "logoUrl": f"https://www.mlbstatic.com/team-logos/{team_id}.svg"
        }

        # Get league ID from team details if available
        league_id = None
        if "league" in team_info:
            league_id = team_info["league"]["id"]
        elif "leagues" in team_info and len(team_info["leagues"]) > 0:
            league_id = team_info["leagues"][0]["id"]

        # Standings with formatted division rank
        if league_id:
            standings = await get_standings(league_id, season, team_id)
            if standings:
                result["record"] = f"{standings['wins']}-{standings['losses']}"
                result["standings"] = {
                    "division": team_data["division_short"],
                    "divisionRank": standings.get("formattedDivisionRank", format_division_rank(standings.get("divisionRank", "N/A"))),
                    "winningPercentage": standings["winningPercentage"],
                    "gamesBack": standings.get("gamesBack", "N/A")
                }

        # Schedule
        games = await get_schedule(team_id, season)
        today = datetime.now(timezone.utc)

        # Last Game
        last_game = next(
            (g for g in sorted(games, key=lambda x: x["gameDate"], reverse=True)
            if datetime.strptime(g["gameDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < today
            and g["status"]["detailedState"] == "Final"), None
        )
        last_game_date = last_game["gameDate"][:10] if last_game else "N/A"
        result["lastGame"] = {
            "date": format_game_date(last_game_date),
            "day": get_day_of_week(last_game_date),
            "opponent": (
                last_game["teams"]["away"]["team"]["name"] if last_game["teams"]["home"]["team"]["id"] == int(team_id)
                else last_game["teams"]["home"]["team"]["name"]
            ) if last_game else "N/A",
            "score": (
                f"{last_game['teams']['away']['score']}-{last_game['teams']['home']['score']}"
                if last_game else "N/A"
            ),
            "result": (
                "Won" if last_game and (
                    (last_game["teams"]["home"]["team"]["id"] == int(team_id) and last_game["teams"]["home"]["score"] > last_game["teams"]["away"]["score"]) or
                    (last_game["teams"]["away"]["team"]["id"] == int(team_id) and last_game["teams"]["away"]["score"] > last_game["teams"]["home"]["score"])
                ) else "Lost" if last_game else "N/A"
            ),
            "gameTime": format_game_time(last_game["gameDate"][11:16]) if last_game else "N/A"
        }

        # Next Game
        next_game = next(
            (g for g in sorted(games, key=lambda x: x["gameDate"])
             if datetime.strptime(g["gameDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) >= today
             and g["status"]["detailedState"] in ["Scheduled", "Pre-Game"]), None
        )
        next_game_date = next_game["gameDate"][:10] if next_game else "N/A"
        result["nextGame"] = {
            "date": format_game_date(next_game_date),
            "day": get_day_of_week(next_game_date),
            "opponent": (
                next_game["teams"]["away"]["team"]["name"] if next_game["teams"]["home"]["team"]["id"] == int(team_id)
                else next_game["teams"]["home"]["team"]["name"]
            ) if next_game else "N/A",
            "location": (
                "Home" if next_game and next_game["teams"]["home"]["team"]["id"] == int(team_id) else "Away" if next_game else "N/A"
            ),
            "probablePitcher": (
                next_game["teams"]["home"]["probablePitcher"]["fullName"] if next_game and next_game["teams"]["home"]["team"]["id"] == int(team_id) and "probablePitcher" in next_game["teams"]["home"]
                else next_game["teams"]["away"]["probablePitcher"]["fullName"] if next_game and next_game["teams"]["away"]["team"]["id"] == int(team_id) and "probablePitcher" in next_game["teams"]["away"]
                else "TBD"
            ),
            "gameTime": format_game_time(next_game["gameDate"][11:16]) if next_game else "N/A",
            "tvBroadcast": next_game.get("broadcasts", [{}])[0].get("name", "N/A") if next_game else "N/A"
        }

        # Update cache if enabled
        if CACHE_LIFE_MINUTES > 0:
            mlb_cache[cache_key] = result
            cache_expiry[cache_key] = datetime.utcnow() + timedelta(minutes=CACHE_LIFE_MINUTES)
            logger.info(f"Cached data for team {team_id} for {CACHE_LIFE_MINUTES} minutes")
        
        return transform_data(result, cached=False)
    except HTTPException as e:
        if CACHE_LIFE_MINUTES > 0 and cache_key in mlb_cache and not force_refresh:
            logger.warning(f"API failed, returning cached data for team {team_id}")
            return transform_data(mlb_cache[cache_key], cached=True)
        raise e

# Custom route handler
@app.api_route("/proxy", methods=["GET"])
@app.state.limiter.limit(os.getenv("MLBDATA_PROXY_REQUESTS_PER_MINUTE", "15") + "/minute")
async def mlbdata_proxy(request: Request):
    logger.info(f"{datetime.now().isoformat()} Received {request.method} request: {request.url} from {get_remote_address(request)}")
    return await proxy_endpoint(request)
