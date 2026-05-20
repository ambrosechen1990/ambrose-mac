# 一次性：从 102148 抽出助手代码并生成独立用例脚本；执行后可删除本文件
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC148 = ROOT / '102148验证密码等于6个字符时，“完成”按钮可点击.py'

MARK_FIXTURE = '@pytest.fixture(scope="function")'
MARK_TEST = "\ndef test_102148"

EXTRA_HELPERS = '''

def _assert_submit_disabled_or_no_effect(driver):
    """Submit 不可点击或点击后仍停留在 Set Password 页。"""
    btn = _find_submit_button(driver, timeout_s=12)
    try:
        enabled = btn.is_enabled()
    except Exception:
        enabled = True
    if enabled is False:
        return
    try:
        btn.click()
    except Exception:
        rect = btn.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    time.sleep(1.2)
    _assert_on_set_password_page(driver, timeout_s=8)


def _check_password_rules(driver, expectations: Dict[str, str]):
    for rule_text, expect_color in expectations.items():
        sel = f'//XCUIElementTypeStaticText[@name="{rule_text}"]'
        rule_elem = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, sel))
        )
        assert rule_elem.is_displayed(), f"规则提示未显示: {rule_text}"
        color_val = None
        if hasattr(rule_elem, "value_of_css_property"):
            try:
                color_val = rule_elem.value_of_css_property("color")
            except Exception:
                color_val = None
        print(f"📝 规则提示: {rule_text} 颜色: {color_val}")
        if color_val:
            low = color_val.lower()
            if expect_color == "red":
                assert ("255" in color_val or "#ff" in low or "red" in low), f"期望红色但实际为 {color_val}"
            else:
                assert (
                    "128" in color_val or "gray" in low or "grey" in low or "#8" in low
                ), f"期望灰色但实际为 {color_val}"


def _click_acknowledge_after_failure(driver) -> bool:
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="知道了"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="知道了"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Confirm")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="OK"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Ok"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="好的"]'),
    ]
    for by, sel in selectors:
        try:
            btn = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, sel)))
            if btn and btn.is_displayed():
                try:
                    btn.click()
                except Exception:
                    rect = btn.rect or {}
                    tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
                    tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
                    driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
                time.sleep(0.8)
                return True
        except Exception:
            continue
    return False
'''


def _find_submit_button_patch(src: str) -> str:
    """102148 无 _find_submit_button：从共用逻辑补充（若已有则跳过）。"""
    if "def _find_submit_button" in src:
        return src
    insert_after = "def _find_password_fields(driver, timeout_s: int = 12):"
    if insert_after not in src:
        return src + "\n" + _FIND_SUBMIT_FN
    # 在 _find_password_fields 函数块之后插入（简化：插在 _assert_submit_enabled 之前）
    anchor = "def _assert_submit_enabled_and_success"
    if anchor in src:
        return src.replace(anchor, _FIND_SUBMIT_FN + "\n\n\n" + anchor)
    return src + "\n" + _FIND_SUBMIT_FN


_FIND_SUBMIT_FN = '''
def _find_submit_button(driver, timeout_s: int = 12):
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="Done"]'),
    ]
    last_err = None
    for by, sel in selectors:
        try:
            e = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((by, sel))
            )
            if e and e.is_displayed():
                return e
        except Exception as ex:
            last_err = ex
            continue
    raise TimeoutException(f"未找到Submit/完成按钮: {last_err}")
'''


def load_base_blocks() -> tuple[str, str, str]:
    raw = SRC148.read_text(encoding="utf-8")
    if MARK_FIXTURE not in raw:
        raise RuntimeError("102148 中未找到 fixture 标记")
    head, _, tail = raw.partition(MARK_FIXTURE)
    head = head.rstrip()
    if "from typing import Dict" not in head:
        head = head.replace(
            "from pathlib import Path\n",
            "from pathlib import Path\nfrom typing import Dict\n",
            1,
        )
    head = _find_submit_button_patch(head)
    helpers = head + EXTRA_HELPERS + "\n"
    fixture_body, _, _ = tail.partition(MARK_TEST)
    fixture_block = MARK_FIXTURE + fixture_body
    return helpers, fixture_block, raw


