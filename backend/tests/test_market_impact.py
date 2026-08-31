from datetime import datetime, timedelta, timezone

from market_impact import MarketImpactEnricher, a_share_impact_score, main_board_eligible


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def _event(**overrides):
    event = {
        "id": "event-1",
        "title": "AI 长剧带动内容板块关注 300413",
        "summary": "上市公司披露相关进展",
        "publishedAt": "2026-08-31T07:55:00+00:00",
        "latestAt": "2026-08-31T07:55:00+00:00",
        "category": "公司",
        "sourceTier": 35,
        "sourceLevel": "S",
        "relatedStocks": ["300413"],
        "relatedSourceCount": 2,
        "relatedSources": ["上市公司公告", "财联社电报"],
    }
    event.update(overrides)
    return event


def test_impact_score_has_exact_five_weighted_components():
    event = _event(
        marketEvidence={
            "stocks": [{"code": "300413", "pct": 10.0}, {"code": "000001", "pct": 6.0}],
            "sectors": [{"name": "影视传媒", "pct": 4.0}, {"name": "文化传媒", "pct": 3.0}],
            "reverseChecks": {"300413": {"news": ["匹配"], "announcements": ["公告"], "investorQa": ["问答"]}},
        },
        transmissionPath={"verified": True},
    )

    score, breakdown, reasons = a_share_impact_score(event, now=NOW)

    assert score == 100
    assert breakdown == {
        "marketReaction": 30,
        "sectorSpread": 25,
        "causalRelation": 20,
        "authority": 15,
        "timeliness": 10,
    }
    assert any("本站计算" in reason for reason in reasons)


def test_market_reverse_check_builds_verified_transmission_path_and_main_board():
    class Provider:
        def observe(self):
            return {
                "observedAt": NOW.isoformat(),
                "stocks": [{"code": "300413", "name": "芒果超媒", "pct": 9.8}],
                "sectors": [{"name": "影视传媒", "pct": 4.6, "breadth": 18}],
                "reverseChecks": {"300413": {
                    "news": [{"title": "AI 长剧业务进展"}],
                    "announcements": [{"title": "公司公告"}],
                    "investorQa": [{"question": "长剧业务"}],
                    "boards": [{"name": "影视传媒"}],
                }},
            }

    result = MarketImpactEnricher(Provider(), now_fn=lambda: NOW).enrich_event(_event())

    assert result["mainBoardEligible"] is True
    assert result["confidence"] == "high"
    assert result["transmissionPath"]["catalyst"] == "AI 长剧带动内容板块关注 300413"
    assert result["transmissionPath"]["aShareSectors"] == ["影视传媒"]
    assert result["transmissionPath"]["relatedStocks"] == ["300413"]
    assert "marketReaction" in result["impactBreakdown"]
    assert result["recheckDueAt"]["15m"] == (NOW + timedelta(minutes=15)).isoformat()


def test_overseas_event_without_a_share_evidence_is_global_observation_only():
    event = _event(
        title="英伟达财报超预期",
        summary="海外公司发布财报",
        category="海外",
        sourceTier=35,
        relatedStocks=[],
        relatedSourceCount=1,
        marketEvidence={"stocks": [], "sectors": [], "reverseChecks": {}},
    )

    score, _, _ = a_share_impact_score(event, now=NOW)
    assert score < 45
    assert main_board_eligible({**event, "aShareImpactScore": score, "confidence": "low"}) is False


def test_single_rumor_without_verified_market_evidence_cannot_enter_main_board():
    event = _event(
        sourceTier=8,
        sourceLevel="传闻",
        relatedSourceCount=1,
        relatedSources=["匿名社交媒体"],
        relatedStocks=[],
        marketEvidence={"stocks": [], "sectors": [], "reverseChecks": {}},
    )
    score, _, _ = a_share_impact_score(event, now=NOW)

    assert score < 45
    assert main_board_eligible({**event, "aShareImpactScore": score, "confidence": "low"}) is False


def test_enricher_is_safe_when_market_provider_fails():
    class BrokenProvider:
        def observe(self):
            raise RuntimeError("upstream unavailable")

    result = MarketImpactEnricher(BrokenProvider(), now_fn=lambda: NOW).enrich_event(_event())

    assert result["marketEvidence"]["status"] == "unavailable"
    assert result["mainBoardEligible"] is False
    assert result["confidence"] == "low"
