"""
Android Gmail App 获取验证码工具。

流程（与 Appium Inspector 资源 ID 一致）：
1. 打开 Gmail 前：adb force-stop 冷启动（清除上次详情页任务栈）
2. 收件箱点击 noreply → 详情页取码
3. 取码后：terminate + adb force-stop（gm/gn 双包）+ 回桌面，再回到被测 App

为何必须彻底 kill：仅 terminate 时部分机型 Recent 仍保留 Gmail，下次 activate_app 会回到详情页。

对外入口：`get_gmail_verification_code(driver=...)`、`kill_gmail_completely(driver=...)`
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Optional

_GMAIL_PKGS = ("com.google.android.gm", "com.google.android.gn")

# 解析 uiautomator dump / page_source 中的 <node ...>（属性顺序不固定）
_NODE_TAG_RE = re.compile(r"<node[^>]+/?>", re.IGNORECASE)
_NODE_TEXT_RE = re.compile(r'\b(?:text|content-desc)="([^"]*)"', re.IGNORECASE)
_NODE_BOUNDS_RE = re.compile(r'\bbounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', re.IGNORECASE)

from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_CODE_RE = re.compile(r"\b(\d{6})\b")
_CODE_SPACED_RE = re.compile(r"(?<!\d)(\d{3})[\s\-]+(\d{3})(?!\d)")
_CODE_EXACT_RE = re.compile(r"^\d{6}$")

# 耗时控制（可通过环境变量覆盖）
# kill 后重进 Gmail 列表已是新的，默认短等 noreply 出现即点击，不做下拉刷新
GMAIL_INBOX_WAIT_S = int(os.environ.get("GMAIL_INBOX_WAIT_S", "5"))
GMAIL_POST_OPEN_SETTLE_S = float(os.environ.get("GMAIL_POST_OPEN_SETTLE_S", "0.2"))
GMAIL_SENDERS_WAIT_S = int(os.environ.get("GMAIL_SENDERS_WAIT_S", "5"))
GMAIL_CLICK_SETTLE_S = float(os.environ.get("GMAIL_CLICK_SETTLE_S", "0.35"))
GMAIL_OPEN_MAIL_TIMEOUT_S = int(os.environ.get("GMAIL_OPEN_MAIL_TIMEOUT_S", "15"))
GMAIL_EXTRACT_CODE_TIMEOUT_S = int(os.environ.get("GMAIL_EXTRACT_CODE_TIMEOUT_S", "10"))
# 默认关闭 adb shell（你当前 Appium 未开启 adb_shell，调用会拖慢数分钟）
GMAIL_USE_ADB_SHELL = os.environ.get("GMAIL_USE_ADB_SHELL", "0").strip() in {"1", "true", "yes"}

_ADB_SHELL_OK: bool | None = None

# Gmail 收件箱 / 详情页（与 Appium Inspector 一致）
GMAIL_RID_SENDERS = "com.google.android.gm:id/senders"
GMAIL_RID_DATE = "com.google.android.gm:id/date"
# 兼容 Gmail / Gmail Go（gn 包名）
XPATH_GMAIL_SENDERS = '//*[contains(@resource-id,"id/senders")]'
XPATH_GMAIL_DATE = '//*[contains(@resource-id,"id/date")]'
XPATH_NOREPLY_ROW = (
    '//*[contains(@resource-id,"conversation_view_container")]'
    '[.//*[contains(@resource-id,"id/senders") and contains(@text,"noreply")]]'
)
XPATH_BEATBOT_LABEL_2 = '(//android.widget.TextView[@text="Beatbot Verification Code"])[2]'
XPATH_BEATBOT_LABEL_ANY = '//android.widget.TextView[@text="Beatbot Verification Code"]'


def _extract_codes(text: str) -> list[str]:
    if not text:
        return []
    s = str(text)
    out: list[str] = []
    for m in _CODE_RE.finditer(s):
        out.append(m.group(1))
    for m in _CODE_SPACED_RE.finditer(s):
        out.append(f"{m.group(1)}{m.group(2)}")
    return out


def _tap(driver, elem) -> None:
    try:
        elem.click()
        return
    except Exception:
        pass
    try:
        r = elem.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]
    except Exception:
        raise


def _can_use_adb_shell(driver) -> bool:
    """检测是否允许 mobile: shell（未开启时跳过，避免每次等待失败）。"""
    global _ADB_SHELL_OK
    if not GMAIL_USE_ADB_SHELL:
        return False
    if _ADB_SHELL_OK is not None:
        return _ADB_SHELL_OK
    try:
        driver.execute_script("mobile: shell", {"command": "echo", "args": ["ok"]})
        _ADB_SHELL_OK = True
    except Exception:
        _ADB_SHELL_OK = False
    return _ADB_SHELL_OK


def _tap_xy(driver, x: int, y: int) -> None:
    """按屏幕坐标点击（gesture / tap；无 adb_shell 时不走 shell）。"""
    x, y = int(x), int(y)
    try:
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        return
    except Exception:
        pass
    driver.tap([(x, y)])  # type: ignore[attr-defined]


def _mail_opened_or_code_visible(driver) -> bool:
    """点击邮件后是否已进入详情页。"""
    if GMAIL_CLICK_SETTLE_S > 0:
        time.sleep(GMAIL_CLICK_SETTLE_S)
    return _is_mail_detail_page(driver) or _is_mail_detail_with_beatbot(driver)


def _wait_detail_opened(driver, timeout_s: float = 2.0) -> bool:
    """点击后短等详情页（Beatbot 标题或详情特征）。"""
    try:
        WebDriverWait(driver, timeout_s, poll_frequency=0.15).until(
            lambda d: _is_mail_detail_with_beatbot(d) or _is_mail_detail_page(d)
        )
        return True
    except TimeoutException:
        return False


def _tap_noreply_row(driver, y_anchor: int, *, offsets: tuple[int, ...] = (35, 75, 115)) -> bool:
    """在 noreply 发件人所在行，用多个纵向偏移尝试点击打开邮件。"""
    size = driver.get_window_size()
    tx = int(size["width"] * 0.62)
    for dy in offsets:
        ty = int(y_anchor + dy)
        print(f"    📧 点击邮件行: ({tx},{ty})")
        _tap_xy(driver, tx, ty)
        if _mail_opened_or_code_visible(driver):
            return True
    return False


def _is_inbox_list_page(driver) -> bool:
    """判断是否仍在 Gmail 收件箱列表页（避免误判已进入详情）。"""
    try:
        for xp in (
            '//*[contains(@resource-id,"conversation_view_container")]',
            '//*[contains(@resource-id,"conversation_list_place_holder")]',
            '//*[contains(@text,"搜索邮件") or contains(@text,"Search mail")]',
        ):
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
    except Exception:
        pass
    return False


def _is_mail_detail_page(driver) -> bool:
    """
    判断是否已进入邮件详情页。

    规则：先认详情特征（返回/正文），再排除纯收件箱列表。
    """
    try:
        for xp in (
            '//*[@content-desc="Navigate up" or @content-desc="Back" or @content-desc="返回"]',
            '//*[contains(@resource-id,"up") and (@class="android.widget.ImageButton" or @class="android.widget.Button")]',
        ):
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    try:
        tvs = driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView")
        visible = 0
        for t in tvs[:120]:
            try:
                if t.is_displayed() and (t.text or t.get_attribute("text")):
                    visible += 1
            except Exception:
                continue
        if visible >= 6:
            return True
    except Exception:
        pass

    # 仍在收件箱且无任何详情特征 → 未打开
    if _is_inbox_list_page(driver):
        return False
    return False


def _shell_dump_ui_xml(driver) -> str:
    """获取界面 XML；默认 page_source（快），仅 GMAIL_USE_ADB_SHELL=1 时用 uiautomator dump。"""
    if not _can_use_adb_shell(driver):
        try:
            return driver.page_source or ""
        except Exception:
            return ""

    dump_path = "/data/local/tmp/gmail_uidump.xml"
    try:
        driver.execute_script(
            "mobile: shell",
            {"command": "uiautomator", "args": ["dump", dump_path]},
        )
        time.sleep(0.3)
        out = driver.execute_script("mobile: shell", {"command": "cat", "args": [dump_path]})
        if isinstance(out, str) and "<hierarchy" in out:
            return out
        if isinstance(out, bytes):
            s = out.decode("utf-8", errors="ignore")
            if "<hierarchy" in s:
                return s
    except Exception:
        pass
    try:
        return driver.page_source or ""
    except Exception:
        return ""


def _collect_text_nodes_from_xml(xml: str) -> list[tuple[str, int, int, int, int]]:
    """从 XML 提取 (text, x1, y1, x2, y2) 列表。"""
    out: list[tuple[str, int, int, int, int]] = []
    if not xml:
        return out
    for tag in _NODE_TAG_RE.findall(xml):
        tm = _NODE_TEXT_RE.search(tag)
        bm = _NODE_BOUNDS_RE.search(tag)
        if not tm or not bm:
            continue
        text = (tm.group(1) or "").strip()
        if not text:
            continue
        x1, y1, x2, y2 = int(bm.group(1)), int(bm.group(2)), int(bm.group(3)), int(bm.group(4))
        out.append((text, x1, y1, x2, y2))
    return out


def _collect_all_text_from_xml(xml: str) -> str:
    nodes = _collect_text_nodes_from_xml(xml)
    return "\n".join(t[0] for t in nodes)


_TIME_META_RE = re.compile(
    r"^(上午|下午|周[一二三四五六日天]|昨天|今天|\d{1,2}:\d{2}|\d+月\d+日|[A-Za-z]{3}\s+\d)",
    re.IGNORECASE,
)
_INBOX_SKIP_TEXTS = {
    "搜索邮件",
    "search mail",
    "写邮件",
    "compose",
    "推广",
    "promotions",
    "主要",
    "primary",
    "邮件",
    "mail",
}


# 单行邮件容器高度上限（超过则视为整页列表父容器，不能用来点击）
_MAX_ROW_CONTAINER_HEIGHT = 220


@dataclass
class _GmailInboxRow:
    """收件箱单行邮件（发件人 + 主题 + 纵向位置）。"""

    sender: str
    subject: str
    y_top: int
    y_bottom: int = 0
    element: Any = None  # 发件人 TextView 或单行容器


def _is_inbox_meta_text(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) <= 1:
        return True
    low = t.lower()
    if low in _INBOX_SKIP_TEXTS:
        return True
    if _TIME_META_RE.match(t):
        return True
    return False


_KNOWN_OTHER_SENDERS = {
    "amazon business",
    "ubiquiti",
    "cursor team",
    "samsung account",
    "google",
}


def _sender_matches_expected(sender: str, from_contains: Optional[str]) -> bool:
    """发件人必须精确为 noreply，排除 Ubiquiti / Amazon 等。"""
    want = (from_contains or "noreply").strip().lower()
    s = (sender or "").strip().lower()
    if not s:
        return False
    if s in _KNOWN_OTHER_SENDERS:
        return False
    if want == "noreply":
        return s == "noreply" or s.startswith("noreply@")
    return want in s


def _is_probable_sender_label(text: str) -> bool:
    """判断 TextView 文案是否像「发件人」而不是主题/预览。"""
    t = (text or "").strip()
    if not t or _is_inbox_meta_text(t):
        return False
    if len(t) > 48:
        return False
    low = t.lower()
    if "verification code" in low or "beatbot verification" in low:
        return False
    if low.startswith("beatbot "):
        return False
    return True


def _subject_matches_expected(subject: str, subject_contains: str) -> bool:
    subj = (subject_contains or "").strip().lower()
    if not subj:
        return True
    return subj in (subject or "").strip().lower()


def _cluster_text_parts_to_rows(
    parts: list[tuple[float, float, str]],
    *,
    y_top: int = 0,
    y_bottom: int = 0,
    element: Any = None,
) -> Optional[_GmailInboxRow]:
    """把同一邮件行内的 TextView 文案聚合成 (发件人, 主题)。"""
    if not parts:
        return None
    parts.sort(key=lambda p: (p[0], p[1]))
    lines: list[list[str]] = []
    line_y: list[float] = []
    for y, _x, s in parts:
        if lines and abs(y - line_y[-1]) < 56:
            lines[-1].append(s)
        else:
            lines.append([s])
            line_y.append(y)
    flat: list[str] = []
    for group in lines:
        flat.extend(group)
    if not flat:
        return None
    sender = flat[0]
    subject = flat[1] if len(flat) > 1 else ""
    return _GmailInboxRow(
        sender=sender,
        subject=subject,
        y_top=y_top or int(line_y[0]),
        y_bottom=y_bottom,
        element=element,
    )


def _subject_near_sender_y(driver, y0: int, band: int = 200) -> str:
    """取与发件人同一邮件行内的主题/预览文案。"""
    found = ""
    try:
        for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
            try:
                if not el.is_displayed():
                    continue
                s = (el.text or el.get_attribute("text") or "").strip()
                if not s or _is_inbox_meta_text(s):
                    continue
                r = el.rect
                if abs(int(r["y"]) - y0) > band:
                    continue
                if "beatbot" in s.lower():
                    return s
                if not found and len(s) > len(found):
                    found = s
            except Exception:
                continue
    except Exception:
        pass
    return found


def _list_gmail_inbox_rows_by_sender_labels(driver) -> list[_GmailInboxRow]:
    """
    按「发件人 TextView」枚举当前页每一封邮件（与 Gmail 列表左侧发件人一致）。
    """
    rows: list[_GmailInboxRow] = []
    try:
        size = driver.get_window_size()
        left_max_x = int(size["width"] * 0.52)
    except Exception:
        left_max_x = 540

    try:
        for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
            try:
                if not el.is_displayed():
                    continue
                s = (el.text or el.get_attribute("text") or "").strip()
                if not _is_probable_sender_label(s):
                    continue
                r = el.rect
                if int(r["x"]) > left_max_x:
                    continue
                y_top = int(r["y"])
                y_bottom = int(r["y"] + r["height"])
                subject = _subject_near_sender_y(driver, y_top)
                rows.append(
                    _GmailInboxRow(
                        sender=s,
                        subject=subject,
                        y_top=y_top,
                        y_bottom=y_bottom,
                        element=el,
                    )
                )
            except Exception:
                continue
    except Exception:
        return rows

    rows.sort(key=lambda r: r.y_top)
    deduped: list[_GmailInboxRow] = []
    for row in rows:
        if deduped and abs(row.y_top - deduped[-1].y_top) < 45:
            continue
        deduped.append(row)
    return deduped


def _list_gmail_inbox_rows_from_containers(driver) -> list[_GmailInboxRow]:
    """从每个「单行」conversation_view_container 解析发件人（跳过整页列表父容器）。"""
    rows: list[_GmailInboxRow] = []
    try:
        containers = driver.find_elements(
            AppiumBy.XPATH,
            '//*[contains(@resource-id,"conversation_view_container")]',
        )
    except Exception:
        return rows

    for c in containers:
        try:
            if not c.is_displayed():
                continue
            rect = c.rect
            h = int(rect["height"])
            if h > _MAX_ROW_CONTAINER_HEIGHT:
                continue
            y_top = int(rect["y"])
            y_bottom = int(rect["y"] + rect["height"])
            parts: list[tuple[float, float, str]] = []
            for t in c.find_elements(AppiumBy.XPATH, ".//android.widget.TextView"):
                try:
                    if not t.is_displayed():
                        continue
                    s = (t.text or t.get_attribute("text") or "").strip()
                    if not s or _is_inbox_meta_text(s):
                        continue
                    tr = t.rect
                    parts.append((float(tr["y"]), float(tr["x"]), s))
                except Exception:
                    continue
            if len(parts) > 14:
                continue
            row = _cluster_text_parts_to_rows(
                parts, y_top=y_top, y_bottom=y_bottom, element=c
            )
            if row and row.sender and _is_probable_sender_label(row.sender):
                rows.append(row)
        except Exception:
            continue

    rows.sort(key=lambda r: r.y_top)
    return rows


def _list_gmail_inbox_rows_from_shell(xml: str) -> list[_GmailInboxRow]:
    """shell dump 按纵向位置聚类为邮件行。"""
    nodes = _collect_text_nodes_from_xml(xml)
    usable = [
        (y1, x1, text)
        for text, x1, y1, x2, y2 in nodes
        if y1 > 120 and not _is_inbox_meta_text(text)
    ]
    usable.sort(key=lambda n: (n[0], n[1]))
    if not usable:
        return []

    clusters: list[list[tuple[float, float, str]]] = []
    cur: list[tuple[float, float, str]] = []
    cur_y = -1
    for y1, x1, text in usable:
        if cur and y1 - cur_y > 130:
            clusters.append(cur)
            cur = []
        cur.append((float(y1), float(x1), text))
        cur_y = y1
    if cur:
        clusters.append(cur)

    rows: list[_GmailInboxRow] = []
    for cluster in clusters:
        row = _cluster_text_parts_to_rows(cluster)
        if row and row.sender:
            rows.append(row)
    rows.sort(key=lambda r: r.y_top)
    return rows


def _scroll_inbox_to_top(driver) -> None:
    """
    收件箱滚到顶部（默认关闭）。

    kill Gmail 后重新打开，列表已是刷新后的状态，再滑动易触发下拉刷新且浪费时间。
    仅调试需要时设 GMAIL_SCROLL_INBOX=1。
    """
    if os.environ.get("GMAIL_SCROLL_INBOX", "0").strip() not in {"1", "true", "yes"}:
        return
    try:
        size = driver.get_window_size()
        w, h = int(size["width"]), int(size["height"])
        for _ in range(2):
            driver.swipe(w // 2, int(h * 0.30), w // 2, int(h * 0.70), 300)
            time.sleep(0.2)
    except Exception:
        pass


def _collect_all_inbox_mails(driver) -> list[_GmailInboxRow]:
    """获取当前收件箱页面所有邮件（发件人列表），不主动下拉刷新。"""
    rows = _list_gmail_inbox_rows_by_sender_labels(driver)
    if len(rows) < 2:
        rows = _list_gmail_inbox_rows_from_containers(driver) or rows
    if len(rows) < 2:
        xml = _shell_dump_ui_xml(driver)
        shell_rows = _list_gmail_inbox_rows_from_shell(xml)
        if shell_rows:
            rows = shell_rows
    return rows


def _log_gmail_inbox_rows(rows: list[_GmailInboxRow]) -> None:
    print("    📋 当前页所有邮件（从上到下，最新在上）:")
    if not rows:
        print("      (无)")
        return
    for i, row in enumerate(rows, 1):
        subj = (row.subject or "")[:48]
        print(f"      [{i}] 发件人={row.sender!r}  主题={subj!r}  y={row.y_top}")


def _row_haystack(row: _GmailInboxRow) -> str:
    """合并该行所有可见文本（发件人/主题/预览）。"""
    parts = [row.sender, row.subject]
    if row.element is not None:
        try:
            for t in row.element.find_elements(AppiumBy.XPATH, ".//android.widget.TextView"):
                try:
                    if not t.is_displayed():
                        continue
                    s = (t.text or t.get_attribute("text") or "").strip()
                    if s and not _is_inbox_meta_text(s):
                        parts.append(s)
                except Exception:
                    continue
        except Exception:
            pass
    return "\n".join(parts)


def _pick_latest_noreply_row(
    rows: list[_GmailInboxRow],
    *,
    from_contains: Optional[str],
    subject_contains: str,
) -> Optional[_GmailInboxRow]:
    """在所有邮件中筛选 noreply，取 y 最小（最新）且含 Beatbot 主题的一封。"""
    noreply_rows: list[_GmailInboxRow] = []
    for row in rows:
        if not _sender_matches_expected(row.sender, from_contains):
            continue
        hay = _row_haystack(row)
        if _subject_matches_expected(hay, subject_contains):
            noreply_rows.append(row)

    if not noreply_rows:
        print("    ⚠️ 当前页未找到 noreply + Beatbot 邮件")
        return None

    noreply_rows.sort(key=lambda r: r.y_top)
    target = noreply_rows[0]
    print(
        f"    🎯 选中最新 noreply: 发件人={target.sender!r} "
        f"主题={(target.subject or '')[:48]!r} y={target.y_top}"
    )
    return target


def _page_shows_wrong_sender(driver, wrong: str) -> bool:
    """打开邮件后若详情页主发件人为 Ubiquiti 等，视为点错。"""
    bad = (wrong or "").strip().lower()
    if not bad:
        return False
    try:
        for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView")[:40]:
            try:
                if not el.is_displayed():
                    continue
                s = (el.text or el.get_attribute("text") or "").strip().lower()
                r = el.rect
                if int(r["y"]) > 400:
                    continue
                if s == bad or s.startswith(bad + " "):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _click_latest_noreply_mail(driver, target: _GmailInboxRow) -> bool:
    """只点击 text 精确为 noreply 的发件人节点所在行（不点容器中心）。"""
    print(f"    👆 点击最新 noreply 邮件行 y={target.y_top}")
    size = driver.get_window_size()
    tap_x = int(size["width"] * 0.62)

    # 1) 精确匹配发件人 TextView: @text="noreply"
    try:
        for el in driver.find_elements(
            AppiumBy.XPATH,
            '//android.widget.TextView[@text="noreply"]',
        ):
            try:
                if not el.is_displayed():
                    continue
                r = el.rect
                if abs(int(r["y"]) - target.y_top) > 120:
                    continue
                ty = int(r["y"] + r["height"] / 2)
                print(f"    📧 点击 noreply 发件人节点: ({tap_x},{ty})")
                _tap_xy(driver, tap_x, ty)
                time.sleep(2.0)
                if _page_shows_wrong_sender(driver, "ubiquiti") or _page_shows_wrong_sender(
                    driver, "amazon business"
                ):
                    print("    ⚠️ 误点其它邮件，返回收件箱重试")
                    driver.back()
                    time.sleep(1.2)
                    return False
                if _mail_opened_or_code_visible(driver):
                    return True
            except Exception:
                continue
    except Exception:
        pass

    # 2) 使用枚举时记录的发件人 element
    if target.element is not None:
        try:
            r = target.element.rect
            ty = int(r["y"] + r["height"] / 2)
            _tap_xy(driver, tap_x, ty)
            time.sleep(2.0)
            if not _page_shows_wrong_sender(driver, "ubiquiti") and _mail_opened_or_code_visible(
                driver
            ):
                return True
            if _page_shows_wrong_sender(driver, "ubiquiti"):
                driver.back()
                time.sleep(1.0)
        except Exception:
            pass

    return False


def _open_noreply_after_listing_mails(
    driver,
    *,
    from_contains: Optional[str],
    subject_contains: str,
) -> bool:
    """流程：获取当前页全部邮件 → 选最新 noreply → 点击。"""
    print("    📬 步骤1: 获取当前页所有邮件...")
    rows = _collect_all_inbox_mails(driver)
    _log_gmail_inbox_rows(rows)

    print("    📬 步骤2: 筛选最新 noreply 邮件...")
    target = _pick_latest_noreply_row(
        rows, from_contains=from_contains, subject_contains=subject_contains
    )
    if not target:
        return False

    print("    📬 步骤3: 点击该 noreply 邮件...")
    return _click_latest_noreply_mail(driver, target)


def _log_gmail_page_text_snapshot(driver, keyword: str = "noreply") -> None:
    """打印收件箱邮件名称列表（用于确认会点哪一封）。"""
    rows = _collect_all_inbox_mails(driver)
    _log_gmail_inbox_rows(rows)
    key = (keyword or "").strip().lower()
    if key:
        hit = [r for r in rows if key in (r.sender or "").lower()]
        if hit:
            print(f"    ✅ 可见发件人含 {keyword!r}: {[r.sender for r in hit]}")
        else:
            print(f"    ⚠️ 当前列表未看到发件人含 {keyword!r}")


def _try_open_noreply_via_shell_dump(
    driver,
    *,
    from_contains: Optional[str],
    subject_contains: str,
) -> bool:
    """shell dump 兜底：仍先列出全部邮件再点最新 noreply。"""
    xml = _shell_dump_ui_xml(driver)
    rows = _list_gmail_inbox_rows_from_shell(xml)
    _log_gmail_inbox_rows(rows)
    target = _pick_latest_noreply_row(
        rows, from_contains=from_contains, subject_contains=subject_contains
    )
    if not target:
        return False
    return _click_latest_noreply_mail(driver, target)


def _prepare_gmail_ui_ready(driver) -> None:
    """进入 Gmail 后短暂等待 UI 渲染（kill 后重进无需滚顶/下拉刷新）。"""
    if GMAIL_POST_OPEN_SETTLE_S > 0:
        time.sleep(GMAIL_POST_OPEN_SETTLE_S)


def _dismiss_popups(driver) -> None:
    """Gmail 弹窗快速处理（最多 2 轮，无弹窗立即退出）。"""
    candidates = (
        "Allow",
        "OK",
        "GOT IT",
        "Got it",
        "Skip",
        "Not now",
        "允许",
        "跳过",
        "稍后",
        "知道了",
    )
    for _ in range(2):
        clicked = False
        for txt in candidates:
            xp = f'//*[@text="{txt}" or contains(@text,"{txt}")]'
            try:
                for el in driver.find_elements(AppiumBy.XPATH, xp)[:2]:
                    if el.is_displayed():
                        print(f"    · 关闭 Gmail 弹窗: {txt!r}")
                        _tap(driver, el)
                        time.sleep(0.25)
                        clicked = True
                        break
            except Exception:
                continue
            if clicked:
                break
        if not clicked:
            break


def _inbox_has_noreply(driver, from_contains: Optional[str]) -> bool:
    want = (from_contains or "noreply").strip().lower()
    if not want:
        return False
    try:
        for el in driver.find_elements(
            AppiumBy.XPATH,
            f'//*[contains(@resource-id,"id/senders") and contains(@text,"{want}")]',
        )[:6]:
            if el.is_displayed():
                return True
        for el in driver.find_elements(
            AppiumBy.XPATH,
            f'//android.widget.TextView[contains(@text,"{want}")]',
        )[:6]:
            if el.is_displayed():
                return True
    except Exception:
        pass
    return False


def _wait_noreply_inbox_ready(
    driver,
    timeout_s: int,
    *,
    from_contains: Optional[str],
) -> None:
    """
    等待收件箱出现 noreply（比等 RecyclerView 更准，避免「停在首页不知道在等什么」）。
    """
    want = (from_contains or "noreply").strip()
    deadline = time.time() + timeout_s
    last_log = 0.0
    print(f"    ⏳ 等待收件箱出现 noreply（{want!r}，最多 {timeout_s}s）...")
    while time.time() < deadline:
        if _inbox_has_noreply(driver, from_contains):
            print("    ✅ 已看到 noreply 邮件，开始点击")
            return
        now = time.time()
        if now - last_log >= 1.0:
            if _is_inbox_list_page(driver):
                print("    · 收件箱列表已打开，等待 noreply 邮件到达...")
            else:
                print("    · 等待 Gmail 收件箱加载...")
            last_log = now
        time.sleep(0.15)
    raise TimeoutError(
        f"收件箱 {timeout_s}s 内未出现 noreply（{want!r}），请确认验证码邮件已发送"
    )


def _fast_click_noreply_mail(driver, *, from_contains: Optional[str]) -> bool:
    """优先快速点击 noreply，避免全量列举 senders/date。"""
    want = (from_contains or "noreply").strip()
    print(f"    👆 快速点击 noreply（{want!r}）...")

    try:
        row = driver.find_element(AppiumBy.XPATH, f"{XPATH_NOREPLY_ROW}[1]")
        if row.is_displayed():
            _tap(driver, row)
            if _wait_detail_opened(driver, 2.5):
                print("    ✅ 已进入详情（noreply 行容器）")
                return True
    except Exception:
        pass

    try:
        el = driver.find_element(
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().resourceIdMatches(".*:id/senders").textContains("{want}")',
        )
        size = driver.get_window_size()
        r = el.rect
        _tap_xy(driver, int(size["width"] * 0.65), int(r["y"] + r["height"] / 2))
        if _wait_detail_opened(driver, 2.5):
            print("    ✅ 已进入详情（senders UiAutomator）")
            return True
    except Exception:
        pass

    try:
        for el in driver.find_elements(
            AppiumBy.XPATH,
            f'//android.widget.TextView[contains(@text,"{want}")]',
        )[:3]:
            if not el.is_displayed():
                continue
            size = driver.get_window_size()
            r = el.rect
            _tap_xy(driver, int(size["width"] * 0.65), int(r["y"] + r["height"] / 2))
            if _wait_detail_opened(driver, 2.5):
                print("    ✅ 已进入详情（noreply TextView）")
                return True
    except Exception:
        pass

    return False


def _wait_inbox_loaded(driver, timeout_s: int = 25) -> None:
    """
    等待 Gmail 收件箱列表出现。
    Gmail 列表结构会随版本变化：
    - 有的版本是 RecyclerView/ListView
    - 也可能出现 conversation_list_view_container / conversation_view_container（见 Inspector 截图）
    """
    def _ok(d) -> bool:
        try:
            for el in d.find_elements(AppiumBy.XPATH, XPATH_GMAIL_SENDERS):
                if el.is_displayed():
                    return True
        except Exception:
            pass
        try:
            # RecyclerView 或 ListView 任一出现即可
            for xp in ("//androidx.recyclerview.widget.RecyclerView", "//android.widget.ListView"):
                for el in d.find_elements(AppiumBy.XPATH, xp):
                    if el.is_displayed():
                        return True
        except Exception:
            pass
        try:
            # Gmail 关键容器 resource-id（不同包名也可能共用 com.google.android.gm:id）
            ids = (
                "com.google.android.gm:id/conversation_list_view_container",
                "com.google.android.gm:id/conversation_list_place_holder",
                "com.google.android.gm:id/conversation_view_container",
                # Gmail Go（截图显示 package=com.google.android.gn）
                "com.google.android.gn:id/conversation_list_view_container",
                "com.google.android.gn:id/conversation_list_place_holder",
                "com.google.android.gn:id/conversation_view_container",
            )
            for rid in ids:
                for el in d.find_elements(AppiumBy.ID, rid):
                    if el.is_displayed():
                        return True
        except Exception:
            pass
        try:
            # 再兜底：不绑定包名，按 resource-id 末尾匹配
            for xp in (
                '//*[@resource-id and contains(@resource-id,"conversation_list_view_container")]',
                '//*[@resource-id and contains(@resource-id,"conversation_view_container")]',
            ):
                for el in d.find_elements(AppiumBy.XPATH, xp):
                    if el.is_displayed():
                        return True
        except Exception:
            pass
        return False

    WebDriverWait(driver, timeout_s, poll_frequency=0.3).until(lambda d: _ok(d))


def _recover_if_wrong_page(driver) -> None:
    """
    仅在 Gmail 内：误点进 Samsung account 等侧页时 back 回收件箱。

    不可在 Beatbot 前台调用 back()，否则会回到邮箱输入页。
    """
    if not _is_gmail_package(_current_package(driver)):
        return
    try:
        bad_markers = (
            "Samsung account",
            "Samsung Account",
        )
        for txt in bad_markers:
            xp = f'//*[contains(@text,"{txt}")]'
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                try:
                    if el.is_displayed():
                        print(f"    ↩️ Gmail 误页恢复: 检测到 {txt!r}，返回收件箱")
                        driver.back()
                        time.sleep(1.0)
                        return
                except Exception:
                    continue
    except Exception:
        pass


def _visible_text_contains(driver, keyword: str) -> bool:
    """通过遍历可见 TextView 文本，判断页面是否包含关键字（用于确认 noreply 是否在列表中）。"""
    if not keyword:
        return False
    try:
        key = keyword.strip().lower()
        if not key:
            return False
        tvs = driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView")
        for t in tvs[:160]:
            try:
                if not t.is_displayed():
                    continue
                s = (t.text or t.get_attribute("text") or "").strip()
                if s and key in s.lower():
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _elem_text(el: Any) -> str:
    for attr in ("text", "content-desc", "name"):
        try:
            v = (el.get_attribute(attr) or "").strip()
            if v:
                return v
        except Exception:
            continue
    try:
        return (el.text or "").strip()
    except Exception:
        return ""


def _current_package(driver) -> str:
    try:
        return (driver.current_package or "").strip()
    except Exception:
        return ""


def _is_gmail_package(pkg: str) -> bool:
    p = (pkg or "").strip()
    return p in _GMAIL_PKGS or p.startswith("com.google.android.gm") or p.startswith(
        "com.google.android.gn"
    )


def _gmail_stuck_on_detail_page(driver) -> bool:
    """
    判断是否停在 Gmail 邮件详情（上次用例未 kill 的典型状态）。

    注意：刚 activate_app 打开 Gmail 收件箱时包名也是 Gmail，不能据此 kill；
    否则 _kill_gmail_app 里的 back() 会退回到下层 Beatbot（ci.xingmai.com）页面。
    """
    if not _is_gmail_package(_current_package(driver)):
        return False
    if _is_inbox_list_page(driver):
        return False
    if _is_mail_detail_with_beatbot(driver):
        return True
    if _is_mail_detail_page(driver):
        return True
    return False


def _adb_cmd_prefix() -> list[str]:
    """本机 adb 命令前缀（支持 UDID/ANDROID_UDID 指定设备）。"""
    cmd = ["adb"]
    serial = (os.environ.get("ANDROID_UDID") or os.environ.get("UDID") or "").strip()
    if serial:
        cmd.extend(["-s", serial])
    return cmd


def _adb_shell(args: list[str], *, timeout_s: int = 8) -> bool:
    """执行 adb shell 子命令。"""
    if os.environ.get("GMAIL_USE_HOST_ADB", "1").strip() not in {"1", "true", "yes"}:
        return False
    try:
        r = subprocess.run(
            _adb_cmd_prefix() + ["shell"] + args,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _force_stop_pkg_host_adb(pkg: str) -> bool:
    """本机 adb force-stop（不受 Appium adb_shell 安全开关影响）。"""
    return _adb_shell(["am", "force-stop", pkg])


def _adb_go_home() -> None:
    """通过 adb 回到系统桌面，减少 Recent 中 Gmail 任务残留。"""
    _adb_shell(
        [
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.HOME",
        ],
        timeout_s=10,
    )


def _collect_gmail_pkgs(gmail_bundle_id: str = "com.google.android.gm") -> list[str]:
    """Gmail / Gmail Go 包名列表（去重）。"""
    pkgs: list[str] = []
    for p in (gmail_bundle_id, *_GMAIL_PKGS):
        if p and p not in pkgs:
            pkgs.append(p)
    return pkgs


def _force_stop_all_gmail_pkgs(
    driver=None,
    *,
    gmail_bundle_id: str = "com.google.android.gm",
    rounds: int = 2,
) -> None:
    """
    对 Gmail / Gmail Go 执行 terminate + force-stop（可重复一轮，兼容 Samsung 任务栈）。

    不调用 driver.back()，避免误退到下层 Beatbot。
    """
    pkgs = _collect_gmail_pkgs(gmail_bundle_id)
    repeat = max(1, int(os.environ.get("GMAIL_FORCE_STOP_ROUNDS", str(rounds))))
    for r in range(repeat):
        for pkg in pkgs:
            if driver is not None:
                try:
                    driver.terminate_app(pkg)
                except Exception:
                    pass
                if _can_use_adb_shell(driver):
                    try:
                        driver.execute_script(
                            "mobile: shell",
                            {"command": "am", "args": ["force-stop", pkg]},
                        )
                    except Exception:
                        pass
            if _force_stop_pkg_host_adb(pkg):
                print(f"    · adb force-stop: {pkg}" + (f" (第{r + 1}轮)" if repeat > 1 else ""))
        if r < repeat - 1:
            time.sleep(0.2)


def _go_home(driver) -> None:
    """回到桌面（Appium HOME + adb HOME）。"""
    try:
        driver.press_keycode(3)
    except Exception:
        pass
    _adb_go_home()


def kill_gmail_completely(
    driver,
    gmail_bundle_id: str = "com.google.android.gm",
) -> None:
    """
    对外：彻底关闭 Gmail，供用例在取码后或下一条用例前显式调用。

    与内部 _kill_gmail_app 相同。
    """
    _kill_gmail_app(driver, gmail_bundle_id)


def _kill_gmail_app(driver, gmail_bundle_id: str = "com.google.android.gm") -> None:
    """
    强制关闭 Gmail，清除任务栈，避免下次 activate_app 仍停在邮件详情页。

    顺序：若在前台先回桌面 → terminate + adb force-stop（gm/gn，可两轮）→ 回桌面 → 校验包名。
    """
    print("    🛑 彻底关闭 Gmail（force-stop，清除详情页任务栈）...")
    pkgs = _collect_gmail_pkgs(gmail_bundle_id)

    if _is_gmail_package(_current_package(driver)):
        _go_home(driver)
        time.sleep(0.3)

    _force_stop_all_gmail_pkgs(driver, gmail_bundle_id=gmail_bundle_id)
    _go_home(driver)
    time.sleep(0.35)

    cur = _current_package(driver)
    if _is_gmail_package(cur):
        print(f"    ⚠️ Gmail 仍在前台({cur})，再次 force-stop")
        _force_stop_all_gmail_pkgs(driver, gmail_bundle_id=gmail_bundle_id, rounds=2)
        _go_home(driver)
        time.sleep(0.35)
        cur = _current_package(driver)

    if _is_gmail_package(cur):
        print(f"    ⚠️ 关闭后当前包名仍为 Gmail: {cur}（请检查 adb 是否连到当前设备）")
    else:
        print(f"    ✅ Gmail 已彻底关闭，当前前台: {cur or '(未知)'}")


def _list_inbox_sender_date_rows(
    driver, *, max_rows: int = 12
) -> list[tuple[Any, str, str, int]]:
    """
    列举收件箱 senders + date（仅扫描前 max_rows 行，兜底路径用）。
    返回 [(senders元素, 发件人文案, 时间文案, y坐标), ...] 按从上到下排序。
    """
    senders_els = driver.find_elements(AppiumBy.XPATH, XPATH_GMAIL_SENDERS)[:max_rows]
    date_els = driver.find_elements(AppiumBy.XPATH, XPATH_GMAIL_DATE)[: max_rows * 2]
    rows: list[tuple[Any, str, str, int]] = []

    for s_el in senders_els:
        try:
            if not s_el.is_displayed():
                continue
            sender = _elem_text(s_el)
            s_y = int(s_el.rect["y"])
            date_text = ""
            best_dy = 9999
            for d_el in date_els:
                try:
                    if not d_el.is_displayed():
                        continue
                    d_y = int(d_el.rect["y"])
                    dy = abs(d_y - s_y)
                    if dy < best_dy and dy <= 90:
                        best_dy = dy
                        date_text = _elem_text(d_el)
                except Exception:
                    continue
            rows.append((s_el, sender, date_text, s_y))
        except Exception:
            continue

    rows.sort(key=lambda item: item[3])
    return rows


def _log_inbox_sender_date_rows(rows: list[tuple[Any, str, str, int]]) -> None:
    print("    📋 收件箱邮件（senders + date）:")
    if not rows:
        print("      (无)")
        return
    for i, (_el, sender, date_text, y) in enumerate(rows, 1):
        print(f"      [{i}] senders={sender!r}  date={date_text!r}  y={y}")


def _sender_is_noreply(sender: str, from_contains: Optional[str]) -> bool:
    want = (from_contains or "noreply").strip().lower()
    s = (sender or "").strip().lower()
    if not s:
        return False
    if want == "noreply":
        return "noreply" in s
    return want in s


def _read_detail_page_date(driver) -> str:
    """详情页读取 com.google.android.gm:id/date 时间文案。"""
    try:
        for el in driver.find_elements(AppiumBy.XPATH, XPATH_GMAIL_DATE):
            try:
                if el.is_displayed():
                    dt = (el.text or el.get_attribute("text") or "").strip()
                    if dt:
                        print(f"    🕐 详情页邮件时间(date): {dt!r}")
                        return dt
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _is_mail_detail_with_beatbot(driver) -> bool:
    try:
        for el in driver.find_elements(AppiumBy.XPATH, XPATH_BEATBOT_LABEL_ANY):
            if el.is_displayed():
                return True
    except Exception:
        pass
    return False


def _try_enter_noreply_detail(driver, s_el: Any, sender: str, date_text: str, y: int) -> bool:
    """
    尝试多种方式打开 noreply 邮件（senders 本身常不可 click）。
    """
    size = driver.get_window_size()
    tap_x = int(size["width"] * 0.65)
    tap_y = int(y + 50)

    attempts: list[tuple[str, Any]] = []

    # 1) 点击包含 noreply senders 的整行容器（最稳）
    try:
        row = driver.find_element(
            AppiumBy.XPATH,
            f'{XPATH_NOREPLY_ROW}[1]',
        )
        attempts.append(("noreply行容器", row))
    except Exception:
        pass

    # 2) senders 元素的祖先 conversation_view_container
    try:
        row2 = s_el.find_element(
            AppiumBy.XPATH,
            './ancestor::*[contains(@resource-id,"conversation_view_container")][1]',
        )
        attempts.append(("senders祖先容器", row2))
    except Exception:
        pass

    attempts.append(("senders节点", s_el))
    attempts.append(("坐标", (tap_x, tap_y)))

    for name, target in attempts:
        try:
            print(f"    👆 尝试点击({name}): senders={sender!r} date={date_text!r}")
            if name == "坐标":
                tx, ty = target
                _tap_xy(driver, int(tx), int(ty))
            else:
                _tap(driver, target)
            if _wait_detail_opened(driver, 2.5):
                _read_detail_page_date(driver)
                print(f"    ✅ 步骤1: 已进入 noreply 详情页（{name}）")
                return True
        except Exception as e:
            print(f"    ⚠️ 点击失败({name}): {e}")

    # 3) UiAutomator 按 senders + noreply 定位后坐标点
    try:
        el = driver.find_element(
            AppiumBy.ANDROID_UIAUTOMATOR,
            'new UiSelector().resourceIdMatches(".*:id/senders").textContains("noreply")',
        )
        r = el.rect
        _tap_xy(driver, tap_x, int(r["y"] + r["height"] / 2))
        if _wait_detail_opened(driver, 2.5):
            _read_detail_page_date(driver)
            print("    ✅ 步骤1: 已进入 noreply 详情页（UiAutomator）")
            return True
    except Exception as e:
        print(f"    ⚠️ UiAutomator 点击失败: {e}")

    return False


def _click_noreply_inbox_senders(driver, *, from_contains: Optional[str]) -> None:
    """
    兜底：列举 senders/date → 点击 noreply（快速路径失败时使用）。
    """
    print("    📬 快速点击未成功，走 senders 列举兜底...")
    WebDriverWait(driver, GMAIL_SENDERS_WAIT_S, poll_frequency=0.2).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_GMAIL_SENDERS))
    )

    rows = _list_inbox_sender_date_rows(driver)
    _log_inbox_sender_date_rows(rows)

    target: tuple[Any, str, str, int] | None = None
    for s_el, sender, date_text, y in rows:
        if _sender_is_noreply(sender, from_contains):
            target = (s_el, sender, date_text, y)
            break

    if not target:
        raise TimeoutError(
            f"收件箱未找到 noreply（{XPATH_GMAIL_SENDERS}），请确认验证码邮件已到"
        )

    s_el, sender, date_text, y = target
    if _try_enter_noreply_detail(driver, s_el, sender, date_text, y):
        return

    raise TimeoutError(
        f"已找到 noreply senders={sender!r}，但多种点击方式均未进入详情页"
    )


def _swipe_mail_detail_to_top(driver, *, max_swipes: int = 3) -> None:
    """详情页滑动到顶部（会话里最新一封邮件通常在上方）。"""
    try:
        size = driver.get_window_size()
        w, h = int(size["width"]), int(size["height"])
        for _ in range(max_swipes):
            driver.swipe(w // 2, int(h * 0.22), w // 2, int(h * 0.78), 500)
            time.sleep(0.35)
    except Exception:
        pass


def _swipe_mail_detail_to_bottom(driver, *, max_swipes: int = 5) -> None:
    """详情页向下滑动至底部（露出正文验证码区域）。"""
    try:
        size = driver.get_window_size()
        w, h = int(size["width"]), int(size["height"])
        for _ in range(max_swipes):
            driver.swipe(w // 2, int(h * 0.78), w // 2, int(h * 0.22), 500)
            time.sleep(0.35)
    except Exception:
        pass


def _is_beatbot_title_line(text: str) -> bool:
    t = (text or "").strip().lower()
    return "beatbot" in t and "verification" in t


def _is_standalone_six_digit(text: str) -> bool:
    return bool(_CODE_EXACT_RE.match((text or "").strip()))


def _read_six_digit_near_label(driver, label_el: Any) -> str | None:
    """
    读取 Beatbot 标题附近 6 位验证码。
    兼容：独立 TextView、正文含 6 位数字、标题下方较远距离。
    """
    try:
        ly = int(label_el.rect["y"])
        lh = int(label_el.rect["height"])
        y_min = ly - 10
        y_max = ly + lh + int(os.environ.get("GMAIL_CODE_BELOW_MAX_PX", "900"))
    except Exception:
        y_min, y_max = 0, 10**9

    best_exact: tuple[int, str] | None = None
    best_any: tuple[int, str] | None = None
    try:
        for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
            try:
                if not el.is_displayed():
                    continue
                t = (el.text or el.get_attribute("text") or "").strip()
                if not t:
                    continue
                try:
                    y = int(el.rect["y"])
                except Exception:
                    y = 0
                if not (y_min <= y <= y_max):
                    continue
                if _CODE_EXACT_RE.match(t):
                    if best_exact is None or y < best_exact[0]:
                        best_exact = (y, t)
                    continue
                for c in _extract_codes(t):
                    if len(c) == 6:
                        if best_any is None or y < best_any[0]:
                            best_any = (y, c)
            except Exception:
                continue
    except Exception:
        pass
    if best_exact:
        return best_exact[1]
    if best_any:
        return best_any[1]
    return None


def _extract_code_below_beatbot_label_index(driver, index: int) -> str | None:
    """取第 index 个 Beatbot Verification Code 标题附近的验证码。"""
    labels = driver.find_elements(AppiumBy.XPATH, XPATH_BEATBOT_LABEL_ANY)
    visible = []
    for el in labels:
        try:
            if el.is_displayed():
                visible.append(el)
        except Exception:
            continue
    if not visible:
        return None
    idx = index if index >= 0 else len(visible) + index
    if idx < 0 or idx >= len(visible):
        return None
    return _read_six_digit_near_label(driver, visible[idx])


def _scan_visible_six_digit_on_detail(driver) -> str | None:
    """扫描详情页所有可见 TextView，提取 6 位验证码。"""
    found: list[tuple[int, str]] = []
    try:
        for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
            try:
                if not el.is_displayed():
                    continue
                t = (el.text or el.get_attribute("text") or "").strip()
                if _CODE_EXACT_RE.match(t):
                    y = int((el.rect or {}).get("y", 0))
                    found.append((y, t))
                    continue
                for c in _extract_codes(t):
                    if len(c) == 6:
                        y = int((el.rect or {}).get("y", 0))
                        found.append((y, c))
            except Exception:
                continue
    except Exception:
        pass
    if not found:
        return None
    found.sort(key=lambda x: x[0])
    return found[0][1]


def _extract_code_from_page_source(driver) -> str | None:
    """从 page_source 正则提取 6 位验证码（兜底，优先取首次出现）。"""
    try:
        src = driver.page_source or ""
    except Exception:
        return None
    if not src:
        return None

    low = src.lower()
    for anchor in ("beatbot verification code", "verification code", "beatbot"):
        pos = low.find(anchor)
        if pos >= 0:
            window = src[pos : pos + 2500]
            codes = _extract_codes(window)
            codes = [c for c in codes if len(c) == 6 and not c.startswith("202")]
            if codes:
                return codes[0]

    codes = _extract_codes(src)
    codes = [c for c in codes if len(c) == 6 and not c.startswith("202")]
    if not codes:
        return None
    if len(codes) == 1:
        return codes[0]
    return codes[0]


def _extract_code_from_visible_page_text(driver) -> str | None:
    """
    收集可见文本，优先「Beatbot Verification Code」标题下一行的独立 6 位数字。
    避免误取标题预览行里的嵌套数字（如 Beatbot Verification Code 975302）。
    """
    lines: list[tuple[int, str]] = []
    try:
        for el in driver.find_elements(
            AppiumBy.XPATH,
            "//android.widget.TextView | //android.view.View[@text!='']",
        ):
            try:
                if not el.is_displayed():
                    continue
                t = (el.text or el.get_attribute("text") or "").strip()
                if not t:
                    continue
                y = int((el.rect or {}).get("y", 0))
                lines.append((y, t))
            except Exception:
                continue
    except Exception:
        pass
    if not lines:
        return None
    lines.sort(key=lambda x: x[0])

    for i, (y, t) in enumerate(lines):
        if not _is_beatbot_title_line(t):
            continue
        if _is_standalone_six_digit(t):
            continue
        for y2, t2 in lines[i + 1 : i + 12]:
            if _is_standalone_six_digit(t2):
                print(f"    ℹ️ 标题下独立验证码（y={y2}）: {t2}")
                return t2
            if _is_beatbot_title_line(t2):
                break

    for y, t in lines:
        if _is_standalone_six_digit(t):
            print(f"    ℹ️ 可见独立 6 位（y={y}）: {t}")
            return t

    for y, t in lines:
        if _is_beatbot_title_line(t) and len(t) > 28:
            for c in _extract_codes(t):
                if len(c) == 6 and not c.startswith("202"):
                    print(f"    ℹ️ 标题行嵌套取码（y={y}）: {c} from {t[:48]!r}")
                    return c
    return None


def _extract_code_from_detail_page(driver) -> str:
    """
    详情页提取验证码（多策略，优先最新/最靠上）：
    1. 滑到顶部 → 第 1 个 Beatbot 标题下方 / 可见独立 6 位
    2. 再滑到底部重试
    3. page_source 正则
    """
    settle = float(os.environ.get("GMAIL_DETAIL_SETTLE_S", "0.6"))

    def _try_pass(where: str) -> str | None:
        code = _extract_code_below_beatbot_label_index(driver, 0)
        if code:
            print(f"    ✅ 步骤2: 验证码={code}（{where}，第1个 Beatbot 标题下方）")
            return code
        code = _extract_code_from_visible_page_text(driver)
        if code:
            print(f"    ✅ 步骤2: 验证码={code}（{where}，可见文本）")
            return code
        code = _scan_visible_six_digit_on_detail(driver)
        if code:
            print(f"    ✅ 步骤2: 验证码={code}（{where}，TextView 扫描）")
            return code
        return None

    _swipe_mail_detail_to_top(driver, max_swipes=3)
    time.sleep(settle)
    code = _try_pass("顶部")
    if code:
        return code

    _swipe_mail_detail_to_bottom(driver, max_swipes=5)
    time.sleep(settle)
    code = _try_pass("底部")
    if code:
        return code

    for desc, idx in (("第2个 Beatbot 标题附近", 1), ("最后一个 Beatbot 标题附近", -1)):
        code = _extract_code_below_beatbot_label_index(driver, idx)
        if code:
            print(f"    ✅ 步骤2: 验证码={code}（{desc}）")
            return code

    code = _extract_code_from_page_source(driver)
    if code:
        print(f"    ✅ 步骤2: 验证码={code}（page_source 正则）")
        return code

    raise TimeoutError(
        "详情页未读到 6 位验证码（已尝试顶部/底部可见文本与 Beatbot 标题）"
    )


def _open_latest_mail(
    driver, *, subject_contains: str, from_contains: Optional[str], timeout_s: int
) -> None:
    """
    打开最新 noreply 邮件（收件箱 → 详情页）：先快速点击，失败再列举兜底。
    """
    _ = subject_contains, timeout_s  # 保留参数兼容
    _recover_if_wrong_page(driver)
    if _fast_click_noreply_mail(driver, from_contains=from_contains):
        return
    try:
        _click_noreply_inbox_senders(driver, from_contains=from_contains)
    except Exception as e:
        raise TimeoutError(f"未能打开 noreply 邮件: {e}") from e


def _extract_code_from_opened_mail(driver, timeout_s: int = 20) -> str:
    """步骤2：详情页提取 6 位验证码（多策略 + 滑动后重试）。"""
    _ = timeout_s
    last_err: Exception | None = None
    for round_i in range(3):
        try:
            if round_i > 0:
                print(f"    🔁 详情页重新提取验证码（第 {round_i + 1} 次）...")
                _swipe_mail_detail_to_bottom(driver, max_swipes=3)
                time.sleep(0.5)
            return _extract_code_from_detail_page(driver)
        except Exception as e:
            last_err = e
    raise TimeoutError(f"详情页提取验证码失败: {last_err}") from last_err


def get_gmail_verification_code(
    *,
    driver=None,
    method: Optional[str] = None,
    subject_contains: str = "Beatbot Verification Code",
    from_contains: str | None = "noreply",
    timeout_s: int = 120,
    poll_interval_s: float = 3.0,
    gmail_bundle_id: str = "com.google.android.gm",
    kill_gmail_after: bool = True,
    return_app_package: str | None = None,
) -> str:
    """
    Android 版本：通过 Gmail App 获取最新 6 位验证码。

    - driver 必传（Appium WebDriver）
    - method 仅支持 app/auto（auto 等价 app）；若要 IMAP，请用原 `gmail_otp_utils_iOS验证码.py`
    - return_app_package: 获取验证码并 kill Gmail 后，自动切回的被测 App 包名（默认读 ANDROID_APP_PACKAGE）
    """
    m = (method or os.environ.get("GMAIL_CODE_METHOD", "app")).strip().lower()
    if m not in {"app", "auto"}:
        raise ValueError(f"Android Gmail util 不支持 method={m}（仅支持 app/auto）")
    if driver is None:
        raise RuntimeError("Android Gmail util 需要传入 driver（Appium WebDriver）")

    killed = False
    start_ts = time.time()
    last_err: Exception | None = None
    code: str | None = None

    try:
        # 进入 Gmail（部分机型安装的是 Gmail Go：com.google.android.gn）
        candidates = [gmail_bundle_id]
        if gmail_bundle_id == "com.google.android.gm":
            candidates.append("com.google.android.gn")
        elif gmail_bundle_id == "com.google.android.gn":
            candidates.append("com.google.android.gm")

        # 打开前冷启动：先 force-stop 再 activate，避免恢复到上次邮件详情页
        if kill_gmail_after:
            print("    🧊 打开 Gmail 前冷启动（force-stop 清除上次详情页状态）...")
            _force_stop_all_gmail_pkgs(driver, gmail_bundle_id=gmail_bundle_id)
            time.sleep(0.25)

        activated = False
        last_act_err: Exception | None = None
        for pkg in candidates:
            try:
                driver.activate_app(pkg)
                gmail_bundle_id = pkg  # 用于 finally 里 terminate
                activated = True
                break
            except Exception as e:
                last_act_err = e
        if not activated:
            raise RuntimeError(f"无法打开 Gmail: {candidates}, last={last_act_err}")

        t_open = time.time()
        _prepare_gmail_ui_ready(driver)
        _dismiss_popups(driver)
        _wait_noreply_inbox_ready(
            driver, GMAIL_INBOX_WAIT_S, from_contains=from_contains
        )

        open_timeout = int(os.environ.get("GMAIL_OPEN_MAIL_TIMEOUT_S", str(GMAIL_OPEN_MAIL_TIMEOUT_S)))
        extract_timeout = int(
            os.environ.get("GMAIL_EXTRACT_CODE_TIMEOUT_S", str(GMAIL_EXTRACT_CODE_TIMEOUT_S))
        )

        for attempt in range(2):
            try:
                if attempt > 0:
                    print(f"    🔁 重试打开 noreply（第 {attempt + 1} 次）...")
                t_click = time.time()
                _open_latest_mail(
                    driver,
                    subject_contains=subject_contains,
                    from_contains=from_contains,
                    timeout_s=open_timeout,
                )
                print(
                    f"    ⏱️ 打开 noreply 耗时 {time.time() - t_click:.1f}s "
                    f"（进入 Gmail 后累计 {time.time() - t_open:.1f}s）"
                )
                code = _extract_code_from_opened_mail(driver, timeout_s=extract_timeout)
                # 必须先 kill Gmail 再回 Beatbot，否则下次进 Gmail 仍在详情页
                if kill_gmail_after:
                    _kill_gmail_app(driver, gmail_bundle_id)
                    killed = True
                pkg = (return_app_package or os.environ.get("ANDROID_APP_PACKAGE") or "").strip()
                if pkg:
                    print(f"    🔄 切回被测 App: {pkg}")
                    try:
                        driver.activate_app(pkg)
                        time.sleep(1.2)
                    except Exception:
                        pass
                print(f"    ✅ 验证码已获取: {code}，Gmail 已关闭")
                return code
            except Exception as e:
                last_err = e
                if attempt == 0:
                    time.sleep(min(poll_interval_s, 1.5))
                    continue
                break

        raise TimeoutError(f"Android Gmail 获取验证码超时（最后错误: {last_err or 'unknown'}）")
    finally:
        # 失败时也 kill Gmail，避免卡在邮箱影响后续步骤
        if kill_gmail_after and not killed:
            _kill_gmail_app(driver, gmail_bundle_id)
            killed = True

        pkg = (return_app_package or os.environ.get("ANDROID_APP_PACKAGE") or "").strip()
        if pkg and not code:
            try:
                driver.activate_app(pkg)
                time.sleep(1.0)
            except Exception:
                pass

