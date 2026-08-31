"""A 股公司资料标准化层：巨潮主源、东财备用、真实数据部分降级。"""

from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

import astock

_TTL_SECONDS = 24 * 60 * 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


class CompanyProfileUnavailable(RuntimeError):
    """所有真实资料源均不可用，且没有可复用的真实缓存。"""

_EMPTY = {
    "code": "", "shortName": "", "fullName": "", "englishName": "",
    "market": "", "industry": "", "legalRepresentative": "",
    "registeredCapitalWan": None, "establishedDate": "", "listedDate": "",
    "website": "", "email": "", "phone": "", "registeredAddress": "",
    "officeAddress": "", "mainBusiness": "", "businessScope": "",
    "companyHistory": "", "source": "", "fetchedAt": "", "stale": False,
    "partial": True,
}


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _clean(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value).strip()


def _number(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _url(value: Any) -> str:
    text = _clean(value)
    if text and not text.startswith(("http://", "https://")):
        return f"https://{text}"
    return text


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if _clean(value):
            return value
    return ""


def _frame_first(frame: Any) -> dict[str, Any]:
    if frame is None or getattr(frame, "empty", True):
        return {}
    return {str(k): v for k, v in frame.iloc[0].to_dict().items()}


def _load_cninfo(code: str) -> dict[str, Any]:
    ak = astock._akshare()
    return _frame_first(ak.stock_profile_cninfo(symbol=code))


def _load_eastmoney(code: str) -> dict[str, Any]:
    return astock.individual_info(code)


def _load_partial(code: str) -> dict[str, Any]:
    quote = astock.tencent_quote([code]).get(code, {})
    blocks = astock.concept_blocks(code)
    board_names = [str(item.get("name", "")) for item in blocks.get("boards", []) if item.get("name")]
    return {
        "shortName": quote.get("name", ""),
        "industry": board_names[0] if board_names else "",
    }


def _market_for(code: str) -> str:
    if code.startswith("6"):
        return "上海证券交易所"
    if code.startswith(("4", "8")):
        return "北京证券交易所"
    return "深圳证券交易所"


def _normalize_cninfo(code: str, row: dict[str, Any]) -> dict[str, Any]:
    data = dict(_EMPTY)
    data.update({
        "code": code,
        "shortName": _clean(_first(row, "A股简称", "证券简称", "公司简称")),
        "fullName": _clean(_first(row, "公司名称", "公司全称")),
        "englishName": _clean(_first(row, "英文名称", "英文全称")),
        "market": _clean(_first(row, "所属市场", "上市市场")) or _market_for(code),
        "industry": _clean(_first(row, "所属行业", "行业")),
        "legalRepresentative": _clean(_first(row, "法人代表", "法定代表人")),
        "registeredCapitalWan": _number(_first(row, "注册资金", "注册资本")),
        "establishedDate": _clean(_first(row, "成立日期", "成立时间")),
        "listedDate": _clean(_first(row, "上市日期", "上市时间")),
        "website": _url(_first(row, "官方网站", "公司网址", "网址")),
        "email": _clean(_first(row, "电子邮箱", "邮箱")),
        "phone": _clean(_first(row, "联系电话", "电话")),
        "registeredAddress": _clean(_first(row, "注册地址")),
        "officeAddress": _clean(_first(row, "办公地址")),
        "mainBusiness": _clean(_first(row, "主营业务")),
        "businessScope": _clean(_first(row, "经营范围")),
        "companyHistory": _clean(_first(row, "机构简介", "公司简介", "公司沿革")),
        "source": "巨潮资讯",
        "partial": False,
    })
    return data


def _normalize_eastmoney(code: str, row: dict[str, Any]) -> dict[str, Any]:
    data = dict(_EMPTY)
    data.update({
        "code": code,
        "shortName": _clean(_first(row, "股票简称", "证券简称")),
        "fullName": _clean(_first(row, "公司名称", "公司全称")),
        "market": _market_for(code),
        "industry": _clean(_first(row, "行业", "所属行业")),
        "listedDate": _clean(_first(row, "上市时间", "上市日期")),
        "source": "东方财富",
        "partial": True,
    })
    return data


def get_company_profile(code: str) -> dict[str, Any]:
    now = time.time()
    with _lock:
        cached = _cache.get(code)
    if cached and now - cached[0] < _TTL_SECONDS:
        return dict(cached[1])

    try:
        primary = _load_cninfo(code)
    except Exception:
        primary = {}
    if primary:
        result = _normalize_cninfo(code, primary)
    else:
        try:
            backup = _load_eastmoney(code)
        except Exception:
            backup = {}
        if backup:
            result = _normalize_eastmoney(code, backup)
        else:
            try:
                partial = _load_partial(code)
            except Exception:
                partial = {}
            if not any(_clean(partial.get(key)) for key in ("shortName", "industry")):
                if cached:
                    stale = dict(cached[1])
                    stale["stale"] = True
                    return stale
                raise CompanyProfileUnavailable("公司资料源暂不可用")
            result = dict(_EMPTY)
            result.update({
                "code": code,
                "shortName": _clean(partial.get("shortName")),
                "industry": _clean(partial.get("industry")),
                "market": _market_for(code),
                "source": "腾讯行情/东方财富板块",
                "partial": True,
            })

    result["fetchedAt"] = datetime.now(timezone.utc).isoformat()
    result["stale"] = False
    with _lock:
        _cache[code] = (now, dict(result))
    return result
