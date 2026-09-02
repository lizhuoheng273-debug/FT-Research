"""Deterministic, bounded post-close brief generation for market review snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import chat
import glm_config
from market_review import BEIJING, PROMPT_VERSION, REVIEW_CACHE_DIR, REVIEW_FILE_LOCK, snapshot_hash


def _now(value: datetime) -> datetime:
    return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)


def brief_ready(snapshot: dict[str, Any]) -> bool:
    breadth = snapshot.get("breadth") or {}
    liquidity = snapshot.get("liquidity") or {}
    return (
        len(snapshot.get("indices") or []) >= 3
        and breadth.get("up") is not None
        and breadth.get("down") is not None
        and liquidity.get("todayAmountYuan") is not None
        and liquidity.get("previousAmountYuan") is not None
    )


def build_brief_context(snapshot: dict[str, Any]) -> str:
    objective = {
        "交易日": snapshot.get("tradingDate"),
        "指数": [{"名称": row.get("name"), "价格": row.get("price"), "涨跌幅": row.get("changePct")} for row in (snapshot.get("indices") or [])[:4]],
        "市场宽度": {key: (snapshot.get("breadth") or {}).get(key) for key in ("up", "down", "upRatio", "downRatio")},
        "成交额": snapshot.get("liquidity"),
        "板块资金": [{"名称": row.get("name"), "净流入亿元": row.get("net"), "涨跌幅": row.get("pct")} for row in ((snapshot.get("sectors") or [])[:5] + (snapshot.get("sectors") or [])[-5:])],
        "短线情绪": snapshot.get("shortTermEmotion"),
        "成交额前五": (snapshot.get("turnoverTop") or [])[:5],
    }
    gaps = []
    for name in ("indices", "breadth", "liquidity", "shortTermEmotion", "turnoverTop", "sectors"):
        if not snapshot.get(name):
            gaps.append(name)
    return (
        "你是金融市场复盘助手，只能解释下面的客观数据，不得补造行情、原因、个股或预测。\n"
        "【客观数据】\n" + json.dumps(objective, ensure_ascii=False) + "\n"
        "【解释约束】围绕指数表现与分化、市场宽度、成交额变化、板块资金轮动；明确区分事实和推断。"
        "不要给买卖建议，不构成投资建议。\n"
        "【验证条件】只在有必要时用一句白话说明后续观察点，避免生硬罗列框架词。\n"
        f"【数据缺口】{', '.join(gaps) or '无'}\n"
    )


def build_brief_prompt(snapshot: dict[str, Any]) -> str:
    # Keep data and framework keywords out of the question: scope routing must
    # not mistake a market-wide snapshot containing stock names for stock research.
    return ("请按市场复盘框架复盘今天的行情，写成面向普通读者的盘后简述。"
            "正文不超过400字，建议250至380字，分2至3个短段落。先用一句话概括，再结合上下文的关键数据解释。"
            "缺失的信息不要猜测或凑齐；不输出标题、字数统计、模板说明或括号中的自我评价。"
            "语言直接自然，不用‘避险特征属推断’一类生硬措辞，推测用‘可能’表达。以完整句子结束。")


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"```|[*_#]", "", text)
    text = re.sub(r"[（(]\s*(?:约|共|全文|字数)?\s*\d+\s*(?:字|个字符)\s*[）)]", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= 400:
        return text
    prefix = text[:400]
    endings = list(re.finditer(r"[。！？!?](?:[”’」])?", prefix))
    return prefix[:endings[-1].end()].strip() if endings else prefix[:399].rstrip("，、；： ") + "。"


class MarketReviewBriefService:
    def __init__(self, cache_dir: Path | None = None, now_fn: Callable[[], datetime] | None = None,
                 llm_call: Callable[[str], Any] | None = None,
                 config_loader: Callable[[], dict[str, str]] | None = None):
        self.cache_dir = Path(cache_dir or REVIEW_CACHE_DIR)
        self.now_fn = now_fn or (lambda: datetime.now(BEIJING))
        self.llm_call = llm_call
        self.config_loader = config_loader or glm_config.load_glm_config

    def _path(self, trading_date: str) -> Path:
        return self.cache_dir / f"{trading_date}.json"

    def _read(self, trading_date: str) -> dict[str, Any]:
        try:
            value = json.loads(self._path(trading_date).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, trading_date: str, snapshot: dict[str, Any], brief: dict[str, Any]) -> None:
        with REVIEW_FILE_LOCK:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            existing = self._read(trading_date)
            latest = existing.get("review") or {}
            base = latest if (latest.get("generatedAt") or "") > (snapshot.get("generatedAt") or "") else snapshot
            review = {**base, "brief": brief}
            payload = {"savedAt": brief.get("lastAttemptAt") or brief.get("generatedAt"), "review": review}
            temp = self._path(trading_date).with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self._path(trading_date))

    def generate(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        trading_date = str(snapshot.get("tradingDate") or _now(self.now_fn()).date().isoformat())
        current_hash = snapshot_hash(snapshot)
        existing = self._read(trading_date)
        previous = existing.get("brief") or (existing.get("review") or {}).get("brief") or {}
        if previous.get("snapshotHash") == current_hash and previous.get("promptVersion") == PROMPT_VERSION:
            return previous
        attempted_at = _now(self.now_fn()).isoformat(timespec="seconds")
        if not brief_ready(snapshot):
            result = {"text": "", "status": "missing", "generatedAt": None, "lastAttemptAt": attempted_at,
                      "snapshotHash": current_hash, "promptVersion": PROMPT_VERSION}
            self._write(trading_date, snapshot, result)
            return result

        prompt = build_brief_prompt(snapshot)
        try:
            if self.llm_call is not None:
                raw = self.llm_call(prompt + "\n" + build_brief_context(snapshot))
            else:
                cfg = self.config_loader()
                if not cfg.get("apiKey"):
                    raise RuntimeError("GLM 未配置")
                raw = chat.run_chat(cfg, [{"role": "user", "content": prompt}], context=build_brief_context(snapshot), analysis_scope="market").get("content", "")
            text = _clean_text(raw)
            if not text:
                raise RuntimeError("模型未返回简述")
            result = {"text": text, "status": "generated", "generatedAt": attempted_at, "lastAttemptAt": attempted_at,
                      "snapshotHash": current_hash, "promptVersion": PROMPT_VERSION}
        except Exception as exc:  # noqa: BLE001 — model outage must not erase objective review
            if previous.get("status") == "generated" and previous.get("text"):
                result = {**previous, "lastAttemptAt": attempted_at, "lastAttemptStatus": "unavailable",
                          "lastError": str(exc)[:160], "snapshotHash": current_hash, "promptVersion": PROMPT_VERSION}
            else:
                result = {"text": "", "status": "unavailable", "generatedAt": None, "lastAttemptAt": attempted_at,
                          "lastAttemptStatus": "unavailable", "lastError": str(exc)[:160],
                          "snapshotHash": current_hash, "promptVersion": PROMPT_VERSION}
        self._write(trading_date, snapshot, result)
        return result
