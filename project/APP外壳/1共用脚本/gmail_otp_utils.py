"""
Gmail 验证码统一入口。

目的：
- 对外只暴露一个方法，测试用例无需关心验证码来自 IMAP 还是 Gmail App。

支持方式：
- imap: 通过 IMAP 读取 Gmail INBOX
- app : 通过 Appium 自动化 iOS Gmail App（需传入 Appium driver）
- auto: 优先 IMAP，失败则回退到 Gmail App（若提供 driver）

可通过环境变量控制默认策略：
- GMAIL_CODE_METHOD=auto|imap|app   （默认 auto）
"""

from __future__ import annotations

import imaplib
import os
import re
import time
from email import message_from_bytes
from email.header import decode_header, make_header
from typing import Optional, Tuple

from appium.webdriver.common.appiumby import AppiumBy


_CODE_RE = re.compile(r"\b(\d{6})\b")
_CODE_SPACED_RE = re.compile(r"(?<!\d)(\d{3})[\s\-]+(\d{3})(?!\d)")
_AUTH_FAILED_RE = re.compile(r"AUTHENTICATIONFAILED", re.IGNORECASE)


def _extract_codes_from_text(text: str) -> list[str]:
    """
    从文本中提取 6 位验证码。

    兼容两类常见展示：
    - 连续 6 位：123456
    - 分组/带分隔：123 456 / 123-456
    """
    if not text:
        return []
    s = str(text)
    out: list[str] = []
    for m in _CODE_RE.finditer(s):
        out.append(m.group(1))
    for m in _CODE_SPACED_RE.finditer(s):
        out.append(f"{m.group(1)}{m.group(2)}")
    return out


def _iter_visible_text_elements(driver):
    """
    Gmail iOS App 的正文元素类型不稳定：
    有时是 StaticText/TextView，有时会落在 Other/Link/Button。
    这里尽量覆盖常见承载文本的控件类型。
    """
    xps = (
        "//XCUIElementTypeStaticText",
        "//XCUIElementTypeTextView",
        "//XCUIElementTypeLink",
        "//XCUIElementTypeButton",
        "//XCUIElementTypeOther",
    )
    for xp in xps:
        try:
            elems = driver.find_elements(AppiumBy.XPATH, xp)
        except Exception:
            elems = []
        for e in elems:
            yield e


def _decode_mime_header(value: str | bytes | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        try:
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return str(value)


def _extract_text_from_email(msg) -> str:
    # 优先 text/plain，其次 text/html
    if msg.is_multipart():
        plain_parts = []
        html_parts = []
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                payload = None
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="ignore")
            except Exception:
                text = payload.decode("utf-8", errors="ignore")
            if ctype == "text/plain":
                plain_parts.append(text)
            elif ctype == "text/html":
                html_parts.append(text)
        return "\n".join(plain_parts) if plain_parts else "\n".join(html_parts)

    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="ignore")
    except Exception:
        return payload.decode("utf-8", errors="ignore")


def _read_gmail_creds() -> Tuple[str, str]:
    addr = os.environ.get("GMAIL_ADDRESS", "").strip()
    pwd = os.environ.get("GMAIL_PASSWORD", "").strip()
    if addr and pwd:
        return addr, pwd

    # fallback: 读取历史 constant.py
    try:
        from constant import email as _email, password as _password  # type: ignore

        addr = str(_email).strip()
        pwd = str(_password).strip()
        if addr and pwd:
            return addr, pwd
    except Exception:
        pass

    raise RuntimeError(
        "未配置 Gmail 凭据：请设置环境变量 GMAIL_ADDRESS/GMAIL_PASSWORD，或在 1共用脚本/constant.py 提供 email/password。"
    )


