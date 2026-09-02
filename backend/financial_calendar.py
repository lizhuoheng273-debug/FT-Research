"""Official upcoming financial events. Cache-only reads; never infer future dates."""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BEIJING = ZoneInfo("Asia/Shanghai")
FED_HOME = "https://www.federalreserve.gov/newsevents/calendar.htm"
NVIDIA_FEED = "https://investor.nvidia.com/rss/Event.aspx?LanguageId=1"
BEA_URL = "https://www.bea.gov/news/schedule"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
SOURCES = {"fed": ("美联储", FED_HOME), "ecb": ("欧洲央行", ECB_URL), "bea": ("美国经济分析局", BEA_URL),
           "nvidia": ("英伟达投资者关系", NVIDIA_FEED), "bls": ("美国劳工统计局", BLS_URL)}
REFRESH_SECONDS = 3600


def safe_url(value):
    parsed = urlparse(str(value or ""))
    return str(value) if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def calendar_event(key, title, kind, day, clock, zone, url):
    """A date without a time stays a local date, never a fabricated UTC midnight."""
    day = date.fromisoformat(day).isoformat()
    starts = None
    if clock:
        starts = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ZoneInfo(zone)).astimezone(BEIJING).isoformat()
    return {"id": hashlib.sha256(key.encode()).hexdigest()[:20], "title": title.strip(), "category": kind,
            "date": starts[:10] if starts else day, "startsAt": starts, "precision": "time" if starts else "date",
            "sourceTimezone": zone, "originalUrl": safe_url(url), "status": "scheduled", "stale": False}


def _clock(text):
    cleaned = text.replace(".", "").strip().upper()
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%H:%M:%S")
        except ValueError:
            pass
    return None


def parse_fed(html, year, month, url):
    soup = BeautifulSoup(html, "html.parser")
    if not soup.select_one(".cal-nojs, #article .row-title"):
        raise ValueError("美联储日历结构无法识别")
    output = []
    for row in soup.select(".panel-body > .row"):
        title_cell, days, time_cell = row.select_one(".col-xs-7"), row.select_one(".col-xs-3"), row.select_one(".col-xs-2")
        if not title_cell or not days:
            continue
        first = title_cell.find("p")
        original = (first or title_cell).get_text(" ", strip=True)
        topic = title_cell.select_one(".calendar__title")
        detail = topic.get_text(" ", strip=True) if topic else ""
        if not re.search(r"Speech|FOMC|Beige Book|G\.17|G\.19|Z\.1", original, re.I):
            continue
        title, kind = original, "经济数据"
        if "Speech" in original:
            # Only economically relevant speeches, not every public engagement.
            if not re.search(r"outlook|econom|monetary|inflation|financial|policy", detail + original, re.I):
                continue
            title = original.replace("Speech - ", "美联储").replace("Governor ", "理事 ").replace("Chair ", "主席 ") + " 讲话"
            if detail:
                title += "：" + detail.replace("Economic Outlook", "经济展望")
            kind = "央行讲话"
        elif "FOMC" in original:
            if "Minutes" in original:
                title, kind = "美联储 FOMC 会议纪要", "央行纪要"
            elif "Press Conference" in original:
                title, kind = "美联储议息新闻发布会", "央行决议"
            elif original.strip() in {"FOMC Meeting", "FOMC Statement", "FOMC Decision"}:
                title, kind = "美联储利率决议", "央行决议"
            else:
                title, kind = original, "央行日程"
            meeting = re.search(r"Two-day meeting,\s*\w+\s+(\d+)\s*[-–]\s*(\d+)", title_cell.get_text(" ", strip=True))
            if meeting:
                day = date(year, month, int(meeting.group(1))).isoformat()
                output.append(calendar_event(f"fed-meeting:{day}", "美联储 FOMC 议息会议（两日）", "重大会议", day, None, "America/New_York", url))
        else:
            title = {"Beige Book": "美联储经济褐皮书", "G.17 - Industrial Production and Capacity Utilization": "美国工业生产与产能利用率",
                     "G.19 - Consumer Credit": "美国消费者信贷", "Z.1 - Financial Accounts of the United States": "美国金融账户数据"}.get(original, original)
        for number in re.findall(r"\d+", days.get_text()):
            day = date(year, month, int(number)).isoformat()
            output.append(calendar_event(f"fed:{original}:{day}", title, kind, day, _clock(time_cell.get_text(" ", strip=True)) if time_cell else None, "America/New_York", url))
    return output


