"""
Android 注册/入口页共用元素定位（与 1登录/200001 同结构，供各用例文件顶部展示及 register_case_base 引用）。

注册页与登录页差异：
- 入口为 Sign Up；注册页 Next 多为 Button（登录 Sign In 页 next 为 ImageView）。
- 邮箱多在 ScrollView/EditText[1]；设置密码页为多个 EditText。
"""

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
# 步骤1～2：已登录判据（More）与登录/注册入口页
# 已登录：首页底部/侧边 More
XPATH_MORE = '//android.view.View[@content-desc="More"]'
# More 备用定位
XPATH_MORE_ALT = '//*[@content-desc="More"]'
# 未登录：入口页至少可见 Sign In 或 Sign Up
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)

# 步骤2：入口页 Sign In（确认在登录/注册落地页时可选）
# 入口页 Sign In 按钮（优先 TextView）
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
# Sign In 宽松匹配
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'

# 步骤3：入口页 Sign Up（进入注册流程）
# Compose 注册按钮（部分机型）
XPATH_SIGN_UP_COMPOSE = (
    "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/"
    "android.view.View/android.view.View[2]/android.widget.Button"
)
# 入口页 Sign Up 按钮（优先 TextView）
XPATH_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
# Sign Up 宽松匹配
XPATH_SIGN_UP_FALLBACK = '//*[@text="Sign Up"]'

# 注册主页面：邮箱输入（与登录 Sign In 页相同 ScrollView 结构）
# 注册页邮箱输入框 ScrollView 内第 1 个 EditText
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
# 点击聚焦邮箱（部分机型需点内层 View）
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
# 无 ScrollView 时的邮箱框 fallback
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"

# 设置密码页：密码 / 确认密码（通常为页面内第 1、2 个 EditText）
XPATH_PASSWORD = "//android.widget.EditText"
# 点击聚焦密码（部分机型需点内层 View）
XPATH_PASSWORD_FOCUS = "//android.widget.EditText/android.view.View[1]"

# 注册页：隐私政策勾选框
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
# 注册页提交 Next（Button；非登录页 ImageView next）
XPATH_NEXT = "//android.widget.Button"
# 登录页提交 next（注册用例一般不用，保留与登录脚本命名对齐）
XPATH_NEXT_LOGIN = '//android.widget.ImageView[@content-desc="next"]'

# 邮箱右侧清空 ×
XPATH_CLEAR_EMAIL = '(//android.widget.ImageView[@content-desc="clear"])[1]'
# 密码右侧清空 ×（设置密码页）
XPATH_CLEAR_PASSWORD = '(//android.widget.ImageView[@content-desc="clear"])[2]'
# 密码明文/密文切换（content-desc=lock）
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

# 国家/地区选择
XPATH_COUNTRY_ARROW = '//android.view.View[@content-desc="arrow_down"]'
# 国家列表搜索框
XPATH_COUNTRY_SEARCH = "//android.widget.EditText"

# 内页返回（国家列表取消、用户名页等）
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'

# 邮箱格式错误提示（注册页）
XPATH_INVALID_EMAIL_HINT = '//android.widget.TextView[@text="Please sign up using your email address"]'
MSG_INVALID_EMAIL = "Please sign up using your email address"

# Sign Up 免责声明整句（Privacy Policy / User Agreement 为 ClickableSpan，无独立节点）
DISCLAIMER_TEXT = "I have read and understood the Privacy Policy and agree to the User Agreement."
PRIVACY_LINK_PHRASE = "Privacy Policy"
USER_AGREEMENT_LINK_PHRASE = "User Agreement"

# 用户名页 Submit
XPATH_SUBMIT = '//*[@text="Submit"]'
# 用户名页 Skip
XPATH_SKIP = '//*[@text="Skip"]'
