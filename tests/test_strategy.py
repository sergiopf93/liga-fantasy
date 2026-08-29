"""Tests para los módulos de estrategia de mercado, cláusulas y portfolio."""
from __future__ import annotations

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from backend.laliga.models import (
    Player, PlayerStats, Market, MarketPlayer,
    Team, TeamPlayer, League,
)
from backend.strategy.market_strategy import MarketStrategy, MarketOpportunity
from backend.strategy.clause_risk import ClauseRisk
from backend.strategy.portfolio import Portfolio


# ============================================================
# Helpers
# ============================================================

def _player(
    pid="p1", name="Jugador", pos="MID",
    market_value=10_000_000, clause=12_000_000,
    points=100, status="ok", last_5_avg=8.0,
) -> Player:
    return Player(
        id=pid, name=name, team="FC Test", position=pos,
        market_value=market_value, clause_value=clause,
        points=points, status=status,
        stats=PlayerStats(
            season_points=points, last_5_avg=last_5_avg,
            total_matches=20, last_match_points=10,
        ),
    )


def _market_player(player, sell_price=None, time_left=7200) -> MarketPlayer:
    price = sell_price if sell_price is not None else int(player.market_value * 0.90)
    return MarketPlayer(player=player, sell_price=price, time_left=time_left, seller_name="Rival")


def _team_player(player, buy_price=None) -> TeamPlayer:
    return TeamPlayer(
        player=player,
        buy_price=buy_price or player.market_value,
        in_lineup=True,
    )


def _team(players, budget=20_000_000) -> Team:
    return Team(id="t1", name="Mi Equipo", budget=budget, players=players)


def _rival(budget=5_000_000) -> Team:
    return Team(id="r1", name="Rival FC", budget=budget, players=[])


# ============================================================
# MarketStrategy
# ============================================================

class TestMarketStrategy:
    def test_finds_bargain(self):
        # Precio 80% del valor → debería ser oportunidad
        player = _player(market_value=10_000_000)
        mp = _market_player(player, sell_price=8_000_000)
        market = Market(players=[mp])
        strategy = MarketStrategy()
        opps = strategy.find_opportunities(market)
        assert len(opps) > 0
        assert opps[0].market_player.player.id == player.id

    def test_skips_own_players(self):
        player = _player(pid="p-mine")
        mp = _market_player(player, sell_price=7_000_000)
        market = Market(players=[mp])
        my_team = _team([_team_player(player)])
        strategy = MarketStrategy()
        opps = strategy.find_opportunities(market, my_team=my_team)
        assert not any(o.market_player.player.id == "p-mine" for o in opps)

    def test_respects_budget(self):
        expensive = _player(market_value=30_000_000)
        mp = _market_player(expensive, sell_price=25_000_000)
        market = Market(players=[mp])
        strategy = MarketStrategy(budget=10_000_000)
        opps = strategy.find_opportunities(market)
        assert len(opps) == 0

    def test_urgency_high_for_bargain_good_player(self):
        player = _player(market_value=10_000_000, last_5_avg=13.0, points=170)
        mp = _market_player(player, sell_price=7_500_000)  # 75% → bargain
        market = Market(players=[mp])
        strategy = MarketStrategy()
        opps = strategy.find_opportunities(market)
        assert opps[0].urgency == "HIGH"

    def test_suggests_sales_for_poor_players(self):
        bad_player = _player(last_5_avg=1.0, points=15, market_value=15_000_000)
        my_team = _team([_team_player(bad_player, buy_price=14_000_000)])
        mp = _market_player(bad_player, sell_price=16_000_000)
        market = Market(players=[mp])
        strategy = MarketStrategy()
        suggestions = strategy.suggest_sales(my_team, market)
        assert len(suggestions) > 0
        assert suggestions[0]["player"].id == bad_player.id


# ============================================================
# ClauseRisk
# ============================================================

class TestClauseRisk:
    def test_low_risk_no_rivals_afford(self):
        player = _player(clause=50_000_000)
        tp = _team_player(player)
        league = League(
            id="l1", name="Test",
            my_team=_team([tp]),
            rival_teams=[_rival(budget=5_000_000)],
        )
        result = ClauseRisk().assess_player(tp, league)
        assert result.risk_level == "LOW"
        assert result.rivals_can_afford == 0

    def test_critical_risk_many_rivals_afford(self):
        player = _player(clause=5_000_000)
        tp = _team_player(player)
        rivals = [_rival(budget=10_000_000) for _ in range(4)]
        league = League(id="l1", name="Test", my_team=_team([tp]), rival_teams=rivals)
        result = ClauseRisk().assess_player(tp, league)
        assert result.risk_level == "CRITICAL"
        assert result.rivals_can_afford >= 3

    def test_assess_team_sorted(self):
        cheap = _player(pid="cheap", clause=1_000_000)
        pricey = _player(pid="pricey", clause=100_000_000)
        rivals = [_rival(budget=50_000_000) for _ in range(3)]
        my_team = _team([_team_player(cheap), _team_player(pricey)])
        league = League(id="l1", name="Test", my_team=my_team, rival_teams=rivals)
        results = ClauseRisk().assess_team(league)
        # El más barato debería aparecer primero (más crítico)
        assert results[0].player.id == "cheap"


# ============================================================
# Portfolio
# ============================================================

class TestPortfolio:
    def _full_team(self):
        players = [
            _player(pid=f"gk{i}",  pos="GK",  last_5_avg=9.0,  market_value=5_000_000)  for i in range(1)
        ] + [
            _player(pid=f"def{i}", pos="DEF", last_5_avg=7.0,  market_value=8_000_000)  for i in range(4)
        ] + [
            _player(pid=f"mid{i}", pos="MID", last_5_avg=10.0, market_value=12_000_000) for i in range(4)
        ] + [
            _player(pid=f"fwd{i}", pos="FWD", last_5_avg=12.0, market_value=15_000_000) for i in range(3)
        ]
        return _team([_team_player(p) for p in players], budget=15_000_000)

    def test_analyze_returns_report(self):
        portfolio = Portfolio()
        report = portfolio.analyze(self._full_team())
        assert report.avg_score > 0
        assert report.total_value > 0
        assert isinstance(report.positional_balance, dict)

    def test_empty_team(self):
        portfolio = Portfolio()
        report = portfolio.analyze(_team([]))
        assert report.total_value == 0
        assert "vacío" in report.summary

    def test_identifies_weak_players(self):
        weak = _player(pid="weak", last_5_avg=0.5, points=5, market_value=20_000_000)
        strong = _player(pid="strong", last_5_avg=14.0, points=180, market_value=5_000_000)
        team = _team([_team_player(weak), _team_player(strong)])
        portfolio = Portfolio()
        report = portfolio.analyze(team)
        sell_ids = [tp.player.id for tp, _ in report.sell_candidates]
        assert "weak" in sell_ids
