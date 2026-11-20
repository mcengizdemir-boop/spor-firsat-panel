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

    def test_no_future_leakage_or_duplicate_leagues(self):
        games = [
            {"matchID": 1, "matchDateTimeUTC": "2026-11-18T12:00:00Z",
             "matchIsFinished": True, "team1": {"teamId": 1, "teamName": "A"},
             "team2": {"teamId": 2, "teamName": "B"},
             "matchResults": [{"resultTypeID": 2, "pointsTeam1": 1, "pointsTeam2": 0}]},
            {"matchID": 2, "matchDateTimeUTC": "2026-11-20T17:00:00Z",
             "matchIsFinished": False, "team1": {"teamId": 1, "teamName": "A"},
             "team2": {"teamId": 2, "teamName": "B"}},
            {"matchID": 3, "matchDateTimeUTC": "2026-11-21T17:00:00Z",
             "matchIsFinished": True, "team1": {"teamId": 1, "teamName": "A"},
             "team2": {"teamId": 2, "teamName": "B"},
             "matchResults": [{"resultTypeID": 2, "pointsTeam1": 0, "pointsTeam2": 9}]},
        ]
        def opener(request, timeout=20):
            return FakeResponse(games if "/bl1/2026" in request.full_url else [])
        result = build(datetime(2026, 11, 20, 12, tzinfo=TZ), opener)
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["matches"][0]["home_strength"]["points_per_game"], 3)
        self.assertEqual(result["matches"][0]["home_form"]["results"], ["G"])
        self.assertEqual(result["coverage"]["with_verified_odds"], 0)
        self.assertEqual(result["coverage"]["with_independently_validated_predictions"], 0)

    def test_public_coverage_counts(self):
        data = json.loads(Path("fixtures.json").read_text(encoding="utf-8"))
        cv = data.get("coverage")
        if cv is None:
            self.skipTest("Published fixture data not yet refreshed with coverage")
        self.assertEqual(cv["fixtures"], len(data["matches"]))
        for key in ("with_five_match_form", "with_five_match_venue_form",
                    "with_team_strength", "with_verified_odds",
                    "with_verified_injuries", "with_independently_validated_predictions"):
            self.assertGreaterEqual(cv[key], 0)
            self.assertLessEqual(cv[key], cv["fixtures"])
        self.assertEqual(cv["with_verified_odds"], 0)
        self.assertEqual(cv["with_independently_validated_predictions"], 0)

    def test_provider_outage_does_not_publish_empty_calendar(self):
        def failed_opener(request, timeout=20):
            raise OSError("provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "All fixture providers failed"):
            build(datetime(2026, 11, 20, 12, tzinfo=TZ), failed_opener)

    def test_partial_provider_outage_is_counted(self):
        def partial_opener(request, timeout=20):
            if "/bl1/2026" in request.full_url:
                return FakeResponse([])
            raise OSError("provider unavailable")
        result = build(datetime(2026, 11, 20, 12, tzinfo=TZ), partial_opener)
        self.assertEqual(result["coverage"]["provider_successes"], 1)
        self.assertEqual(result["coverage"]["provider_failures"], 5)

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