FORGET_STEPS = """
        current_step = "步骤1: 重启APP并处理登录状态"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        if _is_logged_in(driver):
            check_and_logout(driver)
            time.sleep(2)
        _assert_on_login_landing(driver, timeout=12)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 点击Sign In进入登录页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Sign In")]'),
            ],
            timeout_each=8,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击Forgot password进入忘记密码页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[contains(@name,"Forgot password")]'),
            ],
            timeout_each=10,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 输入邮箱并点击Next进入验证码页"
        print(f"🔄 {current_step}")
        _type_email(driver, email_value, timeout=12)
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
            ],
            timeout_each=10,
        )
        _assert_on_verification_page(driver, timeout=18)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成，邮箱: {email_value}")

        current_step = "步骤5: Gmail获取最新验证码code"
        print(f"🔄 {current_step}")
        code = get_gmail_verification_code(
            driver=driver,
            method=os.environ.get("GMAIL_CODE_METHOD", "app"),
            subject_contains=os.environ.get(
                "GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"
            ),
            from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
            timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S", "90")),
            gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.Gmail"),
            kill_gmail_after=True,
        )
        driver.activate_app(beatbot_bundle_id)
        time.sleep(2.0)
        print(f"✅ {current_step} - 完成，code: {code}")

        current_step = "步骤6: 输入验证码进入Set Password页"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, code, timeout=12)
        _assert_on_set_password_page(
            driver, timeout_s=int(os.environ.get("SET_PASSWORD_TIMEOUT_S", "20"))
        )
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")
"""

MAIN_TAIL = """

if __name__ == "__main__":
    pytest.main(["-s", __file__])
"""


