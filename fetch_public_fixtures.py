"""Publish only public fixture facts. No credentials, predictions or betting advice."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")

def build(now=None, opener=urlopen):
    now = now or datetime.now(TZ)
    dates = {now.date(), (now + timedelta(days=1)).date()}
    matches = []
    # OpenLigaDB season year is the starting year of the season.
    for season in {now.year - 1, now.year}:
        url = f"https://api.openligadb.de/getmatchdata/bl1/{season}"
        try:
            with opener(Request(url, headers={"User-Agent": "SporFirsatDashboard/1.0"}), timeout=20) as response:
                events = json.load(response)
        except Exception as exc:
            print("Fixture provider unavailable for", season, type(exc).__name__)
            continue
        if not isinstance(events, list):
            continue
        for m in events:
            try:
                raw = m.get("matchDateTimeUTC")
                kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
                if kickoff.date() not in dates:
                    continue
                matches.append({"id": m["matchID"], "kickoff": kickoff.isoformat(),
                                "league": "Bundesliga", "home": m["team1"]["teamName"],
                                "away": m["team2"]["teamName"],
                                "status": "Tamamlandı" if m.get("matchIsFinished") else "Planlandı",
                                "source": "OpenLigaDB"})
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
    unique = {str(m["id"]): m for m in matches}
    return {"generated_at": now.isoformat(), "source": "OpenLigaDB",
            "scope": "Bundesliga only; no model probabilities or odds",
            "matches": sorted(unique.values(), key=lambda m: m["kickoff"])}

if __name__ == "__main__":
    Path("fixtures.json").write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8")
