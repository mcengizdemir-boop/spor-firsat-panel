"""Offline regression tests for published football data. No network needed."""
import json
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_public_fixtures import build

TZ = ZoneInfo("Europe/Istanbul")


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps(self.data).encode("utf-8")


class FixturesTests(unittest.TestCase):
    def test_form_venue_and_strength(self):
        games = []
        for i in range(6):
            games.append({
                "matchID": i + 1, "matchDateTimeUTC": f"2026-11-{10+i:02d}T12:00:00Z",
                "matchIsFinished": True,
                "team1": {"teamId": 1, "teamName": "Home"},
                "team2": {"teamId": 2, "teamName": "Away"},
                "matchResults": [{"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1}],
            })
        games.append({
            "matchID": 100, "matchDateTimeUTC": "2026-11-20T17:00:00Z",
            "matchIsFinished": False,
            "team1": {"teamId": 1, "teamName": "Home"},
            "team2": {"teamId": 2, "teamName": "Away"},
        })

        def opener(request, timeout=20):
            url = request.full_url
            return FakeResponse(games if "/bl1/2026" in url else [])

        result = build(datetime(2026, 11, 20, 12, tzinfo=TZ), opener)
        self.assertEqual(len(result["matches"]), 1)
        match = result["matches"][0]
        self.assertEqual(match["home_form"]["results"], ["G"] * 5)
        self.assertEqual(match["away_form"]["results"], ["M"] * 5)
        self.assertEqual(match["home_venue_form"]["wins"], 5)
        self.assertEqual(match["away_venue_form"]["losses"], 5)
        self.assertEqual(match["home_strength"]["points_per_game"], 3)
        self.assertEqual(match["away_strength"]["points_per_game"], 0)

    def test_public_json_schema(self):
        data = json.loads(Path("fixtures.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data["matches"], list)
        for match in data["matches"]:
            self.assertIn("kickoff", match)
            self.assertIn("league", match)
            self.assertIn("home", match)
            self.assertIn("away", match)
            self.assertNotIn("api_key", match)
            self.assertNotIn("betting_pick", match)


if __name__ == "__main__":
    unittest.main()