def write_rule_cases(helpers: str, fixture_block: str) -> None:
    cases = [
        ("102149", "102149 验证密码等于20个字符时，“完成”按钮可点击", "Csx1234567Csx1234567", None, True, "步骤7: 输入20位密码(两次)并收起键盘"),
        ("102150", "102150 验证密码为纯数字时，“完成”按钮不可点击", "123456", {"• 6-20 characters": "gray", "• contains letters": "red", "• contains numbers": "gray", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入纯数字密码(两次)并收起键盘"),
        ("102151", "102151 验证密码为纯小写字母时，“完成”按钮不可点击", "xingmai", {"• 6-20 characters": "gray", "• contains letters": "gray", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入纯小写字母密码(两次)并收起键盘"),
        ("102152", "102152 验证密码为纯大写字母时，“完成”按钮不可点击", "XINGMAI", {"• 6-20 characters": "gray", "• contains letters": "gray", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入纯大写字母密码(两次)并收起键盘"),
        ("102153", "102153 验证密码为纯字符时，“完成”按钮不可点击", "!@#$%^&*()-==+\\'l[};:/?...~><`", {"• 6-20 characters": "gray", "• contains letters": "red", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入纯特殊字符密码(两次)并收起键盘"),
        ("102154", "102154 验证密码为数字+小写字母时，“完成”按钮可点击", "xingmai123456", None, True, "步骤7: 输入数字+小写字母密码(两次)并收起键盘"),
        ("102155", "102155 验证密码为数字+大写字母时，“完成”按钮可点击", "XINGMAI123456", None, True, "步骤7: 输入数字+大写字母密码(两次)并收起键盘"),
        ("102156", "102156 验证密码为数字+大+小写字母+字符时，“完成”按钮可点击", "XINGmai12?", None, True, "步骤7: 输入数字+大小写+特殊字符密码(两次)并收起键盘"),
        ("102157", "102157 验证密码为数字+字符时，“完成”按钮不可点击", "!@#$%^&*()-==+\\'l[};:/?...~><`12", {"• 6-20 characters": "gray", "• contains letters": "red", "• contains numbers": "gray", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入数字+特殊字符密码(两次)并收起键盘"),
        ("102158", "102158 验证密码为小写+大写字母时，“完成”按钮不可点击", "XINGmai", {"• 6-20 characters": "gray", "• contains letters": "gray", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入大小写字母混合密码(两次)并收起键盘"),
        ("102159", "102159 验证密码为小写字母+字符时，“完成”按钮不可点击", "!@#&xingmai", {"• 6-20 characters": "gray", "• contains letters": "gray", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入小写字母+特殊字符密码(两次)并收起键盘"),
        ("102160", "102160 验证密码为大写字母+字符时，“完成”按钮不可点击", "!@#*XINGMAI", {"• 6-20 characters": "gray", "• contains letters": "gray", "• contains numbers": "red", "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `": "gray"}, False, "步骤7: 输入大写字母+特殊字符密码(两次)并收起键盘"),
    ]

    for cid, desc, pwd, exp, succeed, step7 in cases:
        pwd_lit = repr(pwd)
        if exp is None:
            exp_lines = "    expectations = None  # 本用例不校验规则颜色"
        else:
            exp_lines = "    expectations = {\n" + "".join(f'        "{k}": "{v}",\n' for k, v in exp.items()) + "    }"

        if succeed:
            after = f'''
        current_step = "步骤8: 点击Submit/完成并断言可提交成功"
        print(f"🔄 {{current_step}}")
        _assert_submit_enabled_and_success(
            driver, timeout_s=int(os.environ.get("SUBMIT_SUCCESS_TIMEOUT_S", "20"))
        )
        print(f"✅ {{current_step}} - 完成")

        print("🎉 测试用例{cid}执行成功！")
'''
        else:
            after = f'''
        current_step = "步骤8: 校验密码规则文案颜色（若能取到color）"
        print(f"🔄 {{current_step}}")
        _check_password_rules(driver, expectations)
        print(f"✅ {{current_step}} - 完成")

        current_step = "步骤9: 点击Submit，断言不可完成修改密码（仍停留Set Password页）"
        print(f"🔄 {{current_step}}")
        _assert_submit_disabled_or_no_effect(driver)
        print(f"✅ {{current_step}} - 完成")

        print("🎉 测试用例{cid}执行成功！")
'''

        test_fn = f'''
def test_{cid}(setup_driver):
    """
    {desc}
    忘记密码链路；本文件自包含步骤与代码，不导入 forgot_password_set_password_common。
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    password_value = os.environ.get("TEST_PASSWORD", {pwd_lit})
{exp_lines}

    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")

    try:
{FORGET_STEPS}

        current_step = "{step7}"
        print(f"🔄 {{current_step}}")
        pwd1, pwd2 = _find_password_fields(driver, timeout_s=12)
        for f in (pwd1, pwd2):
            try:
                f.click()
                f.clear()
            except Exception:
                pass
            f.send_keys(password_value)
            time.sleep(0.5)
        _dismiss_keyboard(driver)
        print(f"✅ {{current_step}} - 完成，password: {{password_value}}")
{after}

    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{{current_step}}失败"
        print(f"\\n{{'=' * 60}}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {{current_step}}")
        print(f"📝 失败原因: {{fail_reason}}")
        print(f"{{'=' * 60}}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_{cid}_failed")
        assert False, f"测试失败 - {{fail_reason}}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="{cid}",
            case_desc={repr(desc)},
            result=case_result,
            fail_reason=fail_reason,
        )
'''

        path = next(ROOT.glob(f"{cid}*.py"))
        path.write_text(helpers + fixture_block + test_fn + MAIN_TAIL, encoding="utf-8")
        print("OK", path.name)


def write_special(helpers: str, fixture_block: str) -> None:
    # 102161
    p161 = next(ROOT.glob("102161*.py"))
    p161.write_text(
        helpers
        + fixture_block
        + '''
def test_102161(setup_driver):
    """102161 一键×清空密码（忘记密码链路；本文件自包含）"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd = os.environ.get("CLEAR_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 两次输入同一密码以显示清除按钮"
        print(f"🔄 {current_step}")
        pwd1, pwd2 = _find_password_fields(driver, timeout_s=12)
        for f in (pwd1, pwd2):
            try:
                f.click()
                f.clear()
            except Exception:
                pass
            f.send_keys(pwd)
            time.sleep(0.5)
        _dismiss_keyboard(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 点击 login delete 清除"
        print(f"🔄 {current_step}")
        delete_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login delete"]'))
        )
        delete_btn.click()
        time.sleep(1.0)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤9: 断言密码框已清空"
        print(f"🔄 {current_step}")
        pwd_input_after, _ = _find_password_fields(driver, timeout_s=10)
        value_after = pwd_input_after.get_attribute("value") or ""
        print(f"📝 清除后密码框内容: '{value_after}'")
        assert value_after in ["", "Password", None], f"清除后密码应为空/占位，当前值: '{value_after}'"
        print(f"✅ {current_step} - 完成")
        print("🎉 测试用例102161执行成功！")
    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败"
        print(f"\\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102161_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102161",
            case_desc='102161 验证输入的密码，可以一键“×”清空',
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p161.name)

    # 102162
    p162 = next(ROOT.glob("102162*.py"))
    p162.write_text(
        helpers
        + fixture_block
        + '''
def test_102162(setup_driver):
    """102162 默认密文"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd = os.environ.get("MASK_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 输入密码并断言默认密文"
        print(f"🔄 {current_step}")
        pwd1, _ = _find_password_fields(driver, timeout_s=12)
        try:
            pwd1.click()
            pwd1.clear()
        except Exception:
            pass
        pwd1.send_keys(pwd)
        time.sleep(1.0)
        default_type = pwd1.get_attribute("type") or ""
        default_value = pwd1.get_attribute("value") or ""
        print(f"📝 默认状态 value: '{default_value}', type: '{default_type}'")
        assert "SecureTextField" in default_type, "默认应为密文输入框"
        assert default_value != pwd, "默认状态不应展示明文"
        print(f"✅ {current_step} - 完成")
        print("🎉 测试用例102162执行成功！")
    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102162_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102162",
            case_desc="102162 验证密码默认密文",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p162.name)

    # 102163 can明文
    p163a = next(ROOT.glob("102163验证密码可以明文*.py"))
    p163a.write_text(
        helpers
        + fixture_block
        + '''
def test_102163(setup_driver):
    """102163 密码可明文"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd = os.environ.get("SHOW_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 点击眼睛显示明文"
        print(f"🔄 {current_step}")
        pwd1, _ = _find_password_fields(driver, timeout_s=12)
        try:
            pwd1.click()
            pwd1.clear()
        except Exception:
            pass
        pwd1.send_keys(pwd)
        time.sleep(1.0)
        show_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login pwd hide"]'))
        )
        show_btn.click()
        time.sleep(1.0)
        plain_password_input = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeTextField[1]"))
        )
        value_plain = plain_password_input.get_attribute("value") or ""
        assert value_plain == pwd, f"明文不符: '{value_plain}'"
        print(f"✅ {current_step} - 完成")
        print("🎉 测试用例102163执行成功！")
    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102163_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102163",
            case_desc="102163 验证密码可以明文",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p163a.name)

    p163b = next(ROOT.glob("102163验证密码明文显示*.py"))
    p163b.write_text(
        helpers
        + fixture_block
        + '''
def test_102163_plain_display(setup_driver):
    """102163 明文显示（独立脚本）"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd = os.environ.get("SHOW_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 点击眼睛显示明文"
        print(f"🔄 {current_step}")
        pwd1, _ = _find_password_fields(driver, timeout_s=12)
        try:
            pwd1.click()
            pwd1.clear()
        except Exception:
            pass
        pwd1.send_keys(pwd)
        time.sleep(1.0)
        show_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login pwd hide"]'))
        )
        show_btn.click()
        time.sleep(1.0)
        plain_password_input = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeTextField[1]"))
        )
        value_plain = plain_password_input.get_attribute("value") or ""
        assert value_plain == pwd
        print("🎉 测试用例102163(明文显示)成功")
    except Exception:
        case_result = "failed"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102163_plain_failed")
        assert False
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102163",
            case_desc="102163 验证密码明文显示",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p163b.name)

    # 102164
    p164 = next(ROOT.glob("102164*.py"))
    p164.write_text(
        helpers
        + fixture_block
        + '''
def test_102164(setup_driver):
    """102164 明文后再隐藏"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd = os.environ.get("SHOW_HIDE_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 明文后再次隐藏"
        print(f"🔄 {current_step}")
        pwd1, _ = _find_password_fields(driver, timeout_s=12)
        try:
            pwd1.click()
            pwd1.clear()
        except Exception:
            pass
        pwd1.send_keys(pwd)
        time.sleep(1.0)
        show_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login pwd hide"]'))
        )
        show_btn.click()
        time.sleep(1.0)
        plain_password_input = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeTextField[1]"))
        )
        assert (plain_password_input.get_attribute("value") or "") == pwd
        show_btn.click()
        time.sleep(1.0)
        secure_password_input_after = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeSecureTextField[1]"))
        )
        field_type_hidden = secure_password_input_after.get_attribute("type") or ""
        value_hidden = secure_password_input_after.get_attribute("value") or ""
        assert "SecureTextField" in field_type_hidden
        assert value_hidden != pwd
        print("🎉 测试用例102164执行成功！")
    except Exception:
        case_result = "failed"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102164_failed")
        assert False
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102164",
            case_desc="102164 验证密码明文后，可以再次隐藏",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p164.name)

    # 102165
    p165 = next(ROOT.glob("102165*.py"))
    p165.write_text(
        helpers
        + fixture_block
        + '''
def test_102165(setup_driver):
    """102165 失败后点知道了"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd1_val = os.environ.get("FAIL_PWD1", "Csx150128")
    pwd2_val = os.environ.get("FAIL_PWD2", "Csx150129")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = "步骤7: 两次不同密码并Submit"
        print(f"🔄 {current_step}")
        f1, f2 = _find_password_fields(driver, timeout_s=12)
        for field, val in ((f1, pwd1_val), (f2, pwd2_val)):
            try:
                field.click()
                field.clear()
            except Exception:
                pass
            field.send_keys(val)
            time.sleep(0.5)
        _dismiss_keyboard(driver)
        btn = _find_submit_button(driver, timeout_s=12)
        try:
            btn.click()
        except Exception:
            rect = btn.rect or {}
            driver.execute_script(
                "mobile: tap",
                {"x": int(rect.get("x", 0) + rect.get("width", 0) / 2), "y": int(rect.get("y", 0) + rect.get("height", 0) / 2)},
            )
        time.sleep(1.5)
        _click_acknowledge_after_failure(driver)
        _assert_on_set_password_page(driver, timeout_s=10)
        pwd_a, pwd_b = _find_password_fields(driver, timeout_s=10)
        assert pwd_a.is_displayed() and pwd_b.is_displayed()
        print("🎉 测试用例102165执行成功！")
    except Exception:
        case_result = "failed"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102165_failed")
        assert False
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102165",
            case_desc="102165 验证密码更换失败后，点击知道了",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p165.name)

    # 102166
    p166 = next(ROOT.glob("102166*.py"))
    p166.write_text(
        helpers
        + fixture_block
        + '''
def test_102166(setup_driver):
    """102166 验证码后等待超5分钟"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    wait_s = int(os.environ.get("WAIT_AFTER_CODE_S", "310"))
    ok_pwd = os.environ.get("EXPIRE_OK_PASSWORD", "Csx150128")
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
    try:
'''
        + FORGET_STEPS
        + '''
        current_step = f"步骤7: 等待超过5分钟（{wait_s}s）"
        print(f"🔄 {current_step}")
        time.sleep(wait_s)
        current_step = "步骤8: 输入密码并Submit（预期无法完成）"
        print(f"🔄 {current_step}")
        f1, f2 = _find_password_fields(driver, timeout_s=12)
        for field in (f1, f2):
            try:
                field.click()
                field.clear()
            except Exception:
                pass
            field.send_keys(ok_pwd)
            time.sleep(0.5)
        _dismiss_keyboard(driver)
        btn = _find_submit_button(driver, timeout_s=12)
        try:
            btn.click()
        except Exception:
            rect = btn.rect or {}
            driver.execute_script(
                "mobile: tap",
                {"x": int(rect.get("x", 0) + rect.get("width", 0) / 2), "y": int(rect.get("y", 0) + rect.get("height", 0) / 2)},
            )
        time.sleep(2.0)
        _click_acknowledge_after_failure(driver)
        _assert_on_set_password_page(driver, timeout_s=10)
        pwd_a, pwd_b = _find_password_fields(driver, timeout_s=10)
        assert pwd_a.is_displayed() and pwd_b.is_displayed()
        print("🎉 测试用例102166执行成功！")
    except Exception:
        case_result = "failed"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102166_failed")
        assert False
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102166",
            case_desc="102166 验证输入验证码后超过5min再输入密码，不可以完成修改密码",
            result=case_result,
            fail_reason=fail_reason,
        )
'''
        + MAIN_TAIL,
        encoding="utf-8",
    )
    print("OK", p166.name)


def main() -> None:
    helpers, fixture_block, _ = load_base_blocks()
    write_rule_cases(helpers, fixture_block)
    write_special(helpers, fixture_block)


if __name__ == "__main__":
    main()
