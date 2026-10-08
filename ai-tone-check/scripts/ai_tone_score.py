#!/usr/bin/env python3
"""给中文文本做 AI 味体检：分层命中、句长波动、相邻句复读、具体性与排版计数、
可疑段落排序；--diff 对改写稿与原稿做事实保全校验。排名与计数只用于定位，不做判决。

用法：
    python3 ai_tone_score.py 文件.md [文件2 ...]
    python3 ai_tone_score.py -                    # 从 stdin 读
    python3 ai_tone_score.py --json 文件.md       # JSON 输出
    python3 ai_tone_score.py --diff 原稿 改写稿   # 保全校验
    python3 ai_tone_score.py --diff 原稿 改写稿 --strict   # 有增删时退出码 1
    python3 ai_tone_score.py --self-test

脚本判断不了文字是否自然，更判断不了作者身份；逐条结合语境复核，以全文连读为准。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

TIER_STRUCT = "结构"
TIER_LEX = "词汇"
TIER_WEIGHT = {TIER_STRUCT: 2, TIER_LEX: 1}

SIGNALS = tuple(
    (name, tier, re.compile(pattern))
    for name, tier, pattern in (
        # ---- 结构层（跨模型稳定，优先处理） ----
        (
            "宏大开场",
            TIER_STRUCT,
            r"^(?:随着|在)(?:当今|这个|数字化|人工智能|科技|信息|互联网|AI)?.{0,32}(?:时代|浪潮|背景下|大背景下|今天|当下|快速发展|飞速发展|不断发展)",
        ),
        (
            "万能升华结尾",
            TIER_STRUCT,
            r"尽管.{0,24}(?:挑战|困难|不足).{0,24}(?:仍|依然)|未来(?:可期|值得期待)|必将(?:迎来|更加|发挥|成为)|相信.{0,8}(?:必将|终将|会更好)",
        ),
        (
            "意义拔高",
            TIER_STRUCT,
            r"[，,].{0,8}(?:体现|彰显|凸显|展现)了|为.{1,24}(?:奠定(?:了)?(?:坚实的?)?基础|注入(?:了)?(?:新的?)?(?:活力|动力))|保驾护航|添砖加瓦",
        ),
        # ---- 词汇层（随模型漂移，聚簇才处理） ----
        (
            "重要性膨胀",
            TIER_LEX,
            r"至关重要|不可忽视|不容忽视|深远影响|深远意义|具有重要意义|举足轻重",
        ),
        (
            "标志与开启",
            TIER_LEX,
            r"标志(?:着|了)|开启(?:了)?(?:全新|崭新|新的?)篇章|迈出了?(?:重要|关键|坚实)的一步",
        ),
        (
            "模糊归因",
            TIER_LEX,
            r"(?:有|相关|多项|大量)?研究(?:均)?(?:表明|显示|指出)|业内(?:普遍)?(?:认为|指出)|"
            r"学界(?:普遍)?(?:认为|指出)|专家(?:普遍)?(?:认为|表示|指出)|众所周知|数据显示",
        ),
        (
            "并列堆砌",
            TIER_LEX,
            r"(?:[\u4e00-\u9fffA-Za-z0-9]{1,12}、){2,}[\u4e00-\u9fffA-Za-z0-9]{1,12}",
        ),
        ("悬浮式连接", TIER_LEX, r"(?:从而|进而|由此|借此)(?:实现|确保|体现|达到|完成|推动|促进|助力)"),
        (
            "抽象主语",
            TIER_LEX,
            r"(?:时代|科技|人工智能|未来|行业|社会|现实)(?:的)?(?:浪潮|洪流|发展|进步)?(?:正在|要求我们|呼唤|迫使|推动着?|重塑)",
        ),
        ("程度副词", TIER_LEX, r"非常|十分|极其|极为|相当|特别|格外|尤其|真的|确实|的确|实在|无比|尤为"),
        (
            "翻译腔",
            TIER_LEX,
            r"对于.{1,18}(?:来说|而言)|使得.{1,24}(?:得以|成为可能)|作为一(?:个|名|种|位).{0,18}[，,、]",
        ),
        (
            "万能动词",
            TIER_LEX,
            r"(?:进行|加以|予以|作出)(?:了)?(?:深入|全面|进一步|仔细|系统)?的?"
            r"(?:分析|研究|处理|优化|调整|改造|讨论|评估|梳理|总结|改进|回应)",
        ),
        (
            "讲义腔路标",
            TIER_LEX,
            r"首先.{0,60}其次|其次.{0,60}(?:再次|最后)|综上所述|总的来说|总而言之|由此可见|"
            r"不难(?:看出|发现)|值得注意的是|值得一提的是|需要指出的是|毋庸置疑",
        ),
        (
            "二分强调",
            TIER_LEX,
            r"不是.{1,24}?而是|不在于.{1,24}?而在于|不仅.{1,24}?(?:更|也|还|而且)是|与其说.{1,24}?不如说",
        ),
        ("黑话", TIER_LEX, r"赋能|抓手|闭环|底层逻辑|颗粒度|组合拳|护城河|第二曲线|价值锚点|生态位|降本增效|拉通对齐"),
        (
            "路标句",
            TIER_LEX,
            r"话不多说|(?:接下来|下面)(?:我们|咱们)?(?:一起|来)?(?:深入)?(?:探讨|了解|看看|分析)|"
            r"本文(?:将)?(?:从|分).{1,12}(?:方面|部分|维度)|以下是(?:你|您|大家)?(?:需要|要)?(?:知道|了解)",
        ),
        (
            "对话残留",
            TIER_LEX,
            r"希望.{0,12}(?:对你有帮助|有所帮助)|(?:如果您|如果你)还想(?:了解|知道)|"
            r"以下是关于.{0,24}(?:概述|介绍|总结)|当然可以[！!]",
        ),
        ("假坦诚", TIER_LEX, r"(?:^|[。！？；])(?:说实话|讲真|坦白讲|这么说吧)[，,]"),
        ("变更叙事", TIER_LEX, r"新增.{0,24}(?:用于|以便)(?:替代|取代)|替代了(?:之前|原有的?)|相比(?:旧版|之前的?版本)"),
        (
            "金句收尾",
            TIER_LEX,
            r"这(?:才|就)是(?:真正|最好)的|这(?:才|就)是.{0,10}(?:的力量|的意义|的答案)|唯有.{0,12}方能|让我们(?:共同|一起)|愿我们",
        ),
    )
)

ABSTRACT_MARKERS = re.compile(
    r"至关重要|不可或缺|不可忽视|意义|价值|关键|核心|本质|趋势|未来|格局|里程碑|标志着|意味着|本质上|归根结底"
)
HAN = re.compile(r"[\u4e00-\u9fff]")
SENTENCE_SPLIT = re.compile(r"[。！？；!?;]+")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")
HALFWIDTH_AFTER_HAN = re.compile(r"[\u4e00-\u9fff][,;:.!?]")

STOP_BIGRAMS = frozenset(
    "我们 你们 他们 她们 这个 那个 这些 那些 一个 一种 一些 一样 这种 那种 可以 可能 需要 能够 "
    "因为 所以 如果 但是 而且 以及 或者 不是 就是 还是 已经 正在 通过 对于 关于 由于 时候 什么 "
    "怎么 这样 那样 非常 很多 那么 于是 因此 然后 同时 此外 并且 只是 相比 例如 比如 包括 其中 "
    "之一 没有 不会 不能 不同 进行 具有 成为 作为 为了 无论 虽然 尽管 只要 只有 而是 无法 得到 "
    "实现 提升 优化 相关 什么 这些 内容 方式 情况 方面 过程 问题 结果 开始 继续 仍然 依然 也是 "
    "的是 是一 一个 上 的 了 是".split()
)


@dataclass
class Para:
    number: int
    start_line: int
    end_line: int
    text: str
    han: int
    signals: list[tuple[str, str]] = field(default_factory=list)  # (name, tier)


def han_count(text: str) -> int:
    return len(HAN.findall(text))


def abstract_opener(text: str) -> bool:
    """段首第一句是不含数字/英文/引号的短抽象判断——零回指评论的启发式近似。"""
    first = SENTENCE_SPLIT.split(text, 1)[0]
    if han_count(first) > 20 or re.search(r"\d|[A-Za-z]", first):
        return False
    if "「" in first or "“" in first or "『" in first:
        return False
    return bool(ABSTRACT_MARKERS.search(first))


def find_signals(text: str) -> list[tuple[str, str]]:
    return [(name, tier) for name, tier, pattern in SIGNALS if pattern.search(text)]


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join([""] * (i + 1) + lines[i + 1:])
    return text


def strip_fences(text: str) -> str:
    """把代码围栏替换成空行，保持原有行号。"""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            out.append("")
            continue
        out.append("" if inside else line)
    return "\n".join(out)


def paragraphs(text: str) -> list[Para]:
    result: list[Para] = []
    buffer: list[str] = []
    start = 1

    def flush(end: int) -> None:
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        if body and not body.startswith("#") and not body.startswith("|"):
            signals = find_signals(body)
            if abstract_opener(body):
                signals.append(("段首抽象评论(启发式)", TIER_STRUCT))
            result.append(Para(len(result) + 1, start, end, body, han_count(body), signals))
        buffer.clear()

    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if line.strip():
            if not buffer:
                start = i
            buffer.append(line)
        else:
            flush(i - 1)
    flush(len(lines))
    return result


def sentence_lengths(text: str) -> list[int]:
    lengths = []
    for chunk in SENTENCE_SPLIT.split(text):
        n = han_count(chunk)
        if n >= 1:
            lengths.append(n)
    return lengths


def bigrams(sentence: str) -> set[str]:
    return {
        sentence[i : i + 2]
        for i in range(len(sentence) - 1)
        if HAN.match(sentence[i]) and HAN.match(sentence[i + 1])
    }


def repetition_pairs(paras: list[Para]) -> list[tuple[int, list[str]]]:
    hits: list[tuple[int, list[str]]] = []
    for para in paras:
        sentences = [c for c in SENTENCE_SPLIT.split(para.text) if han_count(c) >= 4]
        for a, b in zip(sentences, sentences[1:]):
            common = sorted({g for g in bigrams(a) & bigrams(b) if g not in STOP_BIGRAMS})
            if common:
                hits.append((para.number, common[:4]))
    return hits


def typography_counts(text: str) -> dict[str, int]:
    return {
        "破折号——": text.count("——"),
        "弯引号": text.count("“") + text.count("”"),
        "直角引号": text.count("「") + text.count("」"),
        "加粗对": text.count("**") // 2,
        "emoji": len(EMOJI.findall(text)),
        "汉字后半角标点": len(HALFWIDTH_AFTER_HAN.findall(text)),
    }


def specificity_counts(text: str) -> dict[str, int]:
    return {
        "数字": len(re.findall(r"\d+(?:[.,]\d+)*%?", text)),
        "日期": len(re.findall(r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?", text)),
        "百分比": len(re.findall(r"\d+(?:\.\d+)?%", text)),
        "英文词": len(re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{1,40}", text)),
        "链接": len(re.findall(r"https?://\S+", text)),
        "引注": len(re.findall(r"「[^」]{1,160}」", text)) + len(re.findall(r"“[^”]{1,160}”", text)),
    }


def analyze(name: str, text: str) -> dict:
    body = strip_fences(strip_frontmatter(text))
    total_han = han_count(body)
    paras = paragraphs(body)

    counts: dict[str, dict[str, int]] = {TIER_STRUCT: {}, TIER_LEX: {}}
    weighted_hits = 0
    for para in paras:
        seen: set[str] = set()
        for signal, tier in para.signals:
            if signal in seen:
                continue
            seen.add(signal)
            counts[tier][signal] = counts[tier].get(signal, 0) + 1
            weighted_hits += TIER_WEIGHT[tier]

    lengths = sentence_lengths(body)
    if len(lengths) >= 3:
        mean = sum(lengths) / len(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0.0
        sentence_stats = {
            "count": len(lengths),
            "min": min(lengths),
            "max": max(lengths),
            "ratio": round(max(lengths) / min(lengths), 2) if min(lengths) else None,
            "mean": round(mean, 1),
            "cv": round(cv, 2),
        }
    else:
        sentence_stats = {"count": len(lengths)}

    ranked = sorted(
        (p for p in paras if p.signals),
        key=lambda p: (
            sum(TIER_WEIGHT[t] for _, t in p.signals) * 1000 / p.han if p.han else 0.0
        ),
        reverse=True,
    )
    suspects = []
    for para in ranked[:5]:
        density = sum(TIER_WEIGHT[t] for _, t in para.signals) * 1000 / para.han if para.han else 0.0
        excerpt = para.text.replace("\n", " ")
        if len(excerpt) > 60:
            excerpt = excerpt[:60] + "…"
        suspects.append(
            {
                "number": para.number,
                "lines": [para.start_line, para.end_line],
                "density": round(density, 1),
                "signals": [s for s, _ in para.signals],
                "excerpt": excerpt,
            }
        )

    avg_para = round(total_han / len(paras), 1) if paras else 0
    repetition = repetition_pairs(paras)
    return {
        "file": name,
        "han": total_han,
        "paragraphs": len(paras),
        "avg_para_han": avg_para,
        "signals": {
            "struct": counts[TIER_STRUCT],
            "lex": counts[TIER_LEX],
            "weighted_hits": weighted_hits,
            "weighted_per_1000": round(weighted_hits * 1000 / total_han, 1) if total_han else 0.0,
        },
        "sentences": sentence_stats,
        "repetition": {
            "pairs": len(repetition),
            "examples": repetition[:5],
        },
        "typography": typography_counts(body),
        "specificity": specificity_counts(body),
        "suspects": suspects,
    }


def render_text(result: dict) -> str:
    out: list[str] = [
        f"文件: {result['file']}",
        f"汉字: {result['han']}，段落: {result['paragraphs']}（平均每段 {result['avg_para_han']} 字）",
    ]

    out.append("")
    out.append("维度命中（结构层权重 2，词汇层权重 1）")
    signals = result["signals"]
    printed = False
    for tier, label in ((TIER_STRUCT, "结构"), (TIER_LEX, "词汇")):
        if signals["struct" if tier == TIER_STRUCT else "lex"]:
            printed = True
            out.append(f"  {label}层:")
            for name, count in sorted(
                signals["struct" if tier == TIER_STRUCT else "lex"].items(),
                key=lambda kv: (-kv[1], kv[0]),
            ):
                out.append(f"    {name}\t{count}")
    if printed:
        out.append(f"  合计加权 {signals['weighted_hits']} 处，约每千字 {signals['weighted_per_1000']} 处")
    else:
        out.append("  （无）")

    out.append("")
    out.append("句长")
    sentences = result["sentences"]
    if sentences.get("count", 0) >= 3:
        out.append(
            f"  句数 {sentences['count']}，最长 {sentences['max']} 字，最短 {sentences['min']} 字，"
            f"最长÷最短 {sentences['ratio']}，均长 {sentences['mean']} 字，波动 CV {sentences['cv']}"
        )
        if sentences["ratio"] is not None and sentences["ratio"] < 2.5:
            out.append("  提示：句长偏均匀，人类写作的最长÷最短通常在 3 倍以上")
    else:
        out.append("  （句子太少，跳过）")

    out.append("")
    out.append("复读检查（相邻句共用 2 字词组，启发式；专名重复正常）")
    repetition = result["repetition"]
    if repetition["pairs"]:
        out.append(f"  相邻句共用词组 {repetition['pairs']} 处，示例：")
        for number, grams in repetition["examples"]:
            out.append(f"    第 {number} 段：{'、'.join(grams)}")
    else:
        out.append("  （无）")

    out.append("")
    out.append("排版计数（弱信号，须与其他证据聚簇）")
    for name, count in result["typography"].items():
        out.append(f"  {name}\t{count}")

    out.append("")
    out.append("具体性计数（低计数只是线索，不是判决）")
    for name, count in result["specificity"].items():
        out.append(f"  {name}\t{count}")

    out.append("")
    out.append("可疑段落（按加权密度排序，只用于定位）")
    if result["suspects"]:
        for item in result["suspects"]:
            out.append(
                f"  第 {item['number']} 段（行 {item['lines'][0]}-{item['lines'][1]}）"
                f"密度 {item['density']}：{'、'.join(item['signals'])}"
            )
            out.append(f"    > {item['excerpt']}")
    else:
        out.append("  （无命中）")
    return "\n".join(out)


# ---------------- 保全校验 ----------------

FACT_PATTERNS = {
    "数字": r"\d+(?:[.,]\d+)*%?",
    "日期": r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?",
    "引文": None,  # 单独处理（提取引号内文）
    "链接": r"https?://[^\s)>\]]+",
    "路径": r"(?:\.{0,2}/)?(?:[\w\u4e00-\u9fff.-]+/)+[\w\u4e00-\u9fff.-]+\.\w{1,12}",
    "行内代码": r"`([^`\n]{1,120})`",
}


def extract_facts(text: str) -> dict[str, list[str]]:
    facts: dict[str, list[str]] = {}
    for name in ("数字", "日期", "链接", "路径"):
        facts[name] = re.findall(FACT_PATTERNS[name], text)
    facts["引文"] = [q.strip().rstrip("。！？；，、") for q in re.findall(r"「([^」]{1,200})」", text)]
    facts["引文"] += [q.strip().rstrip("。！？；，、") for q in re.findall(r"“([^”]{1,200})”", text)]
    facts["行内代码"] = [c.strip() for c in re.findall(FACT_PATTERNS["行内代码"], text)]
    return facts


def diff_facts(before: str, after: str) -> dict:
    fa, fb = extract_facts(before), extract_facts(after)
    report: dict[str, dict] = {}
    changed = 0
    for name in ("数字", "日期", "引文", "链接", "路径", "行内代码"):
        sa, sb = set(fa[name]), set(fb[name])
        removed, added = sorted(sa - sb), sorted(sb - sa)
        report[name] = {
            "before": len(fa[name]),
            "after": len(fb[name]),
            "removed": removed,
            "added": added,
        }
        changed += len(removed) + len(added)
    fences_a = len(re.findall(r"(?m)^```", before)) // 2
    fences_b = len(re.findall(r"(?m)^```", after)) // 2
    report["代码块"] = {"before": fences_a, "after": fences_b, "removed": [], "added": []}
    if fences_a != fences_b:
        changed += 1
    return {"categories": report, "changed": changed}


def render_diff(before_name: str, after_name: str, diff: dict) -> str:
    out = [f"保全校验: {before_name} → {after_name}"]

    def show(items: list[str]) -> str:
        if not items:
            return "无"
        head = "、".join(items[:8])
        return head + ("…" if len(items) > 8 else "")

    for name, info in diff["categories"].items():
        if name == "代码块":
            out.append(f"  {name}: {info['before']} → {info['after']}")
            continue
        out.append(
            f"  {name}: {info['before']} → {info['after']}；丢失: {show(info['removed'])}；新增: {show(info['added'])}"
        )
    if diff["changed"]:
        out.append(f"结论: 发现 {diff['changed']} 处事实增删，逐条复核（改写不得新增或丢失事实）。")
    else:
        out.append("结论: 未发现数字/日期/引文/链接/路径/行内代码/代码块的事实增删。")
    return "\n".join(out)


# ---------------- 自检 ----------------


def self_test() -> int:
    failures: list[str] = []

    bad = (
        "这次更新至关重要，标志着产品开启了新的篇章。"
        "有研究表明，这种做法能提升效率。"
        "科技正在重塑我们的工作方式。"
        "这才是真正的价值。让我们共同期待，未来必将更加美好。"
    )
    good = (
        "接口在 2025 年 3 月升级后，旧客户端无法登录。"
        "我们把缓存命中率从 41% 提到 78%——代价是内存翻倍。"
        "值吗？看场景：日活高的机器不换。"
    )
    bad_hits = find_signals(bad)
    good_hits = find_signals(good)
    if len(bad_hits) < 5 or not any(t == TIER_STRUCT for _, t in bad_hits):
        failures.append(f"坏样本命中不足: {bad_hits}")
    if good_hits:
        failures.append(f"好样本被误报（含设问/破折号/具体数字）: {good_hits}")

    good_typo = typography_counts(good)
    if good_typo["破折号——"] != 1 or good_typo["汉字后半角标点"] != 0:
        failures.append(f"排版计数不对: {good_typo}")

    diff = diff_facts(
        "覆盖率为 62%。负责人说「先稳定再优化」。",
        "覆盖率提升到 62%？负责人说「先稳定再优化吧」。另外新增 3 台机器。",
    )
    cats = diff["categories"]
    if "3" not in cats["数字"]["added"] or not cats["引文"]["removed"] or not cats["引文"]["added"]:
        failures.append(f"保全校验漏检: {cats}")
    noop = diff_facts("同样的一句话。", "同样的一句话。")
    if noop["changed"]:
        failures.append("保全校验对相同文本误报")

    result = analyze("self-test", bad)
    try:
        json.dumps(result)
    except TypeError as exc:  # pragma: no cover
        failures.append(f"JSON 序列化失败: {exc}")

    if failures:
        print("FAIL  ai tone score self-test")
        for message in failures:
            print(f"      {message}")
        return 1
    print("PASS  ai tone score self-test")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="中文文本 AI 味体检（只定位，不判决）。")
    parser.add_argument("files", nargs="*", help="UTF-8 文件；用 - 从 stdin 读")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--diff", nargs=2, metavar=("原稿", "改写稿"), help="事实保全校验")
    parser.add_argument("--strict", action="store_true", help="--diff 有增删时退出码 1")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.diff:
        before_name, after_name = args.diff
        before = Path(before_name).read_text(encoding="utf-8")
        after = Path(after_name).read_text(encoding="utf-8")
        diff = diff_facts(before, after)
        print(render_diff(before_name, after_name, diff))
        return 1 if (args.strict and diff["changed"]) else 0

    if not args.files:
        parser.error("provide one or more files, or use --self-test / --diff")

    results = []
    for name in args.files:
        text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
        results.append(analyze(name, text))

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(render_text(result))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
