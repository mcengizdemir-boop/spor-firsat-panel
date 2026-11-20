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
    finished = {}
    provider_checks = []
    for league_id, league_name in LEAGUES.items():
        for season in (now.year - 1, now.year):
            url = f"https://api.openligadb.de/getmatchdata/{league_id}/{season}"
            try:
                request = Request(url, headers={"User-Agent": "SporFirsatDashboard/1.0"})
                with opener(request, timeout=20) as response:
                    events = json.load(response)
                provider_checks.append({"league": league_id, "season": season, "ok": isinstance(events, list)})
            except Exception as exc:
                print("Fixture provider unavailable:", league_id, season, type(exc).__name__)
                provider_checks.append({"league": league_id, "season": season, "ok": False})
                continue
            if not isinstance(events, list):
                continue
            for match in events:
                try:
                    raw = match["matchDateTimeUTC"]
                    kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
                    if match.get("matchIsFinished") and kickoff < now:
                        for result in match.get("matchResults") or []:
                            if result.get("resultTypeID") == 2:
                                try:
                                    finished.setdefault(league_id, []).append(
                                        (kickoff, match["team1"]["teamId"],
                                         match["team2"]["teamId"],
                                         int(result["pointsTeam1"]), int(result["pointsTeam2"])))
                                except (KeyError, TypeError, ValueError):
                                    pass
                                break
                    if kickoff.date() not in dates:
                        continue
                    matches.append({
                        "id": match["matchID"], "kickoff": kickoff.isoformat(),
                        "league": league_name, "league_id": league_id,
                        "home_id": match["team1"]["teamId"], "away_id": match["team2"]["teamId"],
                        "home": match["team1"]["teamName"],
                        "away": match["team2"]["teamName"],
                        "status": "Tamamlandı" if match.get("matchIsFinished") else "Planlandı",
                        "source": "OpenLigaDB"
                    })
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
    unique = {(m["league"], str(m["id"])): m for m in matches}
    for match in unique.values():
        for side in ("home", "away"):
            team = match[side + "_id"]
            prior = sorted((g for g in finished.get(match["league_id"], [])
                            if g[0] < datetime.fromisoformat(match["kickoff"])
                            and team in (g[1], g[2])),
                           key=lambda g: g[0], reverse=True)[:5]
            form = []
            for _, home, away, hg, ag in prior:
                own, other = (hg, ag) if team == home else (ag, hg)
                form.append("G" if own > other else "B" if own == other else "M")
            match[side + "_form"] = {"results": form, "samples": len(form),
                                      "sufficient": len(form) == 5}
            venue_games = sorted((g for g in finished.get(match["league_id"], [])
                                  if g[0] < datetime.fromisoformat(match["kickoff"])
                                  and (g[1] == team if side == "home" else g[2] == team)),
                                 key=lambda g: g[0], reverse=True)[:5]
            wins = draws = losses = goals_for = goals_against = 0
            for _, home_id, away_id, hg, ag in venue_games:
                own, other = (hg, ag) if side == "home" else (ag, hg)
                wins += own > other
                draws += own == other
                losses += own < other
                goals_for += own
                goals_against += other
            match[side + "_venue_form"] = {
                "location": "home" if side == "home" else "away",
                "sample_size": len(venue_games), "wins": wins,
                "draws": draws, "losses": losses,
                "goals_for": goals_for, "goals_against": goals_against,
                "sufficient": len(venue_games) == 5,
                "source": "OpenLigaDB completed league matches"
            }
    # Relative opponent strength: historical points per game in the same league.
    # Descriptive evidence only, never a betting probability.
    for match in unique.values():
        games = [g for g in finished.get(match["league_id"], [])
                 if g[0] < datetime.fromisoformat(match["kickoff"])]
        points = {}
        played = {}
        for _, home, away, hg, ag in games:
            for team in (home, away):
                played[team] = played.get(team, 0) + 1
            home_points, away_points = (3, 0) if hg > ag else (0, 3) if ag > hg else (1, 1)
            points[home] = points.get(home, 0) + home_points
            points[away] = points.get(away, 0) + away_points
        for side in ("home", "away"):
            team = match[side + "_id"]
            count = played.get(team, 0)
            match[side + "_strength"] = {
                "points_per_game": round(points.get(team, 0) / count, 2) if count else None,
                "matches": count,
                "metric": "league points per game; not a win probability",
                "source": "OpenLigaDB completed matches"
            }
    if provider_checks and not any(check["ok"] for check in provider_checks):
        raise RuntimeError("All fixture providers failed; preserve the last published calendar")
    coverage = {
        "fixtures": len(unique),
        "provider_requests": len(provider_checks),
        "provider_successes": sum(check["ok"] for check in provider_checks),
        "provider_failures": sum(not check["ok"] for check in provider_checks),
        "leagues": sorted({m["league"] for m in unique.values()}),
        "with_five_match_form": sum(
            bool(m["home_form"]["sufficient"] and m["away_form"]["sufficient"])
            for m in unique.values()),
        "with_five_match_venue_form": sum(
            bool(m["home_venue_form"]["sufficient"] and m["away_venue_form"]["sufficient"])
            for m in unique.values()),
        "with_team_strength": sum(
            bool(m["home_strength"]["matches"] and m["away_strength"]["matches"])
            for m in unique.values()),
        "with_verified_odds": 0,
        "with_verified_injuries": 0,
        "with_independently_validated_predictions": 0,
    }
    return {"coverage": coverage, "generated_at": now.isoformat(), "source": "OpenLigaDB",
            "scope": "German leagues 1-3; no odds or model predictions",
            "matches": sorted(unique.values(), key=lambda m: m["kickoff"])}


if __name__ == "__main__":
    Path("fixtures.json").write_text(
        json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
