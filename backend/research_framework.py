"""按页面默认范围与用户问题组合研究提示词。"""

from __future__ import annotations

import re
from typing import Literal


AnalysisScope = Literal["general", "market", "index", "sector", "stock"]

COMMON_RULES = """【共同研究规则】
- 客观数据优先：需要行情、财务、资金、板块或事件数据时先调用工具，不得编造数字或用观点代替事实。
- 明确区分事实、推断与待验证条件；工具缺失、上游不可用或样本不足时必须标注“数据缺口”。
- 技术位置、支撑压力、均线和量能只用于描述状态与验证条件，不提供买卖、仓位、止损、目标价、评级或收益承诺。
- 用户明确提到的研究对象优先于页面默认范围；简单事实直接回答，单点问题只展开相关模块，全面分析才使用完整框架。
"""

SCOPE_FRAMEWORKS: dict[AnalysisScope, str] = {
    "general": """【通用信息分析】
围绕用户问题整理事实、影响路径、不同解释、风险与数据缺口；不要强行套用市场、板块或个股完整框架。""",
    "market": """【市场复盘框架】
完整复盘依次覆盖：指数整体结构；成交量与关键位置；市场宽度和短线情绪；板块轮动与资金扩散；龙头、中军、补涨和跟风结构；全球市场映射；多情景验证、失效条件与数据缺口。""",
    "index": """【指数研究框架】
完整分析依次覆盖：周期趋势与 K 线结构；EMA/均线、量能、波动与关键位置；市场宽度与板块贡献；海外及宏观映射；待验证条件、失效条件与数据缺口。""",
    "sector": """【板块研究框架】
完整分析依次覆盖：板块相对强弱与历史量价；资金流入、扩散和持续性；龙头、中军、补涨结构；产业景气、业绩和事件驱动；上涨、回落、震荡情景及证伪条件；数据缺口。""",
    "stock": """【个股融合研究框架】
完整分析依次覆盖：结论与关键数据；估值、财报质量与行业景气；资金、筹码与机构行为；大盘—板块—个股联动；K 线、EMA/均线、成交量与关键位置；催化、风险、情景验证与失效条件；数据缺口。""",
}

_STOCK_RE = re.compile(r"(?:个股|这只股票|该股|股票|公司基本面)")
_SIX_DIGIT_RE = re.compile(r"\b\d{6}\b")
_SECTOR_RE = re.compile(r"(?:板块|行业|赛道|产业链)")
_INDEX_RE = re.compile(r"(?:指数|上证|深证|创业板|沪深\s*300|科创\s*50|纳指|标普|道指)")
_MARKET_RE = re.compile(r"(?:大盘|盘面|市场情绪|今日\s*A\s*股|A\s*股市场|市场复盘)", re.IGNORECASE)
_FULL_RE = re.compile(r"(?:全面分析|综合分析|完整分析|深度分析|系统分析|复盘)")
_FACT_RE = re.compile(r"(?:现价|价格|市值|代码).{0,8}(?:多少|是什么|查询|几)|(?:多少|查询).{0,8}(?:现价|价格|市值)")


def latest_question(messages: list[dict] | None) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"]).strip()
    return ""


def resolve_scope(default_scope: AnalysisScope, question: str) -> AnalysisScope:
    """明确对象覆盖页面默认值；多个对象同时出现时优先更具体的对象。"""
    if _STOCK_RE.search(question):
        return "stock"
    if default_scope in {"general", "stock"} and _SIX_DIGIT_RE.search(question):
        return "stock"
    if _SECTOR_RE.search(question):
        return "sector"
    if _INDEX_RE.search(question):
        return "index"
    if _MARKET_RE.search(question):
        return "market"
    return default_scope


def resolve_answer_mode(question: str) -> Literal["fact", "focused", "full"]:
    if _FULL_RE.search(question):
        return "full"
    if len(question) <= 40 and _FACT_RE.search(question):
        return "fact"
    return "focused"


def build_guidance(default_scope: AnalysisScope, messages: list[dict] | None = None) -> str:
    question = latest_question(messages)
    scope = resolve_scope(default_scope, question)
    mode = resolve_answer_mode(question)
    mode_label = {"fact": "事实简答", "focused": "聚焦回答", "full": "完整分析"}[mode]
    if mode == "fact":
        mode_rule = "直接回答事实；只补充必要的数据时间和来源，不展开完整研究框架。"
    elif mode == "focused":
        mode_rule = "只展开与问题直接相关的模块；不要为了形式完整而罗列无关维度。"
    else:
        mode_rule = "使用实际范围对应的完整框架；先给客观结论，再列依据、冲突、风险与数据缺口。"
    return (
        f"{COMMON_RULES}\n【本次路由】页面默认范围：{default_scope}；实际范围：{scope}；回答模式：{mode_label}。\n"
        f"{mode_rule}\n\n{SCOPE_FRAMEWORKS[scope]}"
    )