def parse_nvidia(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("英伟达活动订阅格式异常") from exc
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("英伟达活动订阅格式异常")
    rows = []
    for node in root.findall("./channel/item"):
        original = node.findtext("title") or ""
        match = re.match(r"(\d{1,2}/\d{1,2}/\d{4})\s*:\s*(.+)", original)
        if not match:
            raise ValueError("英伟达活动缺少已确认日期")
        title = match.group(2)
        if re.search(r"cancelled|canceled", title, re.I):
            continue
        kind = "公司财报" if re.search(r"financial results|earnings", title, re.I) else "重大会议"
        day = datetime.strptime(match.group(1), "%m/%d/%Y").date().isoformat()
        rows.append(calendar_event(f"nvidia:{title}:{day}", "英伟达 · " + title, kind, day, None, "America/Los_Angeles", node.findtext("link")))
    return rows


def parse_bea(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#release-schedule-table")
    if not table or not re.search(r"Year\s+\d{4}", table.get_text()):
        raise ValueError("BEA 日历结构无法识别")
    year = int(re.search(r"Year\s+(\d{4})", table.get_text()).group(1))
    output = []
    for row in table.select("tbody tr"):
        d, t, clock = row.select_one(".release-date"), row.select_one(".release-title"), row.select_one(".scheduled-date small")
        if not d or not t:
            continue
        original = t.get_text(" ", strip=True)
        if not re.search(r"GDP|Personal Income and Outlays|International Trade in Goods and Services", original):
            continue
        day = datetime.strptime(f"{year} {d.get_text(strip=True)}", "%Y %B %d").date().isoformat()
        title = original.replace("U.S. International Trade in Goods and Services", "美国商品与服务贸易数据").replace("Personal Income and Outlays", "美国个人收入与支出（含 PCE）")
        output.append(calendar_event(f"bea:{original}:{day}", title, "经济数据", day, _clock(clock.get_text()) if clock else None, "America/New_York", BEA_URL))
    return output


def parse_ecb(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    seen = 0
    for dt in soup.select("dl dt"):
        text = dt.get_text(strip=True)
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
            continue
        seen += 1
        dd = dt.find_next_sibling("dd")
        original = dd.get_text(" ", strip=True) if dd else ""
        if "non-monetary" in original or not re.search(r"monetary policy|Press conference", original):
            continue
        title = "欧洲央行货币政策会议（首日）" if "Day 1" in original else "欧洲央行货币政策会议（次日）" if "Day 2" in original else "欧洲央行议息新闻发布会"
        day = datetime.strptime(text, "%d/%m/%Y").date().isoformat()
        rows.append(calendar_event(f"ecb:{original}:{day}", title, "央行决议", day, None, "Europe/Berlin", ECB_URL))
    if not seen:
        raise ValueError("欧洲央行日历结构无法识别")
    return rows


def parse_bls(text):
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text or text.count("BEGIN:VEVENT") != text.count("END:VEVENT"):
        raise ValueError("BLS 日历格式无法识别")
    text = re.sub(r"\r?\n[ \t]", "", text)
    rows = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        fields = {}
        for line in block.strip().splitlines():
            if ":" in line:
                key, val = line.strip().split(":", 1)
                fields[key.split(";")[0]] = (key, val)
        original = fields.get("SUMMARY", ("", ""))[1]
        if fields.get("STATUS", ("", ""))[1] == "CANCELLED":
            continue
        title = next((zh for en, zh in [("Employment Situation", "美国非农就业报告"), ("Consumer Price Index", "美国 CPI 通胀数据"), ("Producer Price Index", "美国 PPI 数据"), ("Job Openings", "美国职位空缺数据")] if en in original), None)
        if not title:
            continue
        key, val = fields.get("DTSTART", ("", ""))
        if not re.fullmatch(r"\d{8}(?:T\d{6}Z?)?", val):
            raise ValueError("BLS 活动日期格式异常")
        day = datetime.strptime(val[:8], "%Y%m%d").date().isoformat()
        clock = f"{val[9:11]}:{val[11:13]}:{val[13:15]}" if "T" in val else None
        zone_match = re.search(r"TZID=([^;]+)", key)
        zone = "UTC" if val.endswith("Z") else zone_match.group(1).strip('"') if zone_match else "America/New_York"
        rows.append(calendar_event(fields.get("UID", ("", original + day))[1], title, "经济数据", day, clock, zone, fields.get("URL", ("", BLS_URL))[1]))
    return rows


def fetch_text(url):
    # Only explicit official URLs supplied by this module. No user-provided targets.
    response = requests.get(url, timeout=(5, 18), headers={"User-Agent": "FT-Research/1.0 (private financial calendar)", "Accept": "text/html,application/xml,text/calendar"})
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("日历响应过大")
    return response.content


class FinancialCalendar:
    def __init__(self, cache_dir, now_fn=lambda: datetime.now(timezone.utc), fetchers=None):
        self.path = Path(cache_dir) / "calendar.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.now_fn = now_fn
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.fetchers = fetchers if fetchers is not None else {
            "fed": self._fetch_fed, "ecb": lambda: parse_ecb(fetch_text(ECB_URL)),
            "bea": lambda: parse_bea(fetch_text(BEA_URL)), "nvidia": lambda: parse_nvidia(fetch_text(NVIDIA_FEED)),
            "bls": lambda: parse_bls(fetch_text(BLS_URL).decode("utf-8-sig")),
        }

    def _fetch_fed(self):
        now = self.now_fn().astimezone(BEIJING)
        months = {(now.year, now.month), ((now + timedelta(days=14)).year, (now + timedelta(days=14)).month)}
        rows = []
        for year, month in sorted(months):
            url = f"https://www.federalreserve.gov/newsevents/{year}-{calendar.month_name[month].lower()}.htm"
            rows.extend(parse_fed(fetch_text(url), year, month, url))
        return rows

    def _read(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}

    def overview(self):
        data = self._read()
        now = self.now_fn().astimezone(BEIJING)
        end = now + timedelta(days=14)
        items, statuses = [], []
        for source in self.fetchers:
            entry = data.get("sources", {}).get(source, {})
            fetched = entry.get("lastSuccessAt")
            expired = not fetched or (now - datetime.fromisoformat(fetched)).total_seconds() > REFRESH_SECONDS * 2
            stale = not entry.get("ok") or expired
            name, url = SOURCES.get(source, (source, ""))
            statuses.append({"id": source, "name": name, "url": url, "ok": bool(entry.get("ok")) and not expired,
                             "lastSuccessAt": fetched, "error": entry.get("error"), "count": len(entry.get("items", []))})
            for row in entry.get("items", []):
                if row.get("status") == "cancelled" or not safe_url(row.get("originalUrl")):
                    continue
                starts = datetime.fromisoformat(row["startsAt"]) if row.get("startsAt") else None
                local_zone = ZoneInfo(row.get("sourceTimezone") or "UTC")
                eligible = now <= starts <= end if starts else now.astimezone(local_zone).date().isoformat() <= row["date"] <= end.astimezone(local_zone).date().isoformat()
                if eligible:
                    items.append({**row, "source": name, "stale": stale, "fetchedAt": fetched})
        items = list({r["id"]: r for r in items}.values())
        items.sort(key=lambda r: (r["date"], r.get("startsAt") or r["date"] + "T23:59", r["title"]))
        return {"items": items, "windowStart": now.isoformat(), "windowEnd": end.isoformat(), "timezone": "Asia/Shanghai",
                "generatedAt": data.get("generatedAt"), "stale": any(r["stale"] for r in items),
                "partial": any(not s["ok"] for s in statuses), "sources": statuses, "refreshIntervalSeconds": REFRESH_SECONDS}

    def refresh(self):
        if not self.lock.acquire(blocking=False):
            return self.overview()
        try:
            data = self._read()
            sources = data.get("sources", {})
            now = self.now_fn().isoformat()
            def one(pair):
                key, fetcher = pair
                try:
                    rows = fetcher()
                    if not isinstance(rows, list):
                        raise ValueError("日历数据格式异常")
                    return key, {"ok": True, "items": rows, "lastSuccessAt": now, "error": None}
                except Exception as exc:
                    error = f"HTTP {exc.response.status_code}" if isinstance(exc, requests.HTTPError) and exc.response is not None else "来源暂不可用或结构已变化"
                    return key, {**sources.get(key, {}), "ok": False, "error": error, "attemptedAt": now}
            with ThreadPoolExecutor(max_workers=5) as pool:
                updated = dict(pool.map(one, self.fetchers.items()))
            payload = {"generatedAt": now, "sources": updated}
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.path)
        finally:
            self.lock.release()
        return self.overview()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def run():
            while not self.stop_event.is_set():
                try:
                    self.refresh()
                except Exception:
                    pass  # Preserve last atomic snapshot; retry on the next cycle.
                self.stop_event.wait(REFRESH_SECONDS)
        self.thread = threading.Thread(target=run, name="financial-calendar", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
