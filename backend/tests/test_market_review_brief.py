from datetime import datetime

import market_review
from market_review_brief import PROMPT_VERSION, MarketReviewBriefService, brief_ready, build_brief_prompt
from market_review_scheduler import PostCloseReviewScheduler


def complete_snapshot():
    return {
        "tradingDate": "2026-09-02",
        "generatedAt": "2026-09-02T16:00:00+08:00",
        "indices": [
            {"code": "000001", "name": "上证指数", "price": 3900, "changePct": 0.2},
            {"code": "399001", "name": "深证成指", "price": 12000, "changePct": -0.1},
            {"code": "399006", "name": "创业板指", "price": 2500, "changePct": 0.4},
        ],
        "breadth": {"up": 1200, "down": 800, "limitUp": 55, "limitDown": 9},
        "liquidity": {"todayAmountYuan": 1_000_000_000_000, "previousAmountYuan": 900_000_000_000, "changePct": 11.11},
        "sectors": [{"name": "电子", "net": 2.3}, {"name": "银行", "net": -1.1}],
    }


def test_brief_ready_requires_three_indices_breadth_and_liquidity():
    assert brief_ready(complete_snapshot()) is True
    incomplete = complete_snapshot()
    incomplete["indices"] = incomplete["indices"][:2]
    assert brief_ready(incomplete) is False


def test_prompt_separates_objective_interpretation_and_verification_topics():
    prompt = build_brief_prompt(complete_snapshot())
    for marker in ["客观数据", "指数表现", "市场宽度", "成交额", "板块资金", "数据缺口", "验证条件", "不构成投资建议"]:
        assert marker in prompt


def test_generated_brief_is_hard_limited_and_idempotent(tmp_path):
    calls = []
    service = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: calls.append(prompt) or "指数表现与分化" * 100)

    first = service.generate(complete_snapshot())
    second = service.generate(complete_snapshot())

    assert first["status"] == "generated"
    assert len(first["text"]) <= 200
    assert second == first
    assert len(calls) == 1
    assert first["promptVersion"] == PROMPT_VERSION


def test_missing_data_skips_llm(tmp_path):
    calls = []
    service = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: calls.append(prompt) or "不会调用")
    snapshot = complete_snapshot()
    snapshot["liquidity"] = {"todayAmountYuan": None, "previousAmountYuan": None}

    result = service.generate(snapshot)

    assert result["status"] == "missing"
    assert calls == []


def test_failed_new_attempt_preserves_prior_success(tmp_path):
    service = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: "首次成功")
    first = service.generate(complete_snapshot())
    changed = complete_snapshot()
    changed["breadth"] = {**changed["breadth"], "up": 1300}
    failing = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: (_ for _ in ()).throw(RuntimeError("glm offline")))

    result = failing.generate(changed)

    assert first["status"] == "generated"
    assert result["status"] == "generated"
    assert result["text"] == "首次成功"
    assert result["lastAttemptStatus"] == "unavailable"


def test_scheduler_skips_before_close_and_non_trading_day(tmp_path):
    service = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: "简述")
    snapshot = complete_snapshot()
    scheduler = PostCloseReviewScheduler(
        snapshot_service=type("Snapshot", (), {"get_review": lambda self, force=False: snapshot})(),
        brief_service=service,
        now_fn=lambda: datetime(2026, 9, 2, 15, 29, tzinfo=market_review.BEIJING),
    )
    assert scheduler.run_once()["status"] == "before_close"

    weekend = PostCloseReviewScheduler(
        snapshot_service=type("Snapshot", (), {"get_review": lambda self, force=False: snapshot})(),
        brief_service=service,
        now_fn=lambda: datetime(2026, 9, 5, 16, 0, tzinfo=market_review.BEIJING),
    )
    assert weekend.run_once()["status"] == "non_trading_day"


def test_scheduler_runs_after_close_and_is_safe_to_repeat(tmp_path):
    calls = []
    brief = MarketReviewBriefService(tmp_path, llm_call=lambda prompt: calls.append(prompt) or "盘后简述")
    snapshot_service = type("Snapshot", (), {"get_review": lambda self, force=False: complete_snapshot()})()
    scheduler = PostCloseReviewScheduler(
        snapshot_service=snapshot_service,
        brief_service=brief,
        now_fn=lambda: datetime(2026, 9, 2, 15, 30, tzinfo=market_review.BEIJING),
    )

    first = scheduler.run_once()
    second = scheduler.run_once()

    assert first["status"] == "generated"
    assert second["status"] == "generated"
    assert len(calls) == 1
