# -*- coding: utf-8 -*-
"""产品列表与问题模板加载、题目生成。"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Iterable

from .paths import PRODUCTS_XLSX, QUESTION_TEMPLATES_JSON, QUESTION_TEMPLATES_XLSX

# 打乱题库用的固定种子：保证每次跑出来的题一致，断点续跑和回归对比才对得上
SHUFFLE_SEED = 20260924

_ZH_CHAR = re.compile(r"[\u4e00-\u9fff]")


def _row_enabled(value) -> bool:
    """启用列：否/0/N 才跳过，空着或填「是」都出题，方便在表尾直接加行。"""
    t = str(value or "").strip().lower()
    return t not in {"否", "n", "0", "false", "no", "停用"}


def _xlsx_rows(path: Path, sheet: str | None = None) -> tuple[list[str], list[tuple]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    name = sheet if sheet and sheet in wb.sheetnames else wb.sheetnames[0]
    ws = wb[name]
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    wb.close()
    if not rows:
        return [], []
    headers = [str(h or "").strip() for h in rows[0]]
    return headers, list(rows[1:])


def load_products(path: Path | None = None) -> list[str]:
    """读 config/产品列表.xlsx。启用列空着或「是」都会用，填「否」跳过。"""
    path = Path(path) if path else PRODUCTS_XLSX
    if not path.is_file():
        raise FileNotFoundError(f"缺少产品列表: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(f"产品列表须为 Excel: {path}")
    headers, rows = _xlsx_rows(path, "产品列表")
    enabled_i = headers.index("启用") if "启用" in headers else 0
    name_i = None
    for name in ("产品名", "产品", "型号"):
        if name in headers:
            name_i = headers.index(name)
            break
    if name_i is None:
        name_i = 1 if len(headers) > 1 else 0
    out: list[str] = []
    for row in rows:
        if not row or not _row_enabled(row[enabled_i] if enabled_i < len(row) else ""):
            continue
        p = str(row[name_i] or "").strip() if name_i < len(row) else ""
        if p:
            out.append(p)
    if not out:
        raise ValueError(f"产品列表无有效条目: {path}")
    return out


_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("质保服务", re.compile(r"质保|保修|warranty|RMA|restocking|延保|在保|冷静期|重新入库|注册保修|序列号.*保")),
    ("售后物流", re.compile(r"客服|售后|退货|换货|物流|发货|工单|寄修|Amazon|官网订单|理赔|缺件|翻新机|备用机|运费|说明书|包装破|承运商|补发|找谁")),
    ("配件耗材", re.compile(r"滤网|滤芯|滚刷|履带|配件|SKU|耗材|备件|原装|替换滤|边刷|充电器怎么买")),
    ("安全合规", re.compile(r"儿童|小孩|宠物|游泳前|GFCI|防火|锂电池|高压水枪|童锁|看管|人可以下水|人能不能下水|人身|缠住|玩具和浮床|CE 认证|UL 认证|FCC")),
    ("隐私账号", re.compile(r"隐私|两步验证|账号被|陌生人控制|删除账号|数据保存在|解绑|二次验证")),
    ("App账号", re.compile(r"App|APP|配网|Wi-?Fi|账号|通知|固件|OTA|绑定|共享|Alexa|Google Home|登录|推送|蓝牙|路由器|时区|Mesh|iPhone|Android|覆盖率图")),
    ("设备控制", re.compile(r"开始清洁|暂停我的|暂停清洁|恢复清洁|重启|遥控|确认执行|取消待确认|远程启动|远程取消")),
    ("安装电源", re.compile(r"充电座|充电器|插座|电源|电压|插头|NEMA|安装要求|充电线|110V|120V|230V|充电方式|充电距离|指示灯|无线还是有线|自动返回充电")),
    ("水质化学", re.compile(r"盐水|氯|溴|加氯|澄清剂|絮凝|盐氯|ppm|水质|藻类|绿水|铜离子|矿物质消毒|水线浑浊")),
    ("适用场景", re.compile(r"佛罗里达|德州|加州|纽约|德国|法国|西班牙|意大利|英国|HOA|Airbnb|Baja|solar cover|暴雨|花粉|山火|派对|lap pool|乙烯基|gunite|地上泳池|无边际|沙滩式|Spa|鹅卵石|玻璃钢|异形|室内泳池|户外泳池|斜坡|同系列|水泵/过滤|混凝土|喷浆|矩形泳池|灯位")),
    ("季节气候", re.compile(r"冬季|冬天|夏天|夏季|雨季|封池|开池|低温|高温|冰点|花粉季|落叶季|天气|风暴")),
    ("故障排查", re.compile(r"不动|离线|卡住|卡在|充不上|报错|故障码|E12|失败|异常|不工作|转圈|翻车|上浮|怎么办|为什么|排查|没反应|清洁中断|逐步恢复")),
    ("维护保养", re.compile(r"清洗|保养|存放|晾干|冲洗|排水|发霉|除垢|维护|轮换|收纳|运输时")),
    ("规格参数", re.compile(r"水深|续航|重量|尺寸|dimensions|噪音|防护|电池容量|功率|工作模式|面积|加仑|gallon|履带宽度|外形|多大的泳池|充满电需要|满电|清洁一次大约|一周建议|防缠绕|浮缆|无线电池|关键规格")),
    ("售前选型", re.compile(r"适合用吗|购买前|买 .{0,6}前|值不值得|推荐给|应该选|延保值不值得|比较无线|少请 pool|广告图|预算有限|更看重")),
    ("清洁策略", re.compile(r"多久跑|运行频率|清洁策略|只清池底|只想.*水线|快速清洁|节能模式|日常维护和重污染|一周建议清洁")),
    ("日常使用", re.compile(r"如何|怎么|怎样|能否|可以|支持|正确做法|官方建议|首次使用|清洁前需要|注意事项|泡在水里|朝向|先看哪些资料|本月与上月|查找机器人")),
]


def classify_question(text: str) -> str:
    """按题目内容自动归类，供 Excel「问题类型」列和 --type 筛选使用。"""
    q = str(text or "").strip()
    for name, pat in _TYPE_RULES:
        if pat.search(q):
            return name
    return "综合咨询"


# 官网 beatbot.com 公开规格（2026-09 核对），写进客服答案，避免空泛。
_BEATBOT = {
    "sora10": {
        "depth": "0.5–3.5 m（1.6–9.8 ft），浅区可到约 12 in / 30 cm",
        "runtime": "仅池底最长约 5 h，池底+池壁+水线约 4 h",
        "battery": "7800 mAh",
        "charge": "约 3.5 h，65W，110–240V 钛合金充电头",
        "suction": "6800 GPH",
        "basket": "5 L，标配 150 μm，约可装 650 片落叶",
        "cover": "最大约 300 m² / 3229 sq.ft",
        "weight": "8.5 kg / 18.7 lb",
        "size": "432×386×267 mm（17.01×15.20×10.51 in）",
        "ip": "IPX68",
        "warranty": "官网 2 年质保 + 30 天退货（经销商订单除外）",
        "modes": "池底 / 池壁 / 标准 / ECO",
        "extra": "无水面清洁、无遥控模式；有水线停靠、SonicSense 避障、App（2.4G/5G Wi-Fi + 蓝牙）",
    },
    "sora30": {
        "depth": "浅区约 8 in / 20 cm",
        "runtime": "仅池底最长约 5 h，全清洁约 4.5 h",
        "battery": "10000 mAh",
        "charge": "约 4.5 h，65W，110–240V",
        "basket": "约 5.2 L，150 μm，可选 3 μm 细滤",
        "warranty": "官网 2 年质保 + 30 天退货",
        "extra": "有水面停靠和 App 一键召回；无水面清洁、无遥控",
    },
    "sora70": {
        "depth": "浅区约 8 in",
        "runtime": "水面清洁最长约 7 h，池底约 5 h，全清洁约 4.5 h",
        "battery": "10000 mAh",
        "charge": "约 4.5 h，65W，110–240V",
        "basket": "6 L，150 μm，可选 3 μm",
        "warranty": "官网 3 年质保 + 30 天退货",
        "extra": "有 JetPulse 水面清洁和遥控模式",
    },
    "iskim": "iSkim 是水面撇渣机器人，太阳能+约 10000 mAh，适合 24/7 收水面漂浮物，常和 Sora 搭配；官网常见 2 年质保。",
    "asx": "AquaSense X 旗舰：电池约 13400 mAh，水面清洁最长约 10 h、池底约 5 h，覆盖约 3875 sq.ft；AstroRinse 基站约 3 分钟自清洁、22 L 尘盒；无线约 4.5 h / 88W；官网 3 年整机质保。",
    "common": "Sora 系列均可用于混凝土、瓷砖、乙烯基、玻璃钢，以及地埋/地上池；家庭盐水池盐度需低于 5000 ppm。充电 110–240V。",
    "cs": "美国客服 service@beatbot.com，电话 +1 (833) 702-4399，时间 9:00–18:00（CST）。",
}


def _spec_line() -> str:
    s10 = _BEATBOT["sora10"]
    return (
        f"以官网数据为例：Sora 10 水深 {s10['depth']}，电池 {s10['battery']}，"
        f"{s10['runtime']}，充电 {s10['charge']}。"
        f"Sora 30 电池 {_BEATBOT['sora30']['battery']}，{_BEATBOT['sora30']['runtime']}，充电 {_BEATBOT['sora30']['charge']}。"
        f"Sora 70 电池 {_BEATBOT['sora70']['battery']}，{_BEATBOT['sora70']['runtime']}，{_BEATBOT['sora70']['extra']}。"
        f"{_BEATBOT['asx']}"
    )


_ANSWER_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"工作水深|水深范围|最小工作水深|最大工作水深"),
     "官网：Sora 10 工作水深 0.5–3.5 m（1.6–9.8 ft），浅台/晒台可到约 12 in（30 cm），平台建议至少约 3.3 ft×3.3 ft。Sora 30/70 浅区约 8 in（20 cm）。超过 3.5 m 不建议。{p} 请对应该型号说明书。"),
    (re.compile(r"适合多大|建议适用于多大|泳池面积|平方米泳池|gallon 泳池|加仑|3229|240 平方"),
     "官网覆盖：Sora 10 最大约 300 m² / 3229 sq.ft（约 240 m² 也有渠道按此宣传）；AquaSense X 约 3875 sq.ft。20×40 ft 矩形池大约 800 sq.ft，Sora 系列一次通常够用。50 m² 没问题，150 m² 建议用满电并可能要加跑。{p} 以该型号页为准。"),
    (re.compile(r"续航|满电大约|满电能用|一次清洁够不够"),
     "实验室数据：Sora 10 仅池底最长约 5 h，含墙和水线约 4 h；Sora 30 池底约 5 h、全清洁约 4.5 h；Sora 70 水面约 7 h、池底约 5 h；AquaSense X 水面约 10 h、池底约 5 h。脏污、低温会缩短。电量低会停或停靠水面，不保证一次清完超大池。"),
    (re.compile(r"充满电|充电要多久|多久充满"),
     "官网：Sora 10 约 3.5 h / 65W；Sora 30、Sora 70 约 4.5 h / 65W；AquaSense X 约 4.5 h / 88W 无线充。充电器 110–240V。请用原装钛合金充电头，触点擦干再充。"),
    (re.compile(r"履带宽度"),
     "官网规格页未单列履带宽度。Sora 10 整机尺寸 432×386×267 mm、重 8.5 kg。履带具体宽度请看 {p} 包装或说明书零件图，不要用别的型号估算。"),
    (re.compile(r"外形尺寸|dimensions|整机重量"),
     "Sora 10 官网：8.5 kg / 18.7 lb，外形 432×386×267 mm（17.01×15.20×10.51 in）。AquaSense X 基站体积更大（渠道数据约 25.1×21.1×22.0 in）。请按 {p} 规格确认取出是否方便。"),
    (re.compile(r"噪音|分贝|HOA.*噪|晚上.*吵|夜间.*跑"),
     "官网未公布分贝值。Sora 10 是 3 电机机，运行会有电机和履带声。HOA 有噪音限制时建议白天跑。AquaSense X 有夜间清洁和双 1500 Lx 前灯，仍建议避开邻居卧室一侧通宵。"),
    (re.compile(r"防护等级|防水等级|IP"),
     "Sora 10 官网标 IPX68，可在推荐水深内工作。不要当潜水装备，也不要用高压水枪冲内部和充电口。"),
    (re.compile(r"电池容量|电机功率"),
     "官网电池：Sora 10 为 7800 mAh，Sora 30/70 为 10000 mAh，AquaSense X 约 13400 mAh。Sora 10 标 3 电机、吸力 6800 GPH。电机功率（W）官网未统一公布，请看 {p} 铭牌。"),
    (re.compile(r"质保.*(盐|盐水)|盐水.*质保|盐水使用是否在保|美国质保多久|欧盟质保多久"),
     "官网质保：Sora 10/30、iSkim 一般为 2 年，Sora 70、AquaSense X 为 3 年（含驱动盒电池、主板、电机、传感器、塑料件和电源，条款以官网为准）。另有 30 天退货（经销商订单除外）。家庭盐水池盐度低于 5000 ppm 可用；是否因盐水影响理赔以保修条款为准，用完建议淡水冲洗。"),
    (re.compile(r"说明书|快速入门|手册|哪里下载|哪里看"),
     "请到 beatbot.com 对应产品页或 Support 下载 {p} 说明书/快速入门，也可在 Beatbot App 里查看。Sora 10 规格也可直接看 https://beatbot.com/products/sora-10 。"),
    (re.compile(r"售后联系|客服.*什么|怎么联系|英语电话|工作时间"),
     "美国官网客服：邮箱 service@beatbot.com，电话 +1 (833) 702-4399，时间 9:00–18:00（CST）。联系时请带上 {p} 型号、序列号和订单号。"),
    (re.compile(r"UL 认证|CE 认证|FCC"),
     "充电器 110–240V，请认准机身/电源铭牌上的 UL、CE、FCC 等标识。AquaSense X 渠道资料提到约 16 项认证。不同地区套装认证组合可能不同，以您收到的铭牌为准。"),
    (re.compile(r"充电时指示灯|指示灯"),
     "Sora 用钛合金充电头（Sora 10 约 3.5 h/65W，Sora 30/70 约 4.5 h/65W）。指示灯常见为充电中/充满/异常，以说明书图示为准。灯不亮先擦干触点、换插座；仍不亮拍照给 service@beatbot.com。"),
    (re.compile(r"无线还是有线|充电方式|无线电池|浮缆"),
     "Sora 系列是无线电池机，无浮缆。Sora 用钛合金插头充电（Sora 10 约 3.5 h/65W）；AquaSense X 可在 AstroRinse 基站无线充（约 4.5 h/88W）。不要用非原装电源。"),
    (re.compile(r"自动返回充电|自动回充"),
     "Sora 10 清洁结束后会水线停靠约 10 分钟方便捞取，不是开回岸上充电座。Sora 30/70 有水面停靠和 App 一键召回。AquaSense X 可回 AstroRinse 基站清洗并充电。日常 Sora 仍需取出插电。"),
    (re.compile(r"循环泵要开还是关|循环泵开启|和水泵"),
     "可以和循环泵同时开。{p} 是池内清洁机器人（Sora 吸力 6800 GPH），不替代砂缸/滤芯。回水口太猛可能冲偏 S 形路径，必要时调小喷口或错开强力回流。"),
    (re.compile(r"细沙|淤泥"),
     "可以吸细沙、头发、昆虫，Sora 10 标配 150 μm 滤网，进水口水下约 25×170 mm，FAQ 写明能收橡果等。厚淤泥或粉尘建议加选更细滤网（Sora 30/70 可选 3 μm），并更勤倒 5 L 尘盒。"),
    (re.compile(r"瀑布|气泡"),
     "瀑布/气泡开着可以用，但会冲偏 S 形路径和爬墙。建议清洁时关掉水景。Sora 10 无水面清洁，水面泡沫请另捞或改用 Sora 70 / iSkim。"),
    (re.compile(r"风暴预警|有风暴|暴雨前"),
     "雷雨/风暴预警时先取出机器并拔掉 65W 充电器，不要留在池里。暴雨后再下水前先捞大树枝；Sora 10 尘盒 5 L，一次约 650 片叶，特大枝条仍要人工。"),
    (re.compile(r"查看.*天气|所在地天气"),
     "App 天气只作参考。雷雨大风请取出 {p}。佛罗里达/德州落叶季建议加密到每周 3 次以上，滤网勤洗。"),
    (re.compile(r"新US用户|新EU用户|先看哪些资料"),
     "美国用户先看 beatbot.com 对应产品页和快速入门：Sora 10 先充满约 3.5 h，确认水深 0.5–3.5 m 再下水，App 用 2.4G/5G。售后 service@beatbot.com / +1 (833) 702-4399（9–18 CST）。欧洲请认准当地插头和 CE 铭牌。说明书：https://beatbot.com/products/sora-10"),
    (re.compile(r"关键规格以便购买|购买决策"),
     "对照官网：Sora 10 覆盖约 3229 sq.ft、水深 0.5–3.5 m、池底约 5 h、5 L/150 μm、6800 GPH、约 $449、2 年质保，无水面清洁。浅台低于 12 in 选 Sora 30/70（8 in）。要水面+遥控选 Sora 70（6 L、3 年）。要基站自清洁选 AquaSense X（3875 sq.ft、22 L 基站、约 3 分钟冲洗、3 年整机换新）。把泳池尺寸发给客服可对 {p}。"),
    (re.compile(r"室内泳池"),
     "室内池可以用。Sora 10 官网支持各种池形，材料含混凝土/瓷砖/乙烯基/玻璃钢，水深仍要 0.5–3.5 m。室内注意通风和氯浓度，用完沥干，不要长期潮湿存放。"),
    (re.compile(r"户外泳池"),
     "户外家庭池是主场景。Sora 10 尘盒 5 L 约 650 片叶；佛罗里达落叶/花粉季建议每周 2–3 次，滤网满了就洗。充电器放遮雨处。要收水面漂浮物加 Sora 70 / iSkim / AquaSense X。"),
    (re.compile(r"斜坡池底|坡度"),
     "缓坡可以。Sora 10 浅台最低约 12 in，平台建议 ≥3.3×3.3 ft；Sora 30/70 浅区约 8 in。沙滩式过浅或跌落边可能搁浅、爬上岸。官网未公布最大爬坡角，建议第一次守着试跑。"),
    (re.compile(r"乙烯基|池膜|刮伤"),
     "官网写明 Sora 可用于乙烯基池膜。褶皱、修补贴、松弛膜容易卡住履带。先检查池膜平整；出现明显刮痕请停用并联系售后，附照片和序列号。"),
    (re.compile(r"混凝土|喷浆|gunite|pebble|鹅卵石|玻璃钢|fiberglass"),
     "官网兼容：混凝土、瓷砖、乙烯基、玻璃钢，地埋/地上均可。粗糙喷浆/鹅卵石会加快履带磨损；过滑马赛克可能影响爬墙。新铺 plaster 等养护期结束再用。"),
    (re.compile(r"地上泳池|above-ground"),
     "官网写明 Sora 10 可用于地上池和地埋池。前提是水深仍在 0.5–3.5 m，软底或不足约 12 in 的浅区不适合。27 ft 地上圆池用户评价可用。不确定把壁高、水深发给客服。"),
    (re.compile(r"Spa 区|连着 Spa|跑进 Spa"),
     "相连 Spa 往往浅于 12 in（Sora 10）或 8 in（Sora 30/70），机器可能误入或搁浅。请用围挡，或 App 选 Floor 仅池底，不要从 Spa 台阶出发。"),
    (re.compile(r"自动池盖|solar cover|太阳能保温盖"),
     "盖着自动池盖或 solar cover 时不要运行，容易缠轨道或闷机。关上池盖前必须取出。Sora 10 结束后会水线停靠约 10 分钟，请在这段时间捞走再盖盖。"),
    (re.compile(r"Baja|浅台|sun shelf"),
     "Sora 10 浅台最低约 12 in，平台 ≥3.3×3.3 ft；Sora 30/70 可到约 8 in；AquaSense X 约 14 in。更浅的 Baja/晒台会搁浅，躺椅先拿走，过浅区改人工捞。"),
    (re.compile(r"主排水口"),
     "主排水口盖过高或松动，履带可能卡住。Sora 10 有 SonicSense（11 个传感器含 1 个超声波）会尝试绕障，但不能保证。盖板请平整拧紧；反复停在排水口拍视频给售后。"),
    (re.compile(r"灯位|水下灯"),
     "Sora 10 有 SonicSense 避障，会尝试绕灯坑和回水口，不能保证完全避开。灯罩突出或破碎请先修好。AquaSense X 有 29 传感器和 AI 相机，绕障更强。"),
    (re.compile(r"无边际|赶潮|跌落"),
     "官网 FAQ：Sora 10 可清无边际池的池底、池壁和水线。溢流跌水边仍有落差风险，请确认有物理止挡，不要让机器靠近溢流沿。"),
    (re.compile(r"沙滩式入水|爬上岸"),
     "沙滩式入水会浅于推荐水深（Sora 10 约 12 in，Sora 30/70 约 8 in），可能搁浅或爬上甲板。第一次请守着试跑，过浅区改人工清理。"),
    (re.compile(r"更看重爬墙"),
     "Sora 10/30/70 都支持爬墙和水线，Sora 10 有双前滚刷差速和 Wall 模式。墙面过滑（玻璃马赛克）效果会差。更看重墙面+水面一体，选 Sora 70 或 AquaSense X。"),
    (re.compile(r"更看重智能"),
     "全系 Beatbot App：启动/暂停、OTA。Sora 10 有 11 个传感器含超声波避障、S 形路径。Sora 70 多遥控和水面清洁；AquaSense X 有夜间清洁、语音和自清洁基站。入水后实时图会弱。"),
    (re.compile(r"推荐给 50|推荐给 100|推荐给 150|8x4|20x40"),
     "Sora 10 最大约 300 m² / 3229 sq.ft。8×4 m（32 m²）或 20×40 ft（约 74 m²）都在范围内。150 m² 仍可，但建议满电、滤网勤洗，必要时加跑。最小水深仍要满足 0.5 m（Sora 10）。"),
    (re.compile(r"比较无线|有线机器人"),
     "Sora/AquaSense 都是无线机，无浮缆。Sora 10 池底最长约 5 h，充一次约 3.5 h。有线机可一直供电但线会缠绕。大池或要少捞机器，可看 AquaSense X 回充基站。"),
    (re.compile(r"少请 pool service|替代.*服务|省哪些维护"),
     "Sora 能减少日常刷底、捞碎屑（Sora 10 一次约可装 650 片叶）。水质检测、砂缸反冲洗、冲击加氯、绿水开池仍要做。AquaSense X 的 AstroRinse 可减少每次洗滤网，基站 22 L 渠道说最多约两个月倒一次。"),
    (re.compile(r"第三方滤网|非原装滤网"),
     "不建议第三方滤网。Sora 10 标配 150 μm / 5 L；Sora 30/70 可加购官方 3 μm 细滤。尺寸目数不对会漏脏或堵死，也可能影响质保。请买 {p} 原装件。"),
    (re.compile(r"滤芯多久更换|滤网多久.*换|更换周期"),
     "Sora 10 尘盒 5 L、标配 150 μm，先以每次/隔次冲洗为主，破损再换。Sora 30 约 5.2 L，Sora 70 为 6 L，可加购 3 μm 细滤。AquaSense X 基站尘盒约 22 L，渠道说最多约两个月才倒一次。"),
    (re.compile(r"滤网如何清洗|怎么.*洗滤网|冲洗滤网"),
     "Sora 从顶部取出 5–6 L 尘盒，清水冲洗 150 μm 滤网，不要高压水枪或洗碗机。AquaSense X 回 AstroRinse 后约 3 分钟自动冲洗倒污。晾干再装回。"),
    (re.compile(r"滚刷.*更换|履带.*更换|履带磨损|滚刷磨损"),
     "Sora 10 是双前滚刷差速，掉毛、履带开裂或爬墙打滑就该换原装件。粗糙喷浆池会磨得更快。把 {p} 序列号发给 service@beatbot.com 查 SKU。"),
    (re.compile(r"SKU|料号"),
     "滤网/滚刷/履带料号在配件包装或说明书配件表。Sora 10 与 Sora 70 尘盒容量不同（5 L vs 6 L），不要跨型号混用。把序列号发给 service@beatbot.com 可查。"),
    (re.compile(r"单独买充电器|替换充电器"),
     "可单独买原装充电器：Sora 为 65W、110–240V 钛合金头（Sora 10 约 3.5 h 充满）；AquaSense X 基站约 88W 无线充。插头按地区，不要用别的品牌或车载逆变长期充。"),
    (re.compile(r"盐水|盐氯|盐度") ,
     "可以。官网明确 Sora 10/30/70 可用于盐水池，盐浓度需低于 5000 ppm；绝大多数家庭盐池不超过此值。用完建议淡水冲洗履带和金属件。"),
    (re.compile(r"冲击加氯|投放氯|高氯"),
     "冲击加氯后请等药剂循环、浓度回到日常范围再让 {p} 下水。清洁过程中不建议同时大剂量加氯。高氯可能加速密封件老化。"),
    (re.compile(r"澄清剂|絮凝|绿水"),
     "澄清/絮凝后等沉淀完成再跑，否则 150 μm 滤网很快堵。绿水不能单靠机器人变清。AquaSense X 的 ClearWater 需另购 Beatbot 3-in-1 Clarifier Kit，不是机身自带。"),
    (re.compile(r"藻类较多"),
     "轻藻可先刷壁再让机器收脱落物。Sora 30/70 可加购 3 μm 细滤收死藻粉末；标配 150 μm 会放过更细颗粒。片状绿水要先调氯和过滤，机器不能当除藻剂。"),
    (re.compile(r"水线浑浊"),
     "刚启动时水线附近翻起一点浊度较常见，稍后应好转。一直浑浊请查滤网是否满、是否刚加药，以及循环过滤是否在工作。"),
    (re.compile(r"在水下为什么会断开|水下.*断开 Wi-?Fi"),
     "水会衰减无线。Sora 10 标称 Wi-Fi 约 40 m、蓝牙约 20 m，入水后 App 离线很常见，已开始的清洁一般继续。Sora 10 仍有水线停靠。出水后会重新上线。"),
    (re.compile(r"如何连接 Wi-?Fi|配网失败|2\.4|Mesh|本地网络"),
     "Sora 10/30/70 支持 2.4G + 5G Wi-Fi 和蓝牙（Sora 10：Wi-Fi 约 40 m，蓝牙约 20 m）。水下蓝牙/Wi-Fi 会明显变弱，属正常。配网时 iPhone 打开本地网络；Mesh 失败请靠近主路由。App 支持 iOS、Android，Sora 10 还写了 Apple Watch。"),
    (re.compile(r"查看电量|电量百分比"),
     "在 Beatbot App 看电量。Sora 10 池底约 5 h / 全清洁约 4 h；入水后 Wi-Fi/蓝牙变弱，数字可能延迟，以出水后为准。电量低时 Sora 10 会水线停靠方便捞取。"),
    (re.compile(r"充不上电|无法充电|充电器插上没有指示"),
     "确认原装 65W 钛合金头插紧（AquaSense X 用基站 88W），插座 110–240V 有电，触点擦干无盐霜。充电中可能无法关机。灯完全不亮拍照给 service@beatbot.com。"),
    (re.compile(r"如何开机|无法开机|按开机键"),
     "先拔掉充电器（充电中常有保护），确认有电后再按说明书长按开机。Sora 也可用 App 启动。仍无反应不要拆机，带序列号联系 +1 (833) 702-4399。"),
    (re.compile(r"如何开始清洁|现在能让|开始清洁吗"),
     "放入泳池后用机身键或 Beatbot App 启动。Sora 10 有池底/池壁/标准/ECO 等模式；Sora 70 另有遥控和水面清洁。先拿走玩具浮床，水深 Sora 10 建议 0.5–3.5 m。"),
    (re.compile(r"如何暂停清洁|暂停后|恢复清洁|继续这次任务"),
     "岸上或水线附近用 App/机身键暂停、恢复。入水后 Sora 10 常离线，暂停可能要等它靠近水面。任务已结束或电量过低通常不能原地续扫，需重新开始。"),
    (re.compile(r"远程取消|取消待确认|二次确认"),
     "App 弹出确认请看清再点。Sora 10 无遥控模式，入水后常离线，指令可能要等它回到水线。Sora 70 / AquaSense X 支持遥控或更完整 App 控制。要取消待确认，在提示里选取消。"),
    (re.compile(r"设备忙"),
     "提示设备忙，表示 {p} 正在执行任务或还在处理上一条指令。请等当前动作结束，不要连续连点。"),
    (re.compile(r"反复掉线|反复离线"),
     "先分清入水暂时离线还是出水后仍掉线。Sora 10 标称 Wi-Fi 约 40 m、蓝牙约 20 m，水下变弱正常。出水后仍掉线：查 2.4G/5G、iPhone 本地网络权限、是否换过路由，截图给售后。"),
    (re.compile(r"入水后.*离线|水下 App 显示离线|App 显示离线"),
     "入水离线但机器还在走，通常正常（水衰减无线）。Sora 10 仍按已选模式（Floor/Wall/Standard/ECO）继续，结束后水线停靠。出水后仍离线再重新配网。"),
    (re.compile(r"清洁不干净|角落漏扫|覆盖率"),
     "先冲洗 150 μm 滤网、检查双前滚刷。确认不是只开了 Floor。Sora 10 池底走 S 形；台阶、异形角、浅于 12 in 的台容易漏。可换出发位置再跑，或加跑一次。App 覆盖率图只是示意。"),
    (re.compile(r"卡在池底|入水后不动|停住不动|卡住"),
     "查电量、5 L 尘盒是否满、履带/进水口（水下约 25×170 mm）是否缠住，以及台阶、主排水口盖。捞上岸清理后再试。反复卡住拍视频给售后。"),
    (re.compile(r"一直绕圈|转圈"),
     "滤网过满、单侧履带打滑或 SonicSense 被台阶干扰都可能绕圈。先洗 5 L 尘盒、检查履带，换出发位置。仍转圈带视频联系售后。"),
    (re.compile(r"爬墙"),
     "Sora 10/30/70 都支持爬墙和水线，Sora 10 有 Wall / Standard 模式和双前滚刷差速。仅 Floor、电量低或马赛克过滑时可能不爬。水线官网写有约 8 秒加强刷洗。"),
    (re.compile(r"E12|故障码|错误码"),
     "到 App 告警或说明书故障码表查 {p} 的代码，记下代码、时间和现场视频，发给 service@beatbot.com，不要只说「报错了」。"),
    (re.compile(r"注册保修|序列号在哪里|怎么判断还在保"),
     "序列号在机身铭牌。用订单+序列号在 beatbot.com 或 App 注册。官网年限：Sora 10/30 为 2 年，Sora 70 / AquaSense X 为 3 年（X 为整机换新）。是否在保以注册日期和条款为准。"),
    (re.compile(r"质保政策|质保期|美国质保|欧盟质保|保修"),
     "beatbot.com：Sora 10/30 为 2 年质保（维修或换新/翻新机），Sora 70 为 3 年，AquaSense X 为 3 年整机换新；范围含驱动/电池、PCB、电机、传感器、塑料件和电源。另有 30 天退货（经销商除外）。耗材、磕碰、私拆通常不在保。欧盟另有当地消费者法。"),
    (re.compile(r"RMA|申请保修.*照片|保修视频"),
     "申请 RMA 请提供订单号、序列号、故障描述，以及整机、铭牌和故障过程视频。按客服清单补拍，审核通过后给寄修地址。"),
    (re.compile(r"退货|restocking|冷静期"),
     "官网 30-Day Money-Back（经销商订单除外），自签收起 30 个自然日可申请。30 天内若官网或官方 Amazon 同款降价，邮件 service@beatbot.com 可申请差价。Amazon 退货走亚马逊政策；欧盟另有冷静期。包装配件尽量齐全。"),
    (re.compile(r"包装破|缺件|发错|到货.*划痕"),
     "收货 48 小时内拍外箱、内包装和问题部位，连同订单号发给购买渠道或 service@beatbot.com。我们安排补发、换货或指导承运商索赔。"),
    (re.compile(r"物流|发货多久|查物流"),
     "官网订单在账户订单页查物流；Amazon 走亚马逊订单。配件（3 μm 滤网、充电器）时效因仓库而异。查不到单号把订单号发 service@beatbot.com。"),
    (re.compile(r"寄修运费|备用机|RMA.*多久"),
     "先向 service@beatbot.com 建 RMA，不要自行寄无授权地址。是否包运费、有无备用机以当地政策为准。AquaSense X 官网是 3 年整机换新，Sora 多为评估后维修或换新/翻新机。"),
    (re.compile(r"GFCI|110V|120V|230V|插头|德国.*插头"),
     "Sora 充电器官网标 110–240V、65W（AquaSense X 基站约 88W）。美国请用原装头，泳池边建议 GFCI。欧洲用当地插头版本，不要只靠旅行转换头。雷雨请拔电。"),
    (re.compile(r"充电距离|离泳池要隔多远"),
     "Sora 在岸上用钛合金头充电，放干燥处远离溅水，线长以原装为准，不要私接延长线泡在水边。AquaSense X 在 AstroRinse 基站无线充。雷雨拔电。美国泳池边建议 GFCI。"),
    (re.compile(r"游泳前|人可以下水|人能不能下水"),
     "清洁时不要下水。Sora 10 吸力 6800 GPH、进水口约 25×170 mm，人和机器不要同时在池里。游之前先取出。结束后它会水线停靠，请及时捞走。"),
    (re.compile(r"儿童|小孩|宠物|狗在泳池边"),
     "运行中儿童和宠物远离池边，不要伸手碰履带和进水口。能看管时再运行。充电器 65W 放儿童够不到的干处。结束立即取出。"),
    (re.compile(r"自动池盖关闭前必须取出"),
     "是的，关上自动池盖前必须先取出 {p}，否则可能压坏机器或卡住盖子。"),
    (re.compile(r"玩具|浮床"),
     "启动前拿走玩具、浮床、救生圈和缆绳。Sora 10 有 SonicSense 避障，但仍可能缠进双前滚刷。浮床占水面时也不要指望它绕过去。"),
    (re.compile(r"高压水枪"),
     "不要用高压水枪冲内部、轴承和钛合金充电口。Sora 10 虽标 IPX68，高压仍可能破坏密封。外壳用缓水流冲，滤网手洗。"),
    (re.compile(r"洗碗机|白醋|紫外"),
     "5–6 L 滤网不要进洗碗机、紫外箱或长时间泡强酸。清水冲洗晾干。轻水垢可用少量白醋擦后冲净。AquaSense X 回基站约 3 分钟自动冲洗。"),
    (re.compile(r"解绑|二手转让|卖房"),
     "在 Beatbot App 设备设置解绑 {p} 并退出共享。二手/卖房前必须解绑，否则新用户无法绑定。同时告知对方质保余期（Sora 10/30 共 2 年，Sora 70 / X 共 3 年）。"),
    (re.compile(r"数据存在|隐私政策"),
     "账号和设备数据按 Beatbot 隐私政策处理，文本在官网/App 隐私页。删除账号请邮件 service@beatbot.com 申请。"),
    (re.compile(r"两步验证|账号被|陌生人"),
     "请立刻修改密码，退出陌生设备，并检查 {p} 共享列表。如支持两步验证请开启。同时看近期控制记录。"),
    (re.compile(r"分享|配偶|家人"),
     "在 App 里把 {p} 共享给家人账号，可按说明设置控制或仅查看权限。不要把主人账号密码直接给客人。"),
    (re.compile(r"固件|OTA|必须升级"),
     "OTA 请在岸上、电量充足、Wi-Fi 稳定时进行（Sora 10 支持 2.4G/5G）。提示必须升级建议完成。失败不要反复刷，联系 service@beatbot.com。"),
    (re.compile(r"覆盖率图|地图.*不像|清洁地图"),
     "Sora 10 无 AI 相机建图，App 覆盖率多为示意；入水后信号差，图可能和真实池形不一致。AquaSense X 有 HybridSense AI 建图更准。请以实际清洁效果为准。"),
    (re.compile(r"通知|推送|电池优化"),
     "给 Beatbot App 打开通知；Android 关闭电池优化。App 支持 iOS/Android，Sora 10 还写了 Apple Watch。仍收不到查系统通知和是否被踢登录。"),
    (re.compile(r"排水保养|存放|冬季|封池|长时间不用|如何保存"),
     "封池或长期不用：取出机器，倒净积水，冲洗 5–6 L 尘盒和履带，开口朝下晾干。锂电池（Sora 10 7800 mAh）建议留约一半电，放干燥防冻处，不要冰点以下。开春先充满再下水。"),
    (re.compile(r"清洁后如何收纳|晾干"),
     "用完冲洗 150 μm 滤网，沥干机身，开口朝下晾干再收。不要装密封箱。用户评价也建议阴干后再室内充电。"),
    (re.compile(r"运输时"),
     "用原包装或固定履带，避免磕碰钛合金充电口。锂电池：Sora 10 7800 mAh、Sora 30/70 10000 mAh、AquaSense X 约 13400 mAh，航空/托运有限制，跨国先问客服和航司。"),
    (re.compile(r"只清池底|不要爬墙"),
     "Sora 10 在 App 选 Floor，仅池底最长约 5 h。不要选 Wall/Standard。从池中央出发，减少靠墙。"),
    (re.compile(r"只想.*水线|重点清.*水线"),
     "Sora 10 选 Wall 或 Standard（含墙和水线，全清洁约 4 h）。官网写水线有约 8 秒加强刷洗。油膜/防晒残留仍可能要人工擦。要水面油膜选 Sora 70 JetPulse 或 iSkim。"),
    (re.compile(r"快速清洁|强力模式|节能模式|标准模式|清洁模式"),
     "Sora 10 官网模式：Floor（仅池底最长约 5 h）、Wall、Standard（底+墙+水线约 4 h）、ECO。没有单独「仅水线」或「强力」名称。AquaSense X 另有 AI Quick。Sora 70 另有遥控和水面清洁。"),
    (re.compile(r"一周.*几次|多久跑|运行频率"),
     "日常建议每周 2–3 次；落叶/花粉季或派对后可每天或隔天。Sora 10 满电池底约 5 h，尘盒 5 L 满了就洗，不必为了跑满 5 小时每天硬跑。"),
    (re.compile(r"适合用吗|购买前|买 .{0,8}前"),
     "Sora 10 适合约 3229 sq.ft 内、水深 0.5–3.5 m 的家庭池，材料含混凝土/乙烯基/玻璃钢/瓷砖，盐水 <5000 ppm。浅台低于 12 in 选 Sora 30/70；要水面清洁选 Sora 70；要自清洁基站选 AquaSense X。绿水和重污染仍要人工+过滤。把尺寸发给客服可对 {p}。"),
    (re.compile(r"首次使用|清洁前需要|开箱"),
     "开箱：用原装头充满（Sora 10 约 3.5 h），装好 150 μm 滤网，Beatbot App 配 2.4G/5G。确认水深（Sora 10：0.5–3.5 m）后下水，先拿走玩具浮床缆绳。"),
    (re.compile(r"iSkim|撇渣"),
     "iSkim 是水面撇渣机器人，太阳能 + 约 10000 mAh，适合 24/7 收漂浮物，常和 Sora 搭配（Sora 10/30 自己不清水面）。官网常见 2 年质保。大水面油膜/花粉也可看 Sora 70 JetPulse 或 AquaSense X。"),
    (re.compile(r"AquaSense|AstroRinse|基站|自清洁站"),
     "AquaSense X：电池约 13400 mAh，池底约 5 h、水面约 10 h，覆盖约 3875 sq.ft，吸力 6800 GPH，29 传感器 + AI 相机。AstroRinse 约 3 分钟自冲洗，基站尘盒约 22 L（渠道说最多约两个月/约 3000 片叶）。无线充约 4.5 h/88W。官网 3 年整机换新。ClearWater 需另购澄清套装。"),
    (re.compile(r"遥控|remote"),
     "Sora 10/30 无遥控模式；Sora 70 和 AquaSense X 支持 App 遥控（Sora 70 还可水面遥控）。Sora 10 只能 App 启动/暂停和选 Floor/Wall/Standard/ECO。"),
    (re.compile(r"水面清洁|清水面|漂浮物|花粉.*水面"),
     "Sora 10/30 不清水面。要收漂浮物：Sora 70（JetPulse，水面约 7 h，6 L）、AquaSense X（水面约 10 h）或另配 iSkim。Sora 10 只做池底/墙/水线。"),
    (re.compile(r"佛罗里达|德州|加州|花粉季|落叶季"),
     "热门阳光带：建议每周至少 2–3 次。花粉/落叶季 Sora 10 的 5 L/150 μm 会很快满，勤洗；要更细粉尘可看 Sora 30/70 的 3 μm 滤网。只要水面漂浮物，加 Sora 70 或 iSkim。"),
    (re.compile(r"Alexa|Google Home|Siri|语音"),
     "AquaSense X 渠道资料写了 Alexa / Google Home / Siri。Sora 10 官网主打 Beatbot App（iOS/Android/Apple Watch），未把语音助手列为卖点。请以您收到的 App 版本为准。"),
    (re.compile(r"预约|定时|日程"),
     "在 Beatbot App 里预约启动。Sora 是无线机，预约前请确认已放入泳池、电量足够（Sora 10 满电池底约 5 h）。AquaSense X 可从基站自动出发并夜间清洁。"),
    (re.compile(r"清洁区域|清洁池壁|清洁水线|同时清洁池底|清洁池底、池壁|支持哪些清洁"),
     "Sora 10/30：池底、池壁、水线、浅台（Sora 10 浅台约 12 in，Sora 30 约 8 in），不清水面。Sora 70 / AquaSense X 另有水面清洁。Sora 10 选 Standard 可一次做底+墙+水线（约 4 h），只清底选 Floor（约 5 h）。"),
    (re.compile(r"有哪些工作模式|切换工作模式|静音模式"),
     "Sora 10：Floor / Wall / Standard / ECO，在 App 或机身切换。没有单独「静音」档，要更安静选 ECO，并白天跑。Sora 70 另有遥控和水面模式；AquaSense X 另有 AI Quick、夜间清洁。"),
    (re.compile(r"离线了怎么处理|完全离线|没有账号|不连云|云服务故障|本地启动"),
     "入水离线通常正常（Sora 10：Wi-Fi 约 40 m，水下会断）。出水后仍离线：查 2.4G/5G、重新配网。机身键可在无 App 时启动，但预约/遥控/记录要账号。Sora 10 无遥控。"),
    (re.compile(r"App 远程控制|远程控制"),
     "Sora 10/30 可 App 启动/暂停和选模式，无遥控驾驶。Sora 70、AquaSense X 支持 App 遥控。入水后常离线，已开始的任务一般继续。"),
    (re.compile(r"智能功能|哪些智能"),
     "Sora 10：SonicSense（11 传感器含超声波）、S 形路径、水线停靠、Beatbot App（2.4G/5G+蓝牙，含 Apple Watch）。无 AI 相机、无遥控、无水面清洁。这些在 Sora 70 / AquaSense X。"),
    (re.compile(r"防缠绕|长头发或绳子|会不会缠住"),
     "进水口水下约 25×170 mm，头发、缆绳、玩具绳可能缠进双前滚刷。下水前拿走绳子浮床。缠住后上岸清理，不要手伸进运转中的进水口。"),
    (re.compile(r"障碍物会怎么|遇到障碍"),
     "Sora 10 用 SonicSense（与 AquaSense Pro 同级避障宣传）绕开台阶、墙、玩具。不能保证 100%。AquaSense X 有 29 传感器 + AI 相机更强。大障碍请先拿走。"),
    (re.compile(r"分区清洁"),
     "Sora 10 无分区画区，靠 Floor/Wall/Standard/ECO。AquaSense X 有 AI 建图和 AI Quick 针对脏区。想少爬墙就选 Floor。"),
    (re.compile(r"清洁效率|清洁一次大约"),
     "实验室：Sora 10 仅池底最长约 5 h，底+墙+水线约 4 h，覆盖最大约 3229 sq.ft。20×40 ft 家庭池一次通常够。滤网满、水脏会变慢，5 L 尘盒满了先洗再跑。"),
    (re.compile(r"标准配件|包装清单里有充电器|耗材有哪些"),
     "Sora 10 开箱一般含主机、原装 65W 钛合金充电器、5 L/150 μm 尘盒。耗材：滤网、滚刷、履带。Sora 30/70 可另购 3 μm 细滤。清单以收到的装箱单为准。"),
    (re.compile(r"滤网堵塞"),
     "取出 5–6 L 尘盒，清水从里向外冲 150 μm 滤网，不要高压水枪。Sora 30/70 若用了 3 μm 会堵得更快。洗不净或破损再换原装。"),
    (re.compile(r"电量低|低电量"),
     "电量低时 Sora 10 会停止并水线停靠，方便捞取（不是开回岸上充电），通常不能断点续扫，需重新开始。捞出用 65W 头充约 3.5 h。Sora 30/70 有水面停靠和 App 召回。"),
    (re.compile(r"异形池|圆形|腰形|freeform|肾形"),
     "官网：各种池形均可，含矩形、圆、腰形、自由形。Sora 10 走 S 形，异形角可能漏扫，建议换出发位置再跑或配合人工。覆盖仍按约 3229 sq.ft 评估。"),
    (re.compile(r"阶梯区域|台阶"),
     "台阶容易漏扫或卡住。Sora 10 会尝试绕障，不能保证踏步面都清到。可换出发位置，或台阶改人工。浅于 12 in 的踏步 Sora 10 可能上不去。"),
    (re.compile(r"同系列其他型号|和其他型号比"),
     "Sora 10：入门，底/墙/水线，7800 mAh，5 L，2 年，约 $449，无水面无遥控。Sora 30：浅区 8 in，10000 mAh，可 3 μm。Sora 70：水面+遥控，6 L，3 年。AquaSense X：基站自清洁 22 L，3 年整机换新。"),
    (re.compile(r"落叶多|暴雨后|暴风雨后"),
     "先人工捞大枝，再下水。Sora 10 尘盒 5 L 约 650 片叶、150 μm；滤网满了就停洗。落叶季每周 3 次或隔天。只要水面漂叶加 Sora 70 或 iSkim。"),
    (re.compile(r"出水口方向"),
     "Sora 是履带+滚刷吸污，没有传统回水喷口可调方向。路线由 Floor/Wall/Standard/ECO 和 S 形规划决定。觉得冲刷不够，换模式或出发位置。"),
    (re.compile(r"清洁记录|清洁历史|本月与上月"),
     "在 Beatbot App 设备页看近期任务。Sora 10 无精细 AI 地图，记录偏任务列表。AquaSense X 建图更完整。导出/对比以 App 当前版本为准，没有就截图保存。"),
    (re.compile(r"强制关机"),
     "先在 App 或机身正常停止，捞出后再按说明书长按关机。充电中常有保护，先拔掉 65W 头。不要按住强制拆电池。"),
    (re.compile(r"多台设备如何区分"),
     "每台在 Beatbot App 里单独绑定，用备注改成「后院 Sora 10」「前院 Sora 70」。序列号在机身铭牌，不要共用一个未解绑的账号。"),
    (re.compile(r"账号绑定失败|维修回来.*配网"),
     "先确认上任账号已解绑。iPhone 打开本地网络，靠近 2.4G/5G 路由。维修后通常要重新配网。反复失败截图给 service@beatbot.com。"),
    (re.compile(r"清洁中断"),
     "常见原因：5 L 尘盒满、电量低（会水线停靠）、被台阶/排水口卡住、滤网堵。先清洗再满电重跑。App 有故障码请记下发给售后。"),
    (re.compile(r"维护保养周期"),
     "每次或隔次冲洗 150 μm 滤网；滚刷/履带看磨损（粗糙喷浆更勤）。Sora 10 无需换机油。封池季彻底沥干、电量留一半。破损滤网再换。"),
    (re.compile(r"注意事项|需要知道的注意"),
     "确认水深 0.5–3.5 m（Sora 10），拿走玩具缆绳，不要人机同池。盐水 <5000 ppm。用原装 65W 头，雷雨拔电。结束后水线停靠，及时捞出冲洗晾干。"),
    (re.compile(r"德国|法国|西班牙|意大利|英国|欧盟本地语言"),
     "欧洲可用，认准当地插头和 CE 铭牌，充电器 110–240V。App 语言以商店版本为准。售后走当地渠道；美国电话 +1 (833) 702-4399 是 CST 时段。欧盟另有冷静期和电池回收规定。"),
    (re.compile(r"工作水温|工作温度|水温过高"),
     "官网产品页未单列工作水温上下限。请以 {p} 说明书为准，常见建议避开接近冰点和极端高温。不要在冰点以下存放或充电，车库暴晒充电也不建议。"),
    (re.compile(r"水线瓷砖|水线防晒|油膜|钙垢"),
     "Sora 10 水线有约 8 秒加强刷洗，可减少污线，但防晒油膜和瓷砖钙垢往往去不干净，仍需人工或专业除垢。水面油膜请用 Sora 70 / iSkim。"),
    (re.compile(r"玻璃马赛克"),
     "过滑马赛克可能爬墙打滑。Sora 10 有双前滚刷差速，仍不保证。可先试 Wall 模式；打滑就改 Floor，墙面人工刷。"),
    (re.compile(r"胎痕|轮印"),
     "新机或深色灰泥上偶尔会有履带印，多跑几次、冲洗履带后通常减轻。持续黑印请停用并拍照给售后，不要用溶剂硬擦池面。"),
    (re.compile(r"到货破损应联系谁|运输破损"),
     "48 小时内拍外箱和破损部位，连同订单号发给购买渠道或 service@beatbot.com。官网单我们协调补发/索赔；Amazon 单也可同步开亚马逊 A-to-z。"),
    (re.compile(r"延保"),
     "官网标配：Sora 10/30 为 2 年，Sora 70 / AquaSense X 为 3 年（X 整机换新）。是否另售延保以官网或下单页为准，客服可查。"),
    (re.compile(r"免费替换滤网|滤网订阅"),
     "标配一只 150 μm 滤网，一般不默认订阅或长期免费替换。Sora 30/70 的 3 μm 细滤需另购。耗材订单走官网或 Amazon 官方店。"),
    (re.compile(r"如何注册质保"),
     "用订单号 + 机身序列号在 beatbot.com 或 App 注册。Sora 10/30 注册后按 2 年算，Sora 70 / X 按 3 年。"),
    (re.compile(r"购买凭证|是否需要.*凭证"),
     "售后/RMA 请准备订单号、序列号、购买截图（官网或 Amazon）。没有凭证会难核保，把能找到的邮箱订单转给 service@beatbot.com。"),
    (re.compile(r"RoHS|REACH|节能或生态"),
     "请认准机身/电源铭牌和欧盟文件。官网未在 Sora 10 页逐条列出 RoHS/REACH/生态设计编号，需要证书把型号和目的国发给客服索取。"),
    (re.compile(r"回收电池|电池.*回收|报废机器|环保处置"),
     "锂电池不要丢家庭垃圾桶。美国走当地电池回收点或把方案问 service@beatbot.com；欧盟按 WEEE/电池指令交售点。先在 App 解绑。"),
    (re.compile(r"删除.*账号数据|数据存储在美国还是欧盟"),
     "存储地区以 Beatbot 隐私政策为准，需要删除账号/设备数据请邮件 service@beatbot.com。二手转让先在 App 解绑。"),
    (re.compile(r"第一次清洁前应准备"),
     "充满电（Sora 10 约 3.5 h），确认 150 μm 滤网装好，配好 App，水深 0.5–3.5 m，拿走玩具浮床缆绳。盐水池确认 <5000 ppm。"),
    (re.compile(r"翻新机"),
     "质保换机可能是新机或翻新机（官网质保条款写明）。包装/铭牌与订单不一致请 48 小时内拍照给客服。自行购买请认准 Beatbot 官网或 Amazon 官方店。"),
    (re.compile(r"配件缺货"),
     "滤网、充电器缺货时可等补货，不要用第三方电源。Sora 10 与 70 尘盒不通用（5 L vs 6 L）。把型号序列号发给 service@beatbot.com 问替代件。"),
    (re.compile(r"雷雨天要不要拔"),
     "要。雷雨拔掉 65W 充电器，并取出池中的机器。不要在暴雨中充电或运行。"),
    (re.compile(r"室内充电|车库高温|遮雨棚|锂电池.*充电安全"),
     "用原装 65W（或 X 的 88W 基站），放干燥通风处，远离儿童和易燃物。不要密闭高温车库暴晒充电，也不要在浴室内无通风处长充。雷雨拔电。"),
    (re.compile(r"新铺池面养护期"),
     "新铺 plaster/水泥请等养护期结束再用，过早会伤池面也伤履带。养护天数以泳池承包商为准，常见要等数周。"),
    (re.compile(r"公共泳池"),
     "Sora/AquaSense 按家庭池设计和质保。公共/商用池面积、法规和负载通常超出 3229–3875 sq.ft 家用定位，不建议当商用设备。"),
    (re.compile(r"短租客人误操作"),
     "Airbnb 短租：不要把主人账号给客人；可共享有限权限或只由房东操作。交代必须先取出再关池盖，不要人机同池。误操作损坏可能不在保。"),
    (re.compile(r"第三方电池或充电器|自己拆机"),
     "不要用第三方电池/充电器，也不要私拆。钛合金 65W 头和电池仓在质保范围内；私拆、进液、磕碰通常不在保。"),
    (re.compile(r"长期泡在水里"),
     "不要当潜水设备长期泡着。Sora 10 虽 IPX68，清完会水线停靠，请及时捞出冲洗晾干再充电。长期浸泡加速密封和履带老化。"),
    (re.compile(r"Amazon.*正品|确认是正品"),
     "认准 Beatbot Amazon 官方旗舰店或 beatbot.com。价格异常低、无序列号、充电器非钛合金头要警惕。正品可走 30 天退货和 2/3 年质保。"),
    (re.compile(r"配件从美国仓|美国仓发货"),
     "官网/官方 Amazon 配件从美国仓发出，时效因仓库和州而异，偏远更长。查不到单号把订单号发给 service@beatbot.com。"),
    (re.compile(r"查找机器人"),
     "Sora 10 结束后水线停靠，先沿水线找。App 入水后常离线，不能当室内扫地机那样实时定位。Sora 30/70 可用 App 召回。夜间 AquaSense X 有前灯更好找。"),
    (re.compile(r"App 里能看|能看哪些状态"),
     "Beatbot App 一般能看电量、当前模式、在线/离线、任务起停。Sora 10 无 AI 地图；入水后状态常延迟。AquaSense X 建图和脏区信息更完整。"),
    (re.compile(r"滤网/耗材寿命|耗材寿命"),
     "App 若无寿命条，就按使用看：150 μm 滤网破损、洗不净再换；滚刷掉毛、履带开裂再换。Sora 10 没有官方「还剩多少小时」的耗材寿命读数。"),
    (re.compile(r"卡在泳池中间|逐步恢复"),
     "逐步：1）看是否水线停靠或电量低；2）捞出清 5 L 尘盒和进水口（约 25×170 mm）；3）查履带/台阶/排水口盖；4）岸上重启，满电后换出发位置再跑；5）仍卡拍视频给 service@beatbot.com。"),
    (re.compile(r"使用前 30 天|最终建议"),
     "前 30 天：每周 2–3 次，每次洗 5 L/150 μm 滤网，熟悉 Floor/Standard。确认水深 0.5–3.5 m、盐水 <5000 ppm。官网 30 天可退（经销商除外）。滤网勤洗比天天跑满 5 h 更重要。"),
    (re.compile(r"氯消毒|溴消毒"),
     "氯池、溴池都可用，按日常浓度。冲击加氯/加溴后等循环完成再下水。高浓度会加速密封件老化。盐水池另要求 <5000 ppm。"),
    (re.compile(r"地下矩形|地埋.*矩形|矩形泳池"),
     "可以。矩形地埋池是最典型场景。20×40 ft（约 74 m² / 800 sq.ft）Sora 10 一次通常够。S 形路径对矩形更友好。仍要满足 0.5–3.5 m 水深。"),
    (re.compile(r"充电器应该放|放在户外遮雨"),
     "放干燥岸上、儿童够不到处，可用遮雨棚但不要淋雨或泡水。美国泳池边建议 GFCI。雷雨拔掉 65W 头。不要用非原装延长线泡在水边。"),
    (re.compile(r"美国插座|110.?120"),
     "可以。Sora 充电器 110–240V，美国 120V 插座直接用原装头。泳池边建议 GFCI。欧洲用当地插头版本，不要只靠旅行转换头。"),
    (re.compile(r"包装清单有哪些|是否含滤网"),
     "Sora 10 一般含主机、65W 钛合金充电器、已装的 5 L/150 μm 尘盒/滤网。以装箱单为准。3 μm 细滤不是 Sora 10 标配（Sora 30/70 可另购）。"),
    (re.compile(r"滤网多久清洗|怎么拆洗"),
     "建议每次或隔次清洗：从顶部取出 5–6 L 尘盒，清水从里向外冲 150 μm 滤网，晾干装回。不要洗碗机或高压水枪。"),
    (re.compile(r"哪里买替换滤网|哪里买配件"),
     "beatbot.com 或 Amazon Beatbot 官方店。美国仓发货；欧洲看当地站点或官方店。Sora 10 用 150 μm / 5 L，不要买 Sora 70 的 6 L 盒硬套。"),
    (re.compile(r"为什么中途停住"),
     "常见：尘盒满、电量低（Sora 10 会水线停靠）、被卡住、滤网堵。先洗 5 L 盒、检查缠绕和电量，满电换位再跑。"),
    (re.compile(r"翻车或浮起来|翻车|上浮"),
     "吸入气袋、浅于 12 in（Sora 10）、瀑布气泡干扰或滤网极堵可能抬头/上浮。关掉水景，确认水深，清洗滤网。反复翻车拍视频给售后。"),
    (re.compile(r"首次配网|如何.*配网|重新配网|换路由器"),
     "打开 Beatbot App，按说明书加设备。Sora 10 支持 2.4G/5G + 蓝牙。iPhone 打开本地网络；换路由后要重新配。Mesh 失败请靠近主路由。"),
    (re.compile(r"恢复出厂"),
     "在 App 设备设置或按说明书组合键恢复出厂，然后重新配网。会清掉绑定和预约。二手转让前必须做。操作以 {p} 说明书为准。"),
    (re.compile(r"夏季高峰|高峰期建议多久"),
     "夏季建议每周 2–3 次，落叶/派对后加跑。Sora 10 满电底约 5 h，天热电池略缩。不必每天跑满，滤网勤洗更关键。"),
    (re.compile(r"池壁藻类|先人工刷壁"),
     "轻薄藻可先人工刷再让机器收脱落物。Sora 10 能爬墙刷水线，但不能当除藻剂。绿水/片状藻先调水质。细死藻粉可看 Sora 30/70 的 3 μm 滤网。"),
    (re.compile(r"建图或学习|会建图"),
     "Sora 10 不建 AI 地图，靠 SonicSense + S 形路径，不会「越用越熟」。AquaSense X 有 HybridSense AI 建图和脏区规划。"),
    (re.compile(r"从水中取出|打捞钩|提手"),
     "Sora 10 清完水线停靠约 10 分钟，沿水线用手（或提手位置）捞出，官网宣传不必深水捞。没有单独打捞钩标配。先停机再伸手，不要碰运转履带。"),
    (re.compile(r"美国配件发货|欧洲配件发货|发货要多久"),
     "官网/官方 Amazon 美国仓发货，时效因仓库和州而异。欧洲看当地站点。查不到单号把订单号发给 service@beatbot.com。"),
    (re.compile(r"亚马逊买|amazon.*滤网"),
     "可以在 Amazon Beatbot 官方店买 150 μm 滤网。认准官方店以免尺寸不对。Sora 10 是 5 L 盒，不要买 Sora 70 的 6 L。"),
    (re.compile(r"滤网总是很快满"),
     "5 L / 150 μm 在落叶季、刚絮凝或池很脏时会很快满，属正常。先人工捞大叶，水质稳定后再跑。要收更细粉尘用 Sora 30/70 的 3 μm（会更快满）。"),
    (re.compile(r"开池季|第一天要先人工"),
     "开池第一天建议先人工捞大污、检测水质，再让机器人跑。Sora 10 一次约 650 片叶，开池堆积物经常超过这个量。"),
    (re.compile(r"另购电池|电池大概用几个|用户可更换"),
     "电池在质保范围内（Sora 10/30 为 2 年，Sora 70 / X 为 3 年）。用户不建议自行更换，私拆通常不在保。能否另购电池请把序列号问 service@beatbot.com。泳季寿命因使用次数而异。"),
    (re.compile(r"深色池底|夜间清洁"),
     "Sora 10 靠超声波避障，深色池底一般不影响 S 形路径。它没有夜视灯。AquaSense X 有双 1500 Lx 前灯和夜间清洁。Sora 夜间也能跑，只是不好找、不好看覆盖。"),
    (re.compile(r"充电座安装|预留多大空间"),
     "Sora 10/30 没有充电座，岸上插 65W 钛合金头即可，放干燥遮雨处。AquaSense X 才有 AstroRinse 基站（渠道尺寸约 25.1×21.1×22.0 in），需留取放和排水空间，按说明书安装，注意防雨。"),
    (re.compile(r"清洁提醒|隔天自动|自动清洁"),
     "在 Beatbot App 设预约/提醒。Sora 是无线机，预约当天要已放入泳池且有电（Sora 10 满电底约 5 h）。AquaSense X 可从基站自动出发。"),
    (re.compile(r"加热器|开着加热"),
     "加热开着一般可以同时清洁，水流可能影响路线。水温上限官网未公布，极端高温请先看说明书。关掉强力喷口更稳。"),
    (re.compile(r"传感器.*清理|叶轮|进水口怎么清理"),
     "停机捞出后，清进水口（水下约 25×170 mm）、叶轮和超声波窗口，不要用螺丝刀撬叶片。清水冲洗，不要高压水枪冲传感器。"),
    (re.compile(r"滚刷缠了|头发或皮筋"),
     "先停机断电，从双前滚刷上慢慢取头发/皮筋，不要开着机掏。进水口约 25×170 mm 也要检查。剪不断就拍照问客服，避免拉坏滚刷。"),
    (re.compile(r"正确朝向|出发方向"),
     "Sora 10 放入后一般自行定向走 S 形，没有必须对准的出发朝向。建议从较深、障碍少的一侧放入。选 Floor 或 Standard 即可。"),
    (re.compile(r"一台 App|两台设备|两台一起"),
     "一台 App 可绑定多台，用备注区分。两台同时清大池可以，注意不要撞、滤网各自洗。Sora 10 单机覆盖约 3229 sq.ft，超大池双机或改 AquaSense X 更合适。"),
]


def draft_cs_answer(question: str, qtype: str | None = None) -> str:
    """按题目具体内容生成客服参考答案，避免只套大类套话。"""
    q = str(question or "").strip()
    kind = qtype or classify_question(q)
    for pat, ans in _ANSWER_RULES:
        if pat.search(q):
            return ans
    return _compose_cs_answer(q, kind)


def _facts_for_kind(kind: str) -> str:
    """兜底答案也带官网数字，避免空泛。"""
    return {
        "规格参数": "官网：Sora 10 水深 0.5–3.5 m、覆盖约 3229 sq.ft、7800 mAh、池底约 5 h、充电约 3.5 h/65W、5 L/150 μm、6800 GPH、8.5 kg、IPX68。",
        "售前选型": "选型：只要底/墙/水线选 Sora 10（约 3229 sq.ft，2 年）；浅台低于 12 in 选 Sora 30/70（8 in）；要水面选 Sora 70；要基站自清洁选 AquaSense X。",
        "质保服务": "官网：Sora 10/30 为 2 年，Sora 70 为 3 年，AquaSense X 为 3 年整机换新；另有 30 天退货（经销商除外）。",
        "售后物流": "美国客服 service@beatbot.com，+1 (833) 702-4399，9:00–18:00 CST。请带订单号和序列号。",
        "配件耗材": "Sora 10 尘盒 5 L/150 μm；Sora 30 约 5.2 L 可加 3 μm；Sora 70 为 6 L 可加 3 μm。请买原装。",
        "安装电源": "Sora 充电器 65W、110–240V 钛合金头；AquaSense X 基站约 88W 无线充。美国泳池边建议 GFCI。",
        "App账号": "Sora 支持 2.4G/5G Wi-Fi + 蓝牙（Sora 10：Wi-Fi 约 40 m，蓝牙约 20 m），App 为 iOS/Android，Sora 10 还写了 Apple Watch。",
        "适用场景": "官网材料：混凝土/瓷砖/乙烯基/玻璃钢，地埋/地上均可；盐水 <5000 ppm。Sora 10 水深 0.5–3.5 m。",
        "水质化学": "盐水须 <5000 ppm。冲击加氯后等浓度回到日常再下水。绿水不能单靠机器人。",
        "清洁策略": "日常每周 2–3 次。Sora 10 模式：Floor/Wall/Standard/ECO；满电池底约 5 h，全清洁约 4 h。",
        "设备控制": "机身键或 Beatbot App 启动。Sora 10 无遥控；Sora 70 / AquaSense X 支持遥控。",
        "安全合规": "清洁时不要下水。充电器 110–240V，认准 UL/CE/FCC 铭牌。不要高压水枪冲充电口。",
        "维护保养": "每次或隔次冲洗 150 μm 滤网，开口朝下晾干。封池留约一半电，防冻存放。",
        "故障排查": "先查电量、5 L 尘盒、履带缠绕和 App 故障码。复现请拍视频给 service@beatbot.com。",
        "季节气候": "雷雨先取出并拔电。落叶/花粉季加密清洁，Sora 10 的 5 L 尘盒满了就洗。",
        "隐私账号": "解绑在 App 设备设置。删号或隐私问题邮件 service@beatbot.com。",
        "日常使用": "放入泳池后 App 或机身启动，先拿走玩具浮床。Sora 10 结束后水线停靠方便捞取。",
    }.get(kind, "官网对照 Sora 10：0.5–3.5 m，3229 sq.ft，7800 mAh，池底约 5 h，5 L/150 μm，6800 GPH，2 年质保。客服 service@beatbot.com。")


def _compose_cs_answer(q: str, kind: str) -> str:
    topic = re.sub(r"\{p\}|关于\s*|使用 \{p\} 时|正确做法是什么？|官方建议怎么做？|会不会影响.*", "", q)
    topic = re.sub(r"[？?。]+$", "", topic).strip(" ，,")
    topic = re.sub(r"\s+", " ", topic)
    if len(topic) > 36:
        topic = topic[:36].rstrip()
    fact = _facts_for_kind(kind)
    if re.search(r"怎么办|怎么排查|先查什么|先排查", q):
        return f"针对「{topic}」：先看电量、150 μm 滤网是否满、双前滚刷/履带有无缠绕、台阶或排水口盖。能复现就拍视频，连同型号发给 service@beatbot.com。{fact}"
    if re.search(r"怎么|如何|怎样", q):
        return f"关于「{topic}」：按 {p_hint()}说明书或 Beatbot App 操作（Sora 10 模式在 Floor/Wall/Standard/ECO）。页面不一致请截图给客服。{fact}"
    if re.search(r"能不能|能否|可以|支持吗|安全吗", q):
        return f"「{topic}」要看具体型号和泳池条件。Sora 系列支持混凝土/乙烯基/玻璃钢/瓷砖，盐水 <5000 ppm，Sora 10 水深 0.5–3.5 m。把泳池照片发给客服确认。{fact}"
    if re.search(r"适合|推荐", q):
        return f"是否适合「{topic}」，先对照水深 0.5–3.5 m（Sora 10）、面积约 3229 sq.ft、有无低于 12 in 的浅台和是否要清水面。{fact}"
    if kind == "售后物流":
        return f"关于「{topic}」：准备订单号和序列号，联系 service@beatbot.com 或 +1 (833) 702-4399（9–18 CST）。需要时附照片。{fact}"
    if kind == "质保服务":
        return f"关于「{topic}」：Sora 10/30 官网 2 年，Sora 70 为 3 年，AquaSense X 为 3 年整机换新；耗材和人为损坏通常不在保。把订单号发给客服查。{fact}"
    if kind == "故障排查":
        return f"出现「{topic}」时，先清洗 5 L 尘盒、检查缠绕和电量，再看 App 故障码。仍无法恢复请拍视频联系售后。{fact}"
    return f"关于「{topic}」：请结合说明书和 App。需要准确结论时把型号、序列号和现场情况发给 service@beatbot.com。{fact}"


def p_hint() -> str:
    return "{p} "


def _templates_from_xlsx(
    path: Path,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    if library not in wb.sheetnames:
        raise ValueError(f"{path.name} 里没有工作表「{library}」，现有: {wb.sheetnames}")
    ws = wb[library]
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    wb.close()
    if not rows:
        return []
    headers = [str(h or "").strip() for h in rows[0]]
    enabled_i = headers.index("启用") if "启用" in headers else 0
    type_i = headers.index("问题类型") if "问题类型" in headers else None
    question_i = None
    for name in ("问题", "第1轮"):
        if name in headers:
            question_i = headers.index(name)
            break
    if question_i is None:
        question_i = 3 if "问题类型" in headers else (2 if len(headers) > 2 else 1)
    wanted = {t.strip() for t in (types or []) if str(t).strip()}
    out: list[str] = []
    for row in rows[1:]:
        if not row or not _row_enabled(row[enabled_i] if enabled_i < len(row) else ""):
            continue
        if wanted and type_i is not None:
            kind = str(row[type_i] or "").strip() if type_i < len(row) else ""
            if kind not in wanted:
                continue
        q = str(row[question_i] or "").strip() if question_i < len(row) else ""
        if q:
            out.append(q)
    return out


def _templates_from_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    if isinstance(data, dict):
        func = (data.get("libraries") or {}).get("functional") or {}
        raw = func.get("questions") or []
        out = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                q = str(item.get("question") or item.get("text") or "").strip()
                if q:
                    out.append(q)
        return out
    raise ValueError(f"问题模板须为数组或分层对象: {path}")


def resolve_templates_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    if QUESTION_TEMPLATES_XLSX.is_file():
        return QUESTION_TEMPLATES_XLSX
    return QUESTION_TEMPLATES_JSON


def load_question_templates(
    path: Path | None = None,
    *,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> list[str]:
    """优先读 config/测试题库.xlsx，没有再回退 JSON。"""
    path = resolve_templates_path(path)
    if not path.is_file():
        raise FileNotFoundError(f"缺少问题模板: {path}")
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        out = _templates_from_xlsx(path, library, types=types)
    else:
        out = _templates_from_json(path)
    if not out:
        raise ValueError(f"问题模板无有效条目: {path}")
    return out


def _attach_product(tpl: str, product: str) -> str:
    """模板里没写产品名时补上。

    题库有一部分是从 FAQ 直接抄来的通用问法（如「如何设置自清洁习惯？」），
    这样问 Agent 只会反问「请补充产品型号」，测不出东西。
    """
    if product.lower() in tpl.lower():
        return tpl
    if _ZH_CHAR.search(tpl):
        return f"关于 {product}，{tpl.lstrip('，,')}"
    return f"For {product}: {tpl}"


def templates_for_language(templates: list[str], language: str) -> list[str]:
    """按提问语言挑模板，避免中文场次混进英文题。"""
    lang = (language or "").strip().lower()
    want_zh = not lang or "中文" in language or lang.startswith("zh")
    picked = [t for t in templates if bool(_ZH_CHAR.search(t)) == want_zh]
    return picked or list(templates)


def question_pool(
    language: str = "中文",
    *,
    path: Path | None = None,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> list[str]:
    """打乱后的题库。打乱是为了让每个产品拿到的题目覆盖各个主题，
    而不是按原文件顺序全挤在「水深/续航」这一类基础题上。"""
    pool = templates_for_language(
        load_question_templates(path, library=library, types=types),
        language,
    )
    random.Random(SHUFFLE_SEED).shuffle(pool)
    return pool


def generate_questions(
    product: str,
    count: int = 100,
    *,
    index: int = 0,
    language: str = "中文",
    pool: list[str] | None = None,
    templates_path: Path | None = None,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> list[str]:
    """为单个产品生成不重复问题（完整产品名入句）。

    index 是产品序号：每个产品从题库的不同位置取题，
    这样不同产品问的是不同问题，而不是同一批题换个名字。
    count <= 0 表示不限量，把整个题库都问一遍。
    """
    product = product.strip()
    if not product:
        raise ValueError("产品名为空")

    templates = (
        list(pool)
        if pool is not None
        else question_pool(language, path=templates_path, library=library, types=types)
    )
    if count <= 0:
        count = len(templates)
    if count <= 0:
        return []
    if templates:
        start = (index * count) % len(templates)
        templates = templates[start:] + templates[:start]
    seen: set[str] = set()
    out: list[str] = []

    def _add(q: str) -> bool:
        q = re.sub(r"\s+", " ", q).strip()
        if not q or q in seen:
            return False
        seen.add(q)
        out.append(q)
        return True

    for tpl in templates:
        if len(out) >= count:
            break
        if "{p}" in tpl:
            _add(tpl.format(p=product))
        else:
            _add(_attach_product(tpl, product))

    suffixes = [
        "请根据官方资料回答。",
        "请给出关键参数。",
        "请用简明步骤说明。",
        "如果资料不足请明确说明。",
        "请区分产品资料与通用建议。",
    ]
    extras = [
        "工作电压",
        "适配电源",
        "遥控距离",
        "防水等级",
        "充电座安装",
        "滤网型号",
        "滚刷型号",
        "App 兼容系统",
        "固件更新频率",
        "质保年限",
        "是否含税",
        "是否支持预约",
        "边缘清洁能力",
        "转弯半径",
        "坡度适应",
        "线缆长度",
        "指示灯含义",
        "错误码列表",
        "耗材购买渠道",
        "官方客服入口",
    ]
    i = 0
    while len(out) < count:
        base = extras[i % len(extras)]
        suf = suffixes[(i // len(extras)) % len(suffixes)]
        round_id = i // (len(extras) * len(suffixes)) + 1
        q = f"{product} 的{base}是什么？{suf}"
        if round_id > 1:
            q = f"{product} 关于{base}还需要补充说明吗？（第{round_id}组）{suf}"
        if not _add(q):
            tag = hashlib.md5(f"{product}-{i}".encode()).hexdigest()[:6]
            _add(f"{product} 还有哪些与{base}相关的注意事项？[{tag}]")
        i += 1
        if i > count * 20:
            break

    if len(out) < count:
        raise RuntimeError(f"{product} 仅生成 {len(out)}/{count} 题，请补充模板。")
    return out[:count]


def generate_all_questions(
    products: Iterable[str],
    per_product: int = 100,
    *,
    language: str = "中文",
    coverage: str = "split",
    product_index: int | None = None,
    templates_path: Path | None = None,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> list[tuple[str, str]]:
    """coverage=split：各产品取题库的不同片段，合起来覆盖整个题库；
    coverage=full：每个产品都把题库问一遍，产品之间可横向对比同一道题。

    product_index：并行时每个进程只带一个产品，用这个序号取正确的 split 片段。
    """
    pool = question_pool(language, path=templates_path, library=library, types=types)
    rows: list[tuple[str, str]] = []
    for i, p in enumerate(products):
        if coverage == "full":
            index = 0
        elif product_index is not None:
            index = product_index
        else:
            index = i
        for q in generate_questions(p, per_product, index=index, pool=pool):
            rows.append((p, q))
    return rows


def parse_products(text: str) -> list[str]:
    all_products = load_products()
    if not (text or "").strip():
        return list(all_products)
    parts = [p.strip() for p in re.split(r"[,，、]", text) if p.strip()]
    return parts or list(all_products)
