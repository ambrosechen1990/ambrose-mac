# -*- coding: utf-8 -*-
"""Playwright 控制 Yard Agent 页面。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import AgentReply
from .paths import AGENT_URL
from .style import strip_citations


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "未安装 playwright。请先执行:\n"
            "  pip install -r requirements.txt\n"
            "  playwright install chromium"
        ) from exc


class YardAgentClient:
    """控制浏览器与 Yard Agent 页面交互。"""

    def __init__(
        self,
        *,
        url: str = AGENT_URL,
        headed: bool = True,
        timeout_sec: float = 120.0,
        user_data_dir: Optional[str] = None,
        slow_mo_ms: int = 0,
    ):
        require_playwright()
        self.url = url
        self.headed = headed
        self.timeout_ms = int(timeout_sec * 1000)
        self.user_data_dir = user_data_dir
        self.slow_mo_ms = slow_mo_ms
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def _profile_busy_hint(self, exc: Exception) -> str:
        """浏览器配置目录被占用时，给出可操作的提示而不是一大段 Playwright 堆栈。"""
        text = str(exc)
        busy = "现有的浏览器会话" in text or "已在运行" in text or "TargetClosed" in type(exc).__name__
        if not busy:
            return f"启动浏览器失败: {text}"
        return (
            f"浏览器配置目录已被占用: {self.user_data_dir}\n"
            "同一个配置目录只能被一个浏览器实例使用。请任选一种处理：\n"
            "  1) 关掉已打开的测试浏览器窗口 / 等前一个脚本跑完，再重试\n"
            "  2) 想同时跑两个脚本，给本次指定独立配置目录，例如：\n"
            "       --user-data-dir .browser_profile_2\n"
            "     （新目录需要重新登录一次）"
        )

    def start(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch_args = {
            "headless": not self.headed,
            "slow_mo": self.slow_mo_ms,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self.user_data_dir:
            Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
            try:
                self._context = self._pw.chromium.launch_persistent_context(
                    self.user_data_dir,
                    **launch_args,
                    viewport={"width": 1440, "height": 960},
                )
            except Exception as exc:
                self.close()
                raise SystemExit(self._profile_busy_hint(exc)) from exc
            self._page = (
                self._context.pages[0] if self._context.pages else self._context.new_page()
            )
        else:
            self._browser = self._pw.chromium.launch(**launch_args)
            self._context = self._browser.new_context(viewport={"width": 1440, "height": 960})
            self._page = self._context.new_page()

        self._page.set_default_timeout(self.timeout_ms)
        self._page.goto(self.url, wait_until="domcontentloaded")
        self._wait_ready_or_login()

    def close(self):
        for obj in (self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._page = self._context = self._browser = self._pw = None

    def new_chat(self):
        page = self._page
        for sel in (
            page.get_by_role("button", name=re.compile("新建")),
            page.locator("button:has-text('新建')"),
            page.locator("text=新建"),
        ):
            try:
                if sel.count() > 0 and sel.first.is_visible():
                    sel.first.click(timeout=3000)
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                continue
        return False

    def _input_box(self):
        page = self._page
        candidates = [
            page.locator("#agent-message"),
            page.get_by_placeholder("输入问题或任务"),
            page.locator("textarea[placeholder*='输入问题']"),
            page.locator("textarea[placeholder*='Enter']"),
            page.locator("textarea").last,
        ]
        for loc in candidates:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        raise RuntimeError("未找到提问输入框。页面结构可能已变化。")

    def _is_input_enabled(self) -> bool:
        try:
            box = self._input_box()
            disabled = box.get_attribute("disabled")
            aria = box.get_attribute("aria-disabled")
            return disabled is None and aria not in {"true", "True"}
        except Exception:
            return False

    def _wait_generation_idle(self, timeout_sec: float = 90.0) -> bool:
        page = self._page
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            running = page.locator("text=/运行中|思考中|生成中|排队/").count() > 0
            if not running and self._is_input_enabled():
                return True
            page.wait_for_timeout(500)
        return self._is_input_enabled()

    def recover_composer(self) -> None:
        page = self._page
        print("  .. 输入框不可用，尝试恢复…")
        if self._wait_generation_idle(60):
            return
        if self.new_chat():
            page.wait_for_timeout(1200)
            if self._wait_generation_idle(30):
                return
        try:
            page.reload(wait_until="domcontentloaded")
            self._wait_ready_or_login()
            self.new_chat()
            page.wait_for_timeout(1000)
        except Exception as exc:
            print(f"  .. 刷新恢复失败: {exc}")
        self._wait_generation_idle(30)

    def _ensure_input_ready(self, timeout_sec: float = 45.0):
        page = self._page
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                box = self._input_box()
                if box.is_visible() and self._is_input_enabled():
                    return box
            except Exception:
                pass
            running = page.locator("text=/运行中|思考中|生成中|排队/").count() > 0
            if running:
                page.wait_for_timeout(800)
                continue
            self.recover_composer()
            try:
                box = self._input_box()
                if box.is_visible() and self._is_input_enabled():
                    return box
            except Exception:
                pass
            page.wait_for_timeout(500)
        self.recover_composer()
        box = self._input_box()
        if not self._is_input_enabled():
            raise RuntimeError("提问输入框仍为 disabled，无法发送（会话可能卡住或限流）。")
        return box

    def _select_language(self, language: str) -> bool:
        """选择回答语言。标签形如「English en-US」，需兼容精确与包含匹配。"""
        language = (language or "").strip()
        if not language:
            return False
        page = self._page
        candidates = [
            page.get_by_text(language, exact=True),
            page.get_by_role("radio", name=re.compile(re.escape(language), re.I)),
            page.locator(f"label:has-text('{language}')"),
            page.get_by_text(re.compile(rf"^{re.escape(language)}\b", re.I)),
        ]
        for loc in candidates:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=2000)
                    return True
            except Exception:
                continue
        return False

    def _send_button(self):
        page = self._page
        for loc in (
            page.get_by_role("button", name="发送"),
            page.locator("button:has-text('发送')"),
            page.locator("[aria-label*='发送']"),
        ):
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        return None

    def _wait_ready_or_login(self):
        page = self._page
        deadline = time.time() + max(self.timeout_ms / 1000.0, 60)
        while time.time() < deadline:
            try:
                if self._input_box().is_visible():
                    return
            except Exception:
                pass
            login_hint = page.locator("text=/登录|Login|Sign in|SSO/i")
            if login_hint.count() > 0 and self.headed:
                print("检测到需要登录。请在浏览器中完成登录，脚本会自动继续…")
                try:
                    page.wait_for_selector(
                        "textarea[placeholder*='输入问题'], textarea[placeholder*='Enter']",
                        timeout=300_000,
                    )
                    return
                except Exception:
                    continue
            page.wait_for_timeout(800)
        raise TimeoutError(
            f"打开 {self.url} 后未能进入可提问状态。"
            "请登录后重试，或使用 --user-data-dir 保存登录态。"
        )

    def _composer_text(self) -> str:
        try:
            return (self._input_box().input_value(timeout=2000) or "").strip()
        except Exception:
            return ""

    def _submission_started(self, before_answer: str, timeout_sec: float = 10.0) -> bool:
        """判断问题是否真的提交出去了：输入框清空/置灰、开始生成、或答案已变。"""
        page = self._page
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if page.locator("text=/运行中|思考中|生成中|排队/").count() > 0:
                return True
            if not self._is_input_enabled():
                return True
            if not self._composer_text():
                return True
            answer = self._latest_agent_answer()
            if answer and answer != (before_answer or "").strip():
                return True
            page.wait_for_timeout(400)
        return False

    def _submit(self, question: str, before_answer: str) -> None:
        """填入并发送问题；点击有时不生效，确认没发出去就重发。"""
        for attempt in range(1, 4):
            box = self._ensure_input_ready()
            box.click(timeout=10_000)
            box.fill("")
            box.fill(question)

            send = self._send_button()
            if send is not None:
                try:
                    send.click(timeout=10_000)
                except Exception:
                    box.press("Enter")
            else:
                box.press("Enter")

            if self._submission_started(before_answer):
                return
            print(f"  .. 问题似乎没发出去，重发 {attempt}/3…")
        raise RuntimeError("连续 3 次发送后页面无反应（输入框未清空，也未开始生成）。")

    def ask(self, question: str, *, language: str = "中文") -> AgentReply:
        # 原样发送用户问题，不附加任何提示词，保持与真人提问一致
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空")
        if len(question) > 4000:
            raise ValueError("问题超过 4000 字符限制")

        before_count = self._count_completed_replies()
        before_answer = self._latest_agent_answer()
        before_bubbles = self._count_agent_bubbles()

        self._select_language(language)

        t0 = time.time()
        self._submit(question, before_answer)

        answer, status, blocks = self._wait_for_answer(
            before_count, before_answer, before_bubbles
        )
        answer = strip_citations(answer)
        return AgentReply(
            question=question,
            answer=answer,
            status=status,
            elapsed_sec=round(time.time() - t0, 2),
            raw_blocks=blocks,
            date=datetime.now().strftime("%Y/%m/%d"),
        )

    def screenshot(self, path: Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(path), full_page=False)
        return str(path.resolve())

    def _count_agent_bubbles(self) -> int:
        try:
            return self._agent_message_locators().count()
        except Exception:
            return 0

    def _count_completed_replies(self) -> int:
        try:
            return self._page.locator("text=已完成").count()
        except Exception:
            return 0

    def _agent_message_locators(self):
        page = self._page
        loc = page.locator(
            "xpath=(//*[contains(normalize-space(.), 'Yard Agent')]"
            "/ancestor::*[self::article or self::section "
            "or (self::div and (contains(@class,'message') "
            "or contains(@class,'bubble') "
            "or contains(@class,'chat') "
            "or contains(@class,'agent')))][1])"
        )
        if loc.count() == 0:
            loc = page.locator(
                "xpath=(//*[contains(normalize-space(.), 'Yard Agent')]"
                "/ancestor::*[self::article or self::div][1])"
            )
        return loc

    def _clean_agent_text(self, t: str) -> str:
        cleaned = t
        for noise in ("Yard Agent", "已完成", "运行中", "思考中", "生成中", "排队", "发送", "复制", "重试"):
            cleaned = cleaned.replace(noise, "")
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    def _latest_agent_blocks(self) -> list[str]:
        page = self._page
        texts: list[str] = []
        loc = self._agent_message_locators()
        n = loc.count()
        start = max(0, n - 8)
        seen: set[str] = set()
        for i in range(start, n):
            try:
                t = loc.nth(i).inner_text(timeout=2000).strip()
            except Exception:
                continue
            if not t or "Yard Agent" not in t:
                continue
            cleaned = self._clean_agent_text(t)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                texts.append(cleaned)
        if texts:
            return texts

        main = page.locator("main, [class*='chat'], [class*='message'], [class*='conversation']")
        if main.count() == 0:
            main = page.locator("body")
        try:
            blob = main.last.inner_text(timeout=3000)
        except Exception:
            blob = page.inner_text("body")
        parts = [p.strip() for p in blob.split("\n\n") if p.strip()]
        return parts[-3:] if parts else []

    def _latest_agent_answer(self) -> str:
        blocks = self._latest_agent_blocks()
        return blocks[-1].strip() if blocks else ""

    def _new_bubble_answer(self, before_bubbles: int) -> str:
        """只读提问之后新增的那些气泡，避免把上一题的答案当成本题的。

        新气泡刚出现时内容为空，这时返回空串，等它生成出文字为止。
        """
        loc = self._agent_message_locators()
        n = loc.count()
        if n <= before_bubbles:
            return ""
        answer = ""
        for i in range(max(before_bubbles, n - 8), n):
            try:
                t = loc.nth(i).inner_text(timeout=2000).strip()
            except Exception:
                continue
            if "Yard Agent" not in t:
                continue
            cleaned = self._clean_agent_text(t)
            if cleaned:
                answer = cleaned
        return answer

    def _wait_for_answer(
        self, before_completed: int, before_answer: str = "", before_bubbles: int = -1
    ) -> tuple[str, str, list[str]]:
        page = self._page
        started = time.time()
        deadline = started + self.timeout_ms / 1000.0
        last_blocks: list[str] = []
        stable_hits = 0
        last_fingerprint = ""
        saw_running = False
        last_tick = started

        while time.time() < deadline:
            completed = self._count_completed_replies()
            if before_bubbles >= 0:
                # 按气泡位置取本题的答案：既不会拿到上一题的内容，
                # 也不怕两题答案文字恰好一样
                answer = self._new_bubble_answer(before_bubbles)
                is_new = bool(answer)
                if answer:
                    last_blocks = [answer]
            else:
                blocks = self._latest_agent_blocks()
                if blocks:
                    last_blocks = blocks
                answer = blocks[-1].strip() if blocks else ""
                is_new = bool(answer) and answer != (before_answer or "").strip()
            fingerprint = answer
            running = page.locator("text=/运行中|思考中|生成中|排队/").count() > 0
            if running:
                saw_running = True

            if is_new and fingerprint == last_fingerprint:
                stable_hits += 1
            else:
                stable_hits = 0
            last_fingerprint = fingerprint

            # 短回复（如「好的，已为您开启清洁」）也要能收尾，只是多观察几轮
            need_hits = 3 if len(fingerprint) > 20 else 6
            # 输入框恢复可用是生成结束的直接信号；短快回复可能在两次轮询之间就跑完，
            # 此时 saw_running 一直为假，不能只依赖它
            idle = not running and self._is_input_enabled()

            completed_ok = completed > before_completed and is_new
            stable_ok = is_new and (
                (idle and stable_hits >= need_hits)
                or (saw_running and stable_hits >= need_hits + 4)
            )

            if (completed_ok or stable_ok) and not running:
                status = "已完成" if completed_ok else "已稳定"
                return answer, status, last_blocks

            # 页面已空闲却拿不到新答案，说明这题要么没发出去、要么抓取有问题，
            # 没必要耗满整个 timeout
            waited = time.time() - started
            if idle and not is_new and waited > (60 if saw_running else 45):
                raise TimeoutError(
                    f"等待 {int(waited)}s 后页面已空闲，仍未取到本题的新回复。"
                )

            if time.time() - last_tick >= 20:
                last_tick = time.time()
                print(
                    f"  .. 仍在等待（{int(time.time() - started)}s "
                    f"运行中={running} 输入框可用={idle} "
                    f"新答案={is_new} 稳定轮次={stable_hits}/{need_hits}）"
                )
            page.wait_for_timeout(800)

        answer = last_blocks[-1].strip() if last_blocks else ""
        if not answer or (before_bubbles < 0 and answer == (before_answer or "").strip()):
            raise TimeoutError("等待 Yard Agent 新回复超时（未捕获到本题的答案）。")
        return answer, "超时截取", last_blocks