def _fetch_latest_verification_code_via_imap(
    *,
    subject_contains: str,
    from_contains: Optional[str],
    timeout_s: int,
    poll_interval_s: float,
    mailbox: str = "INBOX",
    unseen_only: bool = False,
) -> str:
    addr, pwd = _read_gmail_creds()
    deadline = time.time() + timeout_s
    last_err = None

    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
                imap.login(addr, pwd)
                imap.select(mailbox)

                criteria = []
                if unseen_only:
                    criteria.append("UNSEEN")
                if subject_contains:
                    criteria.append(f'SUBJECT "{subject_contains}"')
                if from_contains:
                    criteria.append(f'FROM "{from_contains}"')

                search_query = " ".join(criteria) if criteria else "ALL"
                status, data = imap.search(None, search_query)
                if status != "OK" or not data or not data[0]:
                    raise RuntimeError(f"IMAP search 无结果: {search_query}")

                ids = data[0].split()
                latest_id = ids[-1]
                status, msg_data = imap.fetch(latest_id, "(RFC822)")
                if status != "OK" or not msg_data:
                    raise RuntimeError("IMAP fetch 失败")

                raw = msg_data[0][1]
                msg = message_from_bytes(raw)
                subj = _decode_mime_header(msg.get("Subject"))
                body = _extract_text_from_email(msg)
                haystack = f"{subj}\n{body}"

                m = _CODE_RE.search(haystack)
                if not m:
                    raise RuntimeError("未在邮件内容中匹配到 6 位验证码")
                return m.group(1)
        except Exception as e:
            msg = ""
            try:
                msg = str(e)
            except Exception:
                msg = ""
            if _AUTH_FAILED_RE.search(msg):
                raise RuntimeError(
                    "Gmail IMAP 认证失败（AUTHENTICATIONFAILED）。\n"
                    "解决方式：\n"
                    "1) Gmail 账号开启两步验证（2FA）\n"
                    "2) 在 Google 账号里创建“应用专用密码”（App Password）\n"
                    "3) 将应用专用密码配置到环境变量 GMAIL_PASSWORD（推荐），或更新 1共用脚本/constant.py 的 password\n"
                    "4) 环境变量 GMAIL_ADDRESS 设置为实际 Gmail 地址\n"
                    "注：普通登录密码通常无法用于 IMAP。"
                ) from e
            last_err = e
            time.sleep(poll_interval_s)

    raise TimeoutError(f"超时仍未获取到验证码（最后错误: {last_err}）")


def _safe_tap(driver, elem):
    try:
        elem.click()
        return
    except Exception:
        rect = elem.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})


def _extract_code_from_visible_text(driver) -> Optional[str]:
    for e in _iter_visible_text_elements(driver):
        try:
            if not e.is_displayed():
                continue
            for attr in ("name", "label", "value"):
                v = e.get_attribute(attr) or ""
                codes = _extract_codes_from_text(str(v))
                if codes:
                    return codes[0]
        except Exception:
            continue
    return None


def _extract_all_codes_from_visible_text(driver) -> list[str]:
    """
    扫描当前可见文本中的所有 6 位验证码（按发现顺序）。
    用于“滑到底部取最新码”：我们最终会返回最后一个匹配到的验证码。
    """
    found: list[str] = []
    for e in _iter_visible_text_elements(driver):
        try:
            if not e.is_displayed():
                continue
            for attr in ("name", "label", "value"):
                v = e.get_attribute(attr) or ""
                found.extend(_extract_codes_from_text(str(v)))
        except Exception:
            continue
    return found


def _swipe_up(driver, *, velocity: int = 900) -> None:
    try:
        driver.execute_script("mobile: swipe", {"direction": "up", "velocity": velocity})
    except Exception:
        # 某些驱动不支持 velocity
        try:
            driver.execute_script("mobile: swipe", {"direction": "up"})
        except Exception:
            pass


def _visible_text_digest(driver) -> str:
    """
    轻量摘要：用于判断“滑动后页面内容是否变化”。
    """
    parts: list[str] = []
    for e in _iter_visible_text_elements(driver):
        try:
            if not e.is_displayed():
                continue
            for attr in ("name", "label", "value"):
                v = e.get_attribute(attr) or ""
                v = str(v).strip()
                if v:
                    parts.append(v)
        except Exception:
            continue
    # 限制长度 + 排序保证稳定性（digest 只是用于“是否变化”的判断，越轻越好）
    parts = parts[:35]
    parts_sorted = sorted(parts)
    return "|".join(parts_sorted)


def _scroll_to_bottom_and_extract_code(
    driver,
    *,
    max_swipes: int = 16,
    swipe_velocity: int = 900,
    pause_s: float = 0.35,
) -> Optional[str]:
    """
    邮件正文验证码可能在底部；这里反复向上滑动（页面向下滚动）直到接近底部，
    并返回“最后一次看到的验证码”（更接近底部/最新）。
    """
    # 先扫一遍当前可见区域（不要立刻返回，先收集，后面会取“最后一个”）
    seen_codes: list[str] = _extract_all_codes_from_visible_text(driver)

    last_digest: str | None = None
    unchanged_count = 0

    # 性能优化：
    # - 并不是每次滑动都做全文扫描/摘要（很慢）
    # - 采用“每隔几次滑动再扫描/摘要”，同时保留早停
    scan_every = 2
    digest_every = 3

    for i in range(max_swipes):
        _swipe_up(driver, velocity=swipe_velocity)
        time.sleep(pause_s)

        # 若连续多次滑动后可见内容摘要不变，认为接近底部/滑不动
        if i % digest_every == 0:
            try:
                digest = _visible_text_digest(driver)
                if last_digest is not None and digest == last_digest:
                    unchanged_count += 1
                else:
                    unchanged_count = 0
                last_digest = digest
                # 更激进早停：连续两次不变基本可判定到底（比 4 次快）
                if unchanged_count >= 2:
                    if i % scan_every != 0:
                        seen_codes.extend(_extract_all_codes_from_visible_text(driver))
                    return seen_codes[-1] if seen_codes else None
            except Exception:
                pass

        if i % scan_every == 0:
            seen_codes.extend(_extract_all_codes_from_visible_text(driver))

    # 滑动次数耗尽：返回最后一个验证码
    return seen_codes[-1] if seen_codes else None


