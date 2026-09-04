"""Conservative, inspectable editorial gates for the global financial front page."""
import re

# A publisher being a financial outlet is not evidence that every article is financial.
TOPICS = (
    ("macro_release", r"通胀|非农|失业率|消费者价格|生产者价格|经济增长|经济展望|国内生产总值|财政预算|贸易|关税|进出口|出口|进口|\b(?:gdp|cpi|ppi|pce|pmi|inflation|payrolls?|unemployment|tariffs?|trade|economy|economic outlook)\b"),
    ("policy_decision", r"利率|降息|加息|降准|货币政策|量化宽松|国债收益率|资产购买|外汇政策|资本要求|资本市场|证券监管|\b(?:interest rates?|rate cuts?|rate hikes?|monetary policy|bond yields?|treasury yields?|fomc)\b"),
    ("market_structure", r"股市|美股|港股|A股|指数|熔断|期货|国债|汇率|美元|黄金|白银|原油|油价|粮价|金价|债券|基金|证券|融资|\b(?:stocks?|equities|nasdaq|s&p|dow jones|bonds?|forex|currency|currencies|oil prices?|gold|commodities|yields?)\b"),
    ("major_disclosure", r"财报|营收|净利润|业绩|盈利|上市|IPO|并购|收购|重组|破产|裁员|分红|回购|资本开支|\b(?:earnings|revenue|profits?|ipo|acquisition|merger|bankruptcy|buybacks?|dividends?|layoffs?)\b"),
    ("industry_update", r"产能|扩产|减产|供应链|供应中断|芯片.*(?:推出|发布|突破)|(?:推出|发布|突破).*芯片|技术突破|\b(?:supply chain|production cuts?|chip launch|semiconductor breakthrough)\b"),
)
_NOISE = re.compile(r"冰川|消融|上映|明星|综艺|天气预报|生态保护|旅游攻略|glacier|celebrity|movie release", re.I)
_ECONOMIC_IMPACT = re.compile(r"利率|营收|股价|股市|财报|产量|减产|出口|进口|关税|油价|粮价|损失.*[亿万]|earnings|revenue|trade|stock|oil price|economic loss", re.I)
_ALIASES = {
    "reuters": "路透社", "路透": "路透社", "路透社": "路透社",
    "bloomberg": "彭博社", "彭博": "彭博社", "彭博社": "彭博社",
    "associated press": "美联社", "美联社": "美联社", "afp": "法新社", "法新社": "法新社",
    "新华社": "新华社", "新华网": "新华社", "xinhua": "新华社",
    "中新社": "中新社", "中国新闻网": "中新社", "中新网财经": "中新社",
    "财联社": "财联社", "财联社电报": "财联社",
    "科创板日报": "财联社", "新浪财经快讯": "新浪财经",
    "bbc": "BBC", "bbc财经": "BBC", "guardian business": "The Guardian",
    "wsj markets": "Dow Jones", "marketwatch": "Dow Jones",
    "东方财富股票": "东方财富", "东方财富资讯": "东方财富", "东方财富快讯": "东方财富",
}
_WIRE = r"路透社?|Reuters|彭博社?|Bloomberg|美联社|Associated Press|法新社|AFP|新华社|Xinhua|中新社|财联社|科创板日报|新浪财经|闪存市场|证券时报|中国证券报|上海证券报|CNBC|BBC"
_ATTRIBUTION = re.compile(rf"(?:据|来源[：:]?\s*|转载自\s*|according to\s+|source[：:]\s*|[（(])({_WIRE})(?:\b|报道|电|消息|[）)]|\s|，|,|$)", re.I)


def headline(title):
    match = re.match(r"\s*【([^】]+)】", title or "")
    return match.group(1) if match else title or ""


def is_roundup(title):
    return bool(re.search(r"要闻速递|要闻汇总|新闻汇总|早报|晚报|morning briefing|news roundup", headline(title), re.I)) or len(re.findall(r"[①②③④⑤⑥⑦⑧⑨]", title or "")) >= 2


def financial_topic(item):
    title = str(item.get("title") or "")
    if is_roundup(title):
        return None
    blob = title + " " + str(item.get("summary") or "")[:600]
    if _NOISE.search(title) and not _ECONOMIC_IMPACT.search(blob):
        return None
    if re.search(r"中签率|中签号码|网上申购|机构调研|投资者关系活动记录", title):
        return None
    if re.search(r"会见|代表团|访问团", title) and not re.search(r"签署|关税|协议|制裁|利率", title):
        return None
    if re.search(r"签订.*合同|中标|股东.*减持|股东.*增持", title):
        return "company_disclosure"
    title_topic = next((name for name, pattern in TOPICS if re.search(pattern, title, re.I)), None)
    if title_topic:
        return title_topic
    return next((name for name, pattern in TOPICS if re.search(pattern, blob, re.I)), None)


def origin_owner(report):
    declared = str(report.get("originSource") or "").strip()
    if not declared:
        blob = f"{report.get('title', '')} {report.get('summary', '')}"
        match = _ATTRIBUTION.search(blob) or re.search(r"(财联社|新华社|中新社)(?:\S{0,8}?)\d+月\d+日电", blob)
        declared = match.group(1) if match else str(report.get("source") or "公开来源")
    return _ALIASES.get(declared.lower(), declared)


def independent_sources(reports):
    owners, copied = set(), set()
    output = []
    channels = {"同花顺快讯", "东方财富快讯", "新浪财经快讯", "财联社电报"}
    bodies = []
    # Prefer an explicitly attributed wire over the carrier when identical
    # copy has had its dateline removed. This is conservative evidence, not reach.
    ordered = sorted(reports, key=lambda r: not (r.get("originSource") or _ATTRIBUTION.search(str(r.get("summary") or "")) or r.get("source") == "财联社电报"))
    for report in ordered:
        owner = origin_owner(report)
        # Even altered headlines / repeated polling from one publisher count once.
        if owner in owners:
            continue
        fingerprint = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", f"{report.get('title', '')}{str(report.get('summary') or '')[:120]}".lower())
        is_channel = report.get("source") in channels
        body = re.sub(r"^\s*【[^】]+】", "", str(report.get("summary") or ""))
        body = re.sub(r"^(?:财联社|新华社|中新社)\S{0,8}?\d+月\d+日电[，,：:]?", "", body)
        body = re.sub(r"[（(][^()（）]{1,40}[）)]\s*$", "", body)
        body = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", body.lower())
        copied_body = len(body) >= 40 and any((is_channel or previous_channel) and min(len(body), len(previous)) >= 40 and (body in previous or previous in body) for previous, previous_channel in bodies)
        if copied_body:
            continue
        if is_channel and fingerprint in copied:
            continue
        owners.add(owner)
        if is_channel:
            copied.add(fingerprint)
        bodies.append((body, is_channel))
        output.append(owner)
    return output
