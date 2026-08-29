"""Tests para el sistema de puntuación de jugadores."""
from __future__ import annotations

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from backend.laliga.models import Player, PlayerStats
from backend.strategy.player_scoring import PlayerScoring, ScoredPlayer
from backend.strategy.goalkeeper_strategy import GoalkeeperStrategy


def make_player(
    position="MID",
    market_value=10_000_000,
    points=100,
    last_5_avg=8.0,
    season_points=100,
    total_matches=20,
    status="ok",
) -> Player:
    stats = PlayerStats(
        season_points=season_points,
        last_5_avg=last_5_avg,
        total_matches=total_matches,
        points_per_match=season_points / max(total_matches, 1),
    )
    return Player(
        id="p1",
        name="Test Player",
        team="Test FC",
        position=position,
        market_value=market_value,
        clause_value=market_value * 1.2,
        points=points,
        status=status,
        stats=stats,
    )


class TestPlayerScoring:
    def setup_method(self):
        self.scorer = PlayerScoring()

    def test_score_returns_scored_player(self):
        p = make_player()
        result = self.scorer.score_player(p)
        assert isinstance(result, ScoredPlayer)
        assert 0.0 <= result.composite <= 1.0

    def test_high_form_scores_higher(self):
        low_form  = make_player(last_5_avg=2.0)
        high_form = make_player(last_5_avg=14.0)
        s_low  = self.scorer.score_player(low_form)
        s_high = self.scorer.score_player(high_form)
        assert s_high.composite > s_low.composite

    def test_injured_player_penalised(self):
        ok      = make_player(status="ok")
        injured = make_player(status="injured")
        s_ok      = self.scorer.score_player(ok)
        s_injured = self.scorer.score_player(injured)
        assert s_injured.composite < s_ok.composite
        assert s_injured.recommendation in ("SELL", "WATCH")

    def test_buy_recommendation_threshold(self):
        good = make_player(last_5_avg=14.0, season_points=180, market_value=5_000_000, points=180)
        result = self.scorer.score_player(good)
        assert result.recommendation == "BUY"

    def test_sell_recommendation_threshold(self):
        poor = make_player(last_5_avg=1.0, season_points=20, market_value=20_000_000, points=20)
        result = self.scorer.score_player(poor)
        assert result.recommendation == "SELL"

    def test_rank_players_sorted(self):
        players = [
            make_player(last_5_avg=3.0),
            make_player(last_5_avg=12.0),
            make_player(last_5_avg=7.0),
        ]
        ranked = self.scorer.rank_players(players)
        scores = [s.composite for s in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_by_position(self):
        players = [
            make_player(position="GK"),
            make_player(position="DEF"),
            make_player(position="MID"),
            make_player(position="FWD"),
        ]
        by_pos = self.scorer.rank_by_position(players)
        assert set(by_pos.keys()) == {"GK", "DEF", "MID", "FWD"}


class TestGoalkeeperStrategy:
    def test_score_goalkeeper(self):
        gk = make_player(position="GK", last_5_avg=10.0)
        strategy = GoalkeeperStrategy()
        result = strategy.score_goalkeeper(gk)
        assert 0.0 <= result.gk_composite <= 1.0
        assert result.player.position == "GK"

    def test_raises_for_non_gk(self):
        striker = make_player(position="FWD")
        strategy = GoalkeeperStrategy()
        with pytest.raises(ValueError, match="no es portero"):
            strategy.score_goalkeeper(striker)

    def test_rank_goalkeepers_filters(self):
        players = [
            make_player(position="GK"),
            make_player(position="MID"),  # debe ignorarse
            make_player(position="GK", last_5_avg=12.0),
        ]
        strategy = GoalkeeperStrategy()
        ranked = strategy.rank_goalkeepers(players)
        assert all(s.player.position == "GK" for s in ranked)
        assert len(ranked) == 2
