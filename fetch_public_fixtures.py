"""Publish public fixture facts without API credentials or betting recommendations."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
LEAGUES = {"bl1": "Bundesliga", "bl2": "2. Bundesliga", "bl3": "3. Liga"}


def build(now=None, opener=urlopen):
    now = now or datetime.now(TZ)
    dates = {now.date(), (now + timedelta(days=1)).date()}
    matches = []
    for league_id, league_name in LEAGUES.items():
        for season in (now.year - 1, now.year):
            url = f"https://api.openligadb.de/getmatchdata/{league_id}/{season}"
            try:
                request = Request(url, headers={"User-Agent": "SporFirsatDashboard/1.0"})
                with opener(request, timeout=20) as response:
                    events = json.load(response)
            except Exception as exc:
                print("Fixture provider unavailable:", league_id, season, type(exc).__name__)
                continue
            if not isinstance(events, list):
                continue
            for match in events:
                try:
                    raw = match["matchDateTimeUTC"]
                    kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
                    if kickoff.date() not in dates:
                        continue
                    matches.append({
                        "id": match["matchID"], "kickoff": kickoff.isoformat(),
                        "league": league_name, "home": match["team1"]["teamName"],
                        "away": match["team2"]["teamName"],
                        "status": "Tamamlandı" if match.get("matchIsFinished") else "Planlandı",
                        "source": "OpenLigaDB"
                    })
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
    unique = {(m["league"], str(m["id"])): m for m in matches}
    return {"generated_at": now.isoformat(), "source": "OpenLigaDB",
            "scope": "German leagues 1-3; no odds or model predictions",
            "matches": sorted(unique.values(), key=lambda m: m["kickoff"])}


if __name__ == "__main__":
    Path("fixtures.json").write_text(
        json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