def _swipe_three_times_and_extract_latest_code(driver) -> Optional[str]:
    """
    按固定步骤从 Gmail 详情页获取验证码：
    进入详情页后等待 2 秒 → 向上滑动 3 次（页面向下滚动）→ 提取“最新验证码”。
    提取方式与之前一致：扫描当前可见区域所有 6 位码，返回最后一个。
    """
    time.sleep(2.0)
    for _ in range(3):
        _swipe_up(driver, velocity=950)
        time.sleep(0.35)
    seen = _extract_all_codes_from_visible_text(driver)
    return seen[-1] if seen else None


def _fetch_latest_code_via_gmail_app(
    driver,
    *,
    gmail_bundle_id: str,
    sender_contains: Optional[str],
    subject_contains: str,
    max_wait_s: int,
    kill_gmail_after: bool,
) -> str:
    driver.activate_app(gmail_bundle_id)
    time.sleep(2.0)
    killed = False

    # 允许首次启动时弹窗（不强依赖）
    for _ in range(2):
        try:
            btns = driver.find_elements(
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Allow" or @name="OK" or @name="Continue" or @name="Not now" or @name="稍后" or @name="允许"]',
            )
            for b in btns:
                try:
                    if b.is_displayed():
                        _safe_tap(driver, b)
                        time.sleep(1)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    deadline = time.time() + max_wait_s
    last_err = None

    def _visible_mail_cells(min_count: int = 1) -> int:
        """
        粗略判断是否处于邮件列表页：可见 Cell 数量通常 > 0。
        """
        try:
            cells = driver.find_elements(AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeCell")
        except Exception:
            cells = []
        n = 0
        for c in cells:
            try:
                if c.is_displayed():
                    n += 1
                    if n >= min_count:
                        return n
            except Exception:
                continue
        return n

    def _is_detail_page() -> bool:
        """
        Gmail 详情页通常会出现返回按钮（Back/nav back）。
        """
        try:
            backs = driver.find_elements(
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Back" or @name="nav back" or @label="Back" or @label="nav back" or contains(@name,"Inbox") or contains(@label,"Inbox") or contains(@name,"收件箱") or contains(@label,"收件箱")]',
            )
            for b in backs:
                try:
                    if b.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _wait_enter_detail(timeout_s: float = 6.0) -> None:
        end = time.time() + timeout_s
        while time.time() < end:
            # 详情页应满足：有返回按钮且列表 cell 不再明显可见
            if _is_detail_page() and _visible_mail_cells(min_count=2) == 0:
                return
            time.sleep(0.25)
        # 不强制抛错：后续滚动/提取失败会进入重试

    try:
        while time.time() < deadline:
            try:
                # 关键修复：
                # - 列表页预览里也可能包含 6 位数字（会被误当验证码）
                # - 因此：只要检测到处于列表页（有可见邮件 Cell），就必须先点击 noreply 进入详情页
                # - 只有在“确认详情页”时，才允许滑动并提取验证码

                in_list = _visible_mail_cells(min_count=1) > 0
                in_detail = _is_detail_page() and _visible_mail_cells(min_count=2) == 0

                # 1) 如果已确认在详情页：滑到底部取最新验证码
                if in_detail:
                    code = _swipe_three_times_and_extract_latest_code(driver)
                    if code:
                        if kill_gmail_after and not killed:
                            try:
                                driver.terminate_app(gmail_bundle_id)
                                time.sleep(0.8)
                                killed = True
                            except Exception:
                                pass
                        return code

                # 2) 邮件列表页：优先点击 noreply + subject 的最新一封（通常在最上方）
                target = None
                if in_list and sender_contains:
                    # 快速路径：直接找包含 noreply 的第一封邮件 cell（通常就是最新）
                    try:
                        cells = driver.find_elements(
                            AppiumBy.XPATH,
                            f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[contains(@name,"{sender_contains}") or contains(@label,"{sender_contains}") or contains(@value,"{sender_contains}")]]',
                        )
                        for c in cells:
                            try:
                                if c.is_displayed():
                                    target = c
                                    break
                            except Exception:
                                continue
                    except Exception:
                        target = None

                    # 若找到多个 noreply，再尝试同 cell 内包含主题的（更准）
                    if target is None:
                        try:
                            cells = driver.find_elements(
                                AppiumBy.XPATH,
                                f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[contains(@name,"{sender_contains}") or contains(@label,"{sender_contains}") or contains(@value,"{sender_contains}")]]',
                            )
                            for cell in cells:
                                try:
                                    if not cell.is_displayed():
                                        continue
                                    subs = cell.find_elements(
                                        AppiumBy.XPATH,
                                        f'.//XCUIElementTypeStaticText[contains(@name,"{subject_contains}") or contains(@label,"{subject_contains}") or contains(@value,"{subject_contains}")]',
                                    )
                                    if subs:
                                        target = cell
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                if target is None:
                    # 没提供 sender_contains 或仍未命中：退化为主题匹配，再退化为首封
                    try:
                        candidates = driver.find_elements(
                            AppiumBy.XPATH,
                            f'//XCUIElementTypeStaticText[contains(@name,"{subject_contains}") or contains(@label,"{subject_contains}") or contains(@value,"{subject_contains}")]',
                        )
                        for c in candidates:
                            try:
                                if c.is_displayed():
                                    target = c
                                    break
                            except Exception:
                                continue
                    except Exception:
                        target = None

                if target is None:
                    cells = driver.find_elements(
                        AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeCell"
                    )
                    for cell in cells:
                        try:
                            if cell.is_displayed():
                                target = cell
                                break
                        except Exception:
                            continue

                if target is None:
                    raise RuntimeError("Gmail 列表未找到可点击的 noreply 邮件")

                _safe_tap(driver, target)
                _wait_enter_detail(timeout_s=6.0)
                time.sleep(0.8)

                # 3) 进入详情页：向上滑动到最底部后取最新验证码
                if _is_detail_page():
                    code = _swipe_three_times_and_extract_latest_code(driver)
                    if code:
                        if kill_gmail_after and not killed:
                            try:
                                driver.terminate_app(gmail_bundle_id)
                                time.sleep(0.8)
                                killed = True
                            except Exception:
                                pass
                        return code

                # 尝试返回列表
                try:
                    back_btns = driver.find_elements(
                        AppiumBy.XPATH,
                        '//XCUIElementTypeButton[@name="Back" or @name="nav back" or contains(@name,"Inbox") or contains(@label,"Inbox") or contains(@name,"收件箱") or contains(@label,"收件箱")]',
                    )
                    for b in back_btns:
                        try:
                            if b.is_displayed():
                                _safe_tap(driver, b)
                                time.sleep(1.0)
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

                last_err = RuntimeError("打开邮件但未提取到验证码")
                time.sleep(1.5)
            except Exception as e:
                last_err = e
                time.sleep(2.0)

        raise TimeoutError(f"Gmail App 获取验证码超时（最后错误: {last_err}）")
    finally:
        if kill_gmail_after and not killed:
            try:
                driver.terminate_app(gmail_bundle_id)
                time.sleep(0.8)
            except Exception:
                pass


