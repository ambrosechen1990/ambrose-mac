# -*- coding: utf-8 -*-
"""答案判定：关键词命中、拒答识别、语言识别、相似度。"""

from __future__ import annotations

import difflib
import re

# 明确表示答不上来的说法，出现在开头就能判定是拒答
STRONG_REFUSAL_MARKERS = (
    "资料不足",
    "信息还不足",
    "信息不足",
    "尚未提供",
    "无法回答",
    "无法提供",
    "不在我的",
    "无法执行",
    "不支持该操作",
    "not enough information",
    "no information",
    "i don't have",
)

# 这些话在一段完整答案的结尾也很常见（「如仍未解决，建议联系客服」），
# 只有整条回复很短、本身就是一句推诿时才算拒答
WEAK_REFUSAL_MARKERS = (
    "无法确定",
    "不确定",
    "没有找到",
    "未找到",
    "暂无",
    "不清楚",
    "没有相关",
    "未收录",
    "建议联系",
    "请联系客服",
    "cannot find",
    "could not find",
    "unable to",
)

REFUSAL_MARKERS = STRONG_REFUSAL_MARKERS + WEAK_REFUSAL_MARKERS

# 只看开头这些字判断强标记；整条短于这个长度才允许用弱标记判定
_REFUSAL_LEAD = 80
_REFUSAL_SHORT = 120


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def is_refusal(text: str) -> bool:
    """判断整条回复是不是「答不上来」。

    只要出现推诿字眼就算拒答的话，一段认真作答、末尾附带
    「如仍未解决建议联系客服」的长回复会被误判，所以要看位置和长度。
    """
    t = normalize(text).lower()
    if not t:
        return False
    if any(m.lower() in t[:_REFUSAL_LEAD] for m in STRONG_REFUSAL_MARKERS):
        return True
    return len(t) <= _REFUSAL_SHORT and any(m.lower() in t for m in REFUSAL_MARKERS)


def hit_keywords(text: str, keywords) -> tuple[list[str], list[str]]:
    """返回 (命中的关键词, 缺失的关键词)，大小写不敏感。"""
    t = normalize(text).lower()
    hits: list[str] = []
    missing: list[str] = []
    for k in keywords or []:
        if str(k).lower() in t:
            hits.append(str(k))
        else:
            missing.append(str(k))
    return hits, missing


def zh_ratio(text: str) -> float:
    """中文字符占「中文字符 + 拉丁字母」的比例。"""
    t = text or ""
    zh = len(re.findall(r"[\u4e00-\u9fff]", t))
    en = len(re.findall(r"[A-Za-z]", t))
    total = zh + en
    if total == 0:
        return 0.0
    return zh / total


def detect_language(text: str) -> str:
    """粗略语言判定：zh / en / unknown。"""
    t = normalize(text)
    if not t:
        return "unknown"
    ratio = zh_ratio(t)
    if ratio >= 0.3:
        return "zh"
    if re.search(r"[A-Za-z]{3,}", t):
        return "en"
    return "unknown"


def similarity(a: str, b: str) -> float:
    """两段文本的相似度 0~1。"""
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def judge(
    answer: str,
    *,
    expect_keywords=None,
    any_keywords=None,
    forbid_keywords=None,
    expect_refusal: bool = False,
    expect_language: str = "",
) -> tuple[bool, str]:
    """统一判定，返回 (是否通过, 原因说明)。"""
    text = normalize(answer)
    if not text:
        return False, "空回答"

    if expect_refusal:
        if is_refusal(text):
            return True, "已明确表示资料不足/无法执行"
        return False, "期望拒答，但给出了确定性回答（疑似幻觉）"

    reasons: list[str] = []

    _, missing = hit_keywords(text, expect_keywords)
    if missing:
        reasons.append(f"缺少关键词 {missing}")

    if any_keywords:
        hits, _ = hit_keywords(text, any_keywords)
        if not hits:
            reasons.append(f"未命中任一关键词 {list(any_keywords)}")

    forbidden, _ = hit_keywords(text, forbid_keywords)
    if forbidden:
        reasons.append(f"出现禁止内容 {forbidden}")

    if expect_language:
        actual = detect_language(text)
        if actual != expect_language:
            reasons.append(f"语言应为 {expect_language}，实际 {actual}")

    if reasons:
        return False, "；".join(reasons)
    return True, "通过"
