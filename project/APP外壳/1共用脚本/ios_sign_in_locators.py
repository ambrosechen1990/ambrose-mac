# -*- coding: utf-8 -*-
"""
iOS Sign in 页：邮箱 / 密码输入区域 XPath（Appium Inspector 采集）。

说明：真机上「可输入」有时是容器 Other，有时是子节点 TextField/SecureTextField；
实际定位请优先用 ios_sign_in_helpers.resolve_sign_in_email_input / resolve_sign_in_password_input。
"""

# 邮箱区域（容器）
IOS_SIGN_IN_EMAIL_CONTAINER_XPATH = (
    "//XCUIElementTypeWindow/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/"
    "XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther[1]/"
    "XCUIElementTypeOther[1]"
)

# 密码区域（容器）
IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH = (
    "//XCUIElementTypeWindow/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/"
    "XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther[1]/"
    "XCUIElementTypeOther[2]"
)

# 容器内常见子节点
IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH = IOS_SIGN_IN_EMAIL_CONTAINER_XPATH + "//XCUIElementTypeTextField"
IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH = IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH + "//XCUIElementTypeSecureTextField"
IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH = IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH + "//XCUIElementTypeTextField"

# 右侧操作按钮
IOS_SIGN_IN_EMAIL_CLEAR_BUTTON_XPATH = '(//XCUIElementTypeButton[@name="login delete"])[1]'
IOS_SIGN_IN_PASSWORD_CLEAR_BUTTON_XPATH = '(//XCUIElementTypeButton[@name="login delete"])[2]'
IOS_SIGN_IN_PASSWORD_VISIBILITY_TOGGLE_XPATH = '//XCUIElementTypeButton[@name="login pwd hide"]'
