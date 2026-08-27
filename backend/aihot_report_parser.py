"""Small dependency-free parser for the private AI HOT period-report pages."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any


class _Node:
    def __init__(self, tag: str = "root", attrs: dict[str, str] | None = None):
        self.tag, self.attrs, self.children = tag, attrs or {}, []

    def text(self) -> str:
        chunks: list[str] = []
        for child in self.children:
            chunks.append(child if isinstance(child, str) else child.text())
        return " ".join("".join(chunks).split())

    def find_all(self, tag: str | None = None, attr: tuple[str, str] | None = None) -> list["_Node"]:
        found: list[_Node] = []
        for child in self.children:
            if isinstance(child, _Node):
                if (tag is None or child.tag == tag) and (attr is None or child.attrs.get(attr[0]) == attr[1]):
                    found.append(child)
                found.extend(child.find_all(tag, attr))
        return found

    def find_class(self, class_name: str) -> list["_Node"]:
        return [node for node in self.find_all() if class_name in node.attrs.get("class", "").split()]


class _TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in {"meta", "link", "img", "input", "br", "hr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag and tag not in {"meta", "link", "img", "input", "br", "hr"}:
            self.stack.pop()

    def handle_endtag(self, tag: str):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str):
        if data.strip():
            self.stack[-1].children.append(unescape(data))


def _first_text(node: _Node, tag: str) -> str:
    matches = node.find_all(tag)
    return matches[0].text() if matches else ""


def parse_report_html(html: str, *, kind: str, period: str, source_url: str) -> dict[str, Any]:
    parser = _TreeParser()
    parser.feed(html)
    root = parser.root
    lead_nodes = root.find_class("period-lead-overview") or root.find_all(attr=("data-lead", ""))
    lead = lead_nodes[0].text().replace("本期主线", "", 1).strip() if lead_nodes else ""
    stats: dict[str, int] = {}
    for node in root.find_all(attr=("data-stat", "")):
        raw = node.text().replace(",", "").strip()
        if raw.isdigit():
            stats[node.attrs["data-stat"]] = int(raw)
    for node in root.find_all():
        if "data-stat" in node.attrs:
            raw = node.text().replace(",", "").strip()
            if raw.isdigit():
                stats[node.attrs["data-stat"]] = int(raw)
    for stat in root.find_class("period-stat"):
        value_nodes = stat.find_class("period-stat-value")
        label_nodes = stat.find_class("period-stat-label")
        raw = value_nodes[0].text().replace(",", "").strip() if value_nodes else ""
        label = label_nodes[0].text() if label_nodes else ""
        if label and raw.isdigit():
            stats[label] = int(raw)

    themes: list[dict[str, Any]] = []
    sections = root.find_class("daily-section") or root.find_all(attr=("data-theme", ""))
    for section in sections:
        heading_nodes = section.find_class("daily-section-title")
        heading = (heading_nodes[0].text() if heading_nodes else "") or _first_text(section, "h2") or _first_text(section, "h3") or "未命名主题"
        intro_nodes = section.find_class("period-theme-intro")
        stories: list[dict[str, Any]] = []
        for article in section.find_class("period-story") or section.find_all("article"):
            links: dict[str, str] = {}
            for link in article.find_all("a"):
                href = link.attrs.get("href", "")
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://aihot.virxact.com" + href
                if "aihot.virxact.com" in href:
                    links["aihot"] = href
                    if "/items/" in href and "original" not in links:
                        links["original"] = href
                    if "/story/" in href:
                        links["story"] = href
                elif "original" not in links:
                    links["original"] = href
            story: dict[str, Any] = {
                "title": (article.find_class("period-story-title") or [None])[0].text() if article.find_class("period-story-title") else (_first_text(article, "h3") or _first_text(article, "h2")),
                "summary": _first_text(article, "p"),
                "source": "",
                "links": links,
            }
            published = article.attrs.get("data-published-at", "")
            if not published:
                times = article.find_all("time")
                published = (times[0].attrs.get("datetime") or times[0].text()) if times else ""
            if published:
                story["publishedAt"] = published
            if article.attrs.get("data-story-id"):
                story["storyId"] = article.attrs["data-story-id"]
            source_nodes = article.find_class("period-story-source") or article.find_all(attr=("data-source", ""))
            if source_nodes:
                story["source"] = source_nodes[0].text()
            stories.append(story)
        themes.append({"title": heading, "summary": intro_nodes[0].text() if intro_nodes else _first_text(section, "p"), "stories": stories})
    if not themes:
        fallback_stories: list[dict[str, Any]] = []
        seen: set[str] = set()
        for link in root.find_all("a"):
            href = link.attrs.get("href", "")
            label = link.text()
            if (not href.startswith("http") or "aihot.virxact.com" in href or "beian.miit.gov.cn" in href
                    or href.endswith("/privacy") or href.endswith("/terms") or len(label) < 8 or label in seen):
                continue
            seen.add(label)
            fallback_stories.append({"title": label, "summary": "", "source": "", "links": {"original": href}})
        if fallback_stories:
            themes.append({"title": "本期精选", "summary": "来自周期报告页面的精选报道。", "stories": fallback_stories[:50]})
    return {
        "kind": kind,
        "period": period,
        "title": _first_text(root, "h1") or ("AI HOT周报" if kind == "weekly" else "AI HOT月报"),
        "lead": lead,
        "stats": stats,
        "themes": themes,
        "source": {"provider": "AI HOT", "url": source_url},
    }
