from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class PolicyChunk:
    chunk_id: str
    title: str
    content: str
    metadata: dict[str, str] = field(default_factory=dict)


_ARTICLE_RE = re.compile(r"(第[一二三四五六七八九十百]+条)")
_CHAPTER_RE = re.compile(r"(第[一二三四五六七八九十]+章)\s*([^第\n]+)?")


def clean_policy_text(text: str) -> str:
    text = text.replace("\r", "\n").replace("\u3000", " ")
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "?":
            continue
        line = re.sub(r"\?+", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if _looks_like_empty_form_line(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _looks_like_empty_form_line(line: str) -> bool:
    form_tokens = ("单位（公章）", "工 号", "姓 名", "电 话", "转卡金额", "合计人民币")
    if any(token in line for token in form_tokens):
        return True
    return len(line) <= 8 and any(token in line for token in ("—", "□"))


def build_policy_chunks(text: str, *, source: str) -> list[PolicyChunk]:
    clean = clean_policy_text(text)
    chunks: list[PolicyChunk] = []
    chunks.extend(_article_chunks(clean, source=source))
    chunks.extend(_appendix_chunks(clean, source=source))
    return _dedupe_chunks(chunks)


def _article_chunks(text: str, *, source: str) -> list[PolicyChunk]:
    parts = _ARTICLE_RE.split(text)
    chunks: list[PolicyChunk] = []
    current_chapter = "总则"
    if parts and parts[0]:
        chapter_match = _CHAPTER_RE.search(parts[0])
        if chapter_match:
            current_chapter = _chapter_title(chapter_match)
    for index in range(1, len(parts), 2):
        article = parts[index]
        body = parts[index + 1] if index + 1 < len(parts) else ""
        chapter_match = _CHAPTER_RE.search(body)
        if chapter_match:
            before = body[: chapter_match.start()].strip()
            if before:
                chunks.append(_make_chunk(source, current_chapter, article, f"{article} {before}"))
            current_chapter = _chapter_title(chapter_match)
            body = body[chapter_match.end() :].strip()
        appendix_index = body.find("分地区、分级别差旅住宿费")
        if appendix_index >= 0:
            body = body[:appendix_index].strip()
        content = f"{current_chapter}\n{article} {body}".strip()
        if len(content) >= 12:
            chunks.append(_make_chunk(source, current_chapter, article, content))
    return chunks


def _appendix_chunks(text: str, *, source: str) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    lodging_rows = [
        ("北京、上海、海南、西藏、青海、深圳", "800", "500", "350"),
        ("浙江、广东、江苏、厦门、青岛、大连", "800", "490", "340"),
        ("新疆", "800", "480", "340"),
        ("辽宁、福建、山东、河南、重庆、云南", "800", "", "330"),
        ("湖北", "800", "", "320"),
        ("山西", "800", "", "310"),
        ("广西、甘肃、宁夏", "800", "470", "330"),
        ("江西、四川、贵州", "800", "", "320"),
        ("内蒙古、陕西", "800", "460", "320"),
        ("安徽", "800", "", "310"),
        ("湖南", "800", "450", "330"),
        ("天津", "800", "", "320"),
        ("河北、吉林、黑龙江", "800", "", "310"),
    ]
    if "住宿费房型" in text or "北京、上海、海南" in text:
        for area, provincial, department, others in lodging_rows:
            parts = [
                "附件1 住宿费限额标准",
                f"地区：{area}",
                f"省级及相当职级人员{provincial}元/天",
            ]
            if department:
                parts.append(f"厅级及相当职级人员、高级专业技术职称人员{department}元/天")
            if others:
                parts.append(f"其余人员{others}元/天")
            chunks.append(
                _make_chunk(
                    source,
                    "附件1",
                    f"住宿费限额标准-{area}",
                    "；".join(parts) + "。",
                    kind="lodging_limit",
                )
            )
    allowance = (
        "附件1 伙食补助费和公杂费标准：省外伙食补助费每人每天100元，"
        "西藏、青海、新疆每人每天120元；省内凭餐饮发票每人每天100元标准内据实报销，"
        "无餐饮发票按每人每天30元包干。省外公杂费每人每天80元；"
        "省内凭市内交通等公杂费发票每人每天60元限额内据实报销，"
        "无公杂费发票按每人每天30元补助。"
    )
    if "伙食" in text and "公杂费" in text:
        chunks.append(_make_chunk(source, "附件1", "伙食补助费和公杂费标准", allowance, kind="allowance"))
    return chunks


def _chapter_title(match: re.Match[str]) -> str:
    name = (match.group(2) or "").strip()
    return f"{match.group(1)} {name}".strip()


def _make_chunk(
    source: str,
    chapter: str,
    title: str,
    content: str,
    *,
    kind: str = "article",
) -> PolicyChunk:
    normalized = re.sub(r"\s+", " ", content).strip()
    digest = hashlib.sha256(f"{source}|{title}|{normalized}".encode("utf-8")).hexdigest()[:16]
    return PolicyChunk(
        chunk_id=f"{source}:{digest}",
        title=title,
        content=normalized,
        metadata={"source": source, "chapter": chapter, "kind": kind},
    )


def _dedupe_chunks(chunks: list[PolicyChunk]) -> list[PolicyChunk]:
    seen: set[str] = set()
    out: list[PolicyChunk] = []
    for chunk in chunks:
        key = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out
