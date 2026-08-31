"""Evidence-first A-share impact scoring and reverse lookup orchestration."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

UTC = timezone.utc


class MarketEvidenceProvider(Protocol):
    def observe(self, event: dict[str, Any] | None = None) -> dict[str, Any]: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def _age_minutes(value: Any, now: datetime) -> float:
    parsed = _parse(value)
    if not parsed:
        return 10_000
    return max(0.0, (now.astimezone(UTC) - parsed).total_seconds() / 60)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def a_share_impact_score(event: dict[str, Any], *, now: datetime | None = None) -> tuple[int, dict[str, int], list[str]]:
    """Return the fixed 100-point score, its five components, and reasons."""
    current = now or _now()
    evidence = event.get("marketEvidence") if isinstance(event.get("marketEvidence"), dict) else {}
    stocks = [row for row in _list(evidence.get("stocks")) if isinstance(row, dict) and str(row.get("code") or "")]
    sectors = [row for row in _list(evidence.get("sectors")) if isinstance(row, dict) and str(row.get("name") or "")]
    reverse = evidence.get("reverseChecks") if isinstance(evidence.get("reverseChecks"), dict) else {}
    explicit_stocks = [str(code) for code in _list(event.get("relatedStocks")) if str(code)]
    verified_reverse = sum(1 for value in reverse.values() if isinstance(value, dict) and any(_list(value.get(key)) for key in ("news", "announcements", "investorQa", "boards")))

    reaction_strength = sum(min(10.0, abs(_number(row.get("pct")))) for row in stocks)
    market_reaction = min(30, round(len(stocks) * 8 + min(14, reaction_strength))) if stocks else 0
    breadth = sum(1 for row in sectors if _number(row.get("breadth")) > 0)
    spread_bonus = min(5, max(max(0, len(stocks) - 1) * 5, breadth * 2))
    sector_spread = min(25, len(sectors) * 10 + spread_bonus) if sectors else 0
    causal_relation = min(20, (8 if explicit_stocks else 0) + (8 if verified_reverse else 0) + (4 if event.get("transmissionPath", {}).get("verified") else 0))
    authority = min(15, round(max(0, min(35, _number(event.get("sourceTier")))) * 15 / 35))
    age = _age_minutes(event.get("latestAt") or event.get("publishedAt"), current)
    timeliness = 10 if age <= 10 else 8 if age <= 60 else 6 if age <= 360 else 3 if age <= 1440 else 0
    breakdown = {
        "marketReaction": market_reaction,
        "sectorSpread": sector_spread,
        "causalRelation": causal_relation,
        "authority": authority,
        "timeliness": timeliness,
    }
    reasons = [
        f"实际市场反应 {market_reaction}/30（{len(stocks)} 只已观测股票）",
        f"板块扩散 {sector_spread}/25（{len(sectors)} 个已观测板块）",
        f"因果关系 {causal_relation}/20（{verified_reverse} 个个股反查）",
        f"权威来源 {authority}/15",
        f"时效/持续发酵 {timeliness}/10",
        "本站计算，不代表投资建议",
    ]
    return min(100, sum(breakdown.values())), breakdown, reasons


def main_board_eligible(event: dict[str, Any]) -> bool:
    score = int(event.get("aShareImpactScore") or 0)
    if score < 60 or event.get("confidence") == "low":
        return False
    evidence = event.get("marketEvidence") if isinstance(event.get("marketEvidence"), dict) else {}
    if evidence.get("status") == "unavailable":
        return False
    if str(event.get("category") or "") == "海外" and event.get("confidence") != "high":
        return False
    return bool(_list(evidence.get("stocks")) or _list(evidence.get("sectors")))


class _UnavailableProvider:
    def observe(self, event: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"status": "unavailable", "stocks": [], "sectors": [], "reverseChecks": {}, "error": "no provider configured"}


class DefaultMarketEvidenceProvider:
    """Adapter around existing public market/stock functions.

    Imports are lazy and every upstream call is independently guarded, so the
    news scheduler can continue when AkShare or one public endpoint is absent.
    """

    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def observe(self, event: dict[str, Any] | None = None) -> dict[str, Any]:
        import astock
        import market

        codes = [str(code) for code in _list((event or {}).get("relatedStocks")) if str(code).isdigit() and len(str(code)) == 6][:5]
        cache_key = ",".join(sorted(codes)) or "market"
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1]
        result: dict[str, Any] = {"stocks": [], "sectors": [], "reverseChecks": {}, "status": "ok"}
        try:
            overview = market.get_overview() or {}
            result["sectors"].extend(overview.get("sectors") or [])
        except Exception as exc:
            result["marketError"] = str(exc)[:160]
        try:
            industry = astock.industry_comparison(top_n=10) or {}
            result["sectors"].extend(industry.get("top") or [])
            result["sectors"].extend(industry.get("bottom") or [])
        except Exception as exc:
            result["industryError"] = str(exc)[:160]
        if codes:
            try:
                quotes = astock.tencent_quote(codes) or {}
                result["stocks"].extend({"code": code, **(quotes.get(code) or {})} for code in codes if isinstance(quotes.get(code), dict))
            except Exception as exc:
                result["quoteError"] = str(exc)[:160]
            for code in codes:
                check: dict[str, Any] = {}
                for key, fetch in (("news", lambda: astock.stock_news(code, limit=5)), ("announcements", lambda: astock.announcements(code, limit=5)), ("investorQa", lambda: astock.investor_qa(code, page_size=5)), ("boards", lambda: (astock.concept_blocks(code) or {}).get("boards", []))):
                    try:
                        check[key] = fetch() or []
                    except Exception:
                        check[key] = []
                result["reverseChecks"][code] = check
        result["observedAt"] = _now().isoformat()
        self._cache[cache_key] = (time.monotonic(), result)
        return result


def build_default_provider() -> MarketEvidenceProvider:
    return DefaultMarketEvidenceProvider()


class MarketImpactEnricher:
    def __init__(self, provider: MarketEvidenceProvider | None = None, *, now_fn: Callable[[], datetime] = _now):
        self.provider = provider or _UnavailableProvider()
        self.now_fn = now_fn

    def _observe(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.provider.observe(event)
        except TypeError:
            # Keep simple test/custom providers that expose observe() only.
            try:
                return self.provider.observe()  # type: ignore[call-arg]
            except Exception as exc:
                return {"status": "unavailable", "stocks": [], "sectors": [], "reverseChecks": {}, "error": str(exc)[:160]}
        except Exception as exc:
            return {"status": "unavailable", "stocks": [], "sectors": [], "reverseChecks": {}, "error": str(exc)[:160]}

    def enrich_event(self, event: dict[str, Any]) -> dict[str, Any]:
        result = dict(event)
        evidence = self._observe(event)
        result["marketEvidence"] = evidence
        sector_names = sorted({str(row.get("name")) for row in _list(evidence.get("sectors")) if isinstance(row, dict) and row.get("name")})
        verified_stocks = sorted({str(row.get("code")) for row in _list(evidence.get("stocks")) if isinstance(row, dict) and row.get("code")})
        stocks = sorted(set(str(code) for code in _list(event.get("relatedStocks")) if str(code)) | set(verified_stocks))
        reverse = evidence.get("reverseChecks") if isinstance(evidence.get("reverseChecks"), dict) else {}
        reverse_count = sum(1 for code in stocks if code in reverse and isinstance(reverse[code], dict) and any(_list(reverse[code].get(key)) for key in ("news", "announcements", "investorQa", "boards")))
        transmission = {
            "catalyst": str(event.get("title") or ""),
            "industry": str(event.get("track") or event.get("category") or ""),
            "aShareSectors": sector_names,
            "relatedStocks": stocks,
            "marketEvidence": ["批量行情" if verified_stocks else "", "板块观察" if sector_names else "", f"个股反查 {reverse_count} 条" if reverse_count else ""],
            "verified": bool(stocks and (sector_names or reverse_count)),
        }
        result["relatedStocks"] = stocks
        result["transmissionPath"] = transmission
        result["marketEvidence"] = {**evidence, "verifiedStocks": verified_stocks, "verifiedSectors": sector_names}
        score, breakdown, reasons = a_share_impact_score(result, now=self.now_fn())
        result["aShareImpactScore"] = score
        result["impactBreakdown"] = breakdown
        result["impactReasons"] = reasons
        result["confidence"] = "low" if evidence.get("status") == "unavailable" else "high" if transmission["verified"] and score >= 60 and result["sourceTier"] >= 28 else "medium" if transmission["verified"] or result["sourceTier"] >= 28 else "low"
        result["mainBoardEligible"] = main_board_eligible(result)
        result["candidate"] = not result["mainBoardEligible"] and score >= 45
        result["globalObservation"] = str(result.get("category") or "") == "海外" and not result["mainBoardEligible"]
        base = self.now_fn().astimezone(UTC)
        result["recheckDueAt"] = {name: (base + timedelta(minutes=minutes)).isoformat() for name, minutes in (("immediate", 0), ("15m", 15), ("45m", 45), ("90m", 90))}
        return result