def get_gmail_verification_code(
    *,
    driver=None,
    method: Optional[str] = None,
    subject_contains: str = "Beatbot Verification Code",
    from_contains: str | None = "noreply",
    timeout_s: int = 120,
    poll_interval_s: float = 3.0,
    gmail_bundle_id: str = "com.google.Gmail",
    kill_gmail_after: bool = True,
) -> str:
    """
    获取 Gmail 最新 6 位验证码。

    - **driver**: 当 method=app/auto 且需要走 Gmail App 时必须提供（Appium WebDriver）
    - **method**: auto|imap|app；不传则读取环境变量 `GMAIL_CODE_METHOD`，默认 auto
    """
    m = (method or os.environ.get("GMAIL_CODE_METHOD", "auto")).strip().lower()
    if m not in {"auto", "imap", "app"}:
        raise ValueError(f"不支持的 method: {m}（仅支持 auto/imap/app）")

    last_err: Exception | None = None

    def _via_imap() -> str:
        return _fetch_latest_verification_code_via_imap(
            subject_contains=subject_contains,
            from_contains=from_contains,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            unseen_only=False,
        )

    def _via_app() -> str:
        if driver is None:
            raise RuntimeError("method=app 需要传入 driver（Appium WebDriver）")
        return _fetch_latest_code_via_gmail_app(
            driver,
            gmail_bundle_id=gmail_bundle_id,
            sender_contains=from_contains,
            subject_contains=subject_contains,
            max_wait_s=timeout_s,
            kill_gmail_after=kill_gmail_after,
        )

    if m == "imap":
        return _via_imap()
    if m == "app":
        return _via_app()

    # auto: 先 IMAP，失败再回退 App
    try:
        return _via_imap()
    except Exception as e:
        last_err = e

    # IMAP 失败后，若提供 driver 则尝试 Gmail App
    try:
        return _via_app()
    except Exception as e:
        raise RuntimeError(f"auto 获取验证码失败：IMAP 失败({last_err})；Gmail App 也失败({e})") from e

