"""Typeset a resume source (YAML) into an A4 PDF, optionally a DOCX, and print a JSON report.

The body size is chosen between a floor and a ceiling so that the content fills the target number
of pages. The report says whether it fits and lists lines worth tightening. The source format is
described in the skill's references/source.md.
"""

import argparse
import base64
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path

import yaml

TEMPLATES = Path(__file__).resolve().parents[1] / "assets" / "templates"
TEMPLATE_ACCENTS = {"serif": "#262626", "classic": "#1f4e79", "modern": "#2563a8",
                    "timeline": "#13706b", "sidebar": "#8c2f39", "banner": "#23426b"}
DEFAULT_TEMPLATE = "serif"
BLEED = {"banner"}  # 页头色块铺满首页顶部：首页上边距归零，可用高度多出一个页边距
LANGS = ("zh", "en")

# 正文字号在 FLOOR–CEILING（磅）之间按 STEP 取最大的那一档；行距和页边距随字号一起放宽，内容少时页面仍从容。
FLOOR, CEILING, STEP = 9.0, 11.5, 0.1
DENSE = 9.5  # 低于它正文偏小，提示删减较弱的内容
SPARSE = {1: 0.85, 2: 0.5}  # 最后一页用到的高度占比低于它算内容偏少；两页的简历第二页至少过半
LONG_LINES = 3  # 一条要点超过这么多行，提示拆开或收紧
STUB = 0.12  # 末行宽度不到整行的这个比例，算只剩几个字的短尾行
PAGE_W, PAGE_H = 210, 297  # mm
PX_PER_MM = 96 / 25.4
PT_PER_MM = 72 / 25.4

FONTS = {
    "zh": {"sans": '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif',
           "serif": '"Noto Serif CJK SC", "Songti SC", SimSun, serif'},
    "en": {"sans": '"Noto Sans", "Helvetica Neue", Arial, "Noto Sans CJK SC", sans-serif',
           "serif": '"Noto Serif", Georgia, "Noto Serif CJK SC", serif'},
}
# Word 版按用户电脑上常见的字体写：中文微软雅黑、宋体，英文 Calibri、Times New Roman。
DOCX_FONTS = {"zh": {"sans": ("Microsoft YaHei", "微软雅黑"), "serif": ("Times New Roman", "宋体")},
              "en": {"sans": ("Calibri", "微软雅黑"), "serif": ("Times New Roman", "宋体")}}

FIELDS = {"template", "accent", "lang", "pages", "name", "headline", "contacts", "photo", "sections"}
SECTION_FIELDS = {"title", "entries", "items", "bullets", "text"}
ENTRY_FIELDS = {"title", "subtitle", "location", "date", "note", "bullets"}
ITEM_FIELDS = {"label", "text"}
BODIES = ("entries", "items", "bullets", "text")

INLINE = re.compile(r"\[(?P<label>[^\]\n]+)\]\((?P<url>[^)\s]+)\)|\*\*(?P<bold>.+?)\*\*|【(?P<todo>[^】\n]*)】")
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
DOMAIN = re.compile(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", re.I)
PHONE = re.compile(r"\+?\d[\d\s-]{6,}\d")
CJK = r"\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef"  # CJK 文字与全角标点


class SourceError(Exception):
    pass


class TextLoader(yaml.SafeLoader):
    pass


# 只保留 null 的隐式解析：2024.10、0571 开头的电话、GPA 3.70 都按原文读成文字，不会被 YAML 改成数字。
TextLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in resolvers if tag == "tag:yaml.org,2002:null"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@dataclass
class Run:
    text: str
    bold: bool = False
    url: str | None = None
    todo: bool = False


def link_url(url):
    if url.startswith(("http://", "https://", "mailto:")):
        return url
    return "https://" + url


def runs(text, bold=False, url=None):
    """行内写法：**加粗**、[文字](网址)、【待补充】；链接文字和加粗里还能再嵌套。"""
    out, position = [], 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            out.append(Run(text[position:match.start()], bold, url))
        if match["label"] is not None:
            out += runs(match["label"], bold, link_url(match["url"]))
        elif match["bold"] is not None:
            out += runs(match["bold"], True, url)
        else:
            out.append(Run(match.group(0), bold, url, todo=True))
        position = match.end()
    if position < len(text):
        out.append(Run(text[position:], bold, url))
    return out


def join_lines(text):
    """YAML 多行文字合成一行：中文之间直接相连，其余补一个空格。"""
    def glue(match):
        before, after = match.string[match.start() - 1:match.start()], match.string[match.end():match.end() + 1]
        return "" if re.match(f"[{CJK}]", before) and re.match(f"[{CJK}]", after) else " "
    return re.sub(r"\s*\n\s*", glue, text.strip())


def scalar(value, where, required=False):
    if value is None:
        if required:
            raise SourceError(f"{where} is required")
        return None
    if not isinstance(value, str):
        raise SourceError(f"{where} must be text")
    value = join_lines(value)
    if required and not value:
        raise SourceError(f"{where} is empty")
    return value or None


def text_list(value, where):
    if value is None:
        return []
    if not isinstance(value, list):
        raise SourceError(f"{where} must be a list")
    return [item for index, raw in enumerate(value) if (item := scalar(raw, f"{where}[{index}]"))]


def check_fields(data, allowed, where):
    if not isinstance(data, dict):
        raise SourceError(f"{where} must be a mapping")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise SourceError(f"{where}: unknown field {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")


def read_source(path):
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=TextLoader)
    except yaml.YAMLError as error:
        raise SourceError(f"invalid YAML: {error}") from None
    check_fields(data, FIELDS, "source")
    spec = {
        "template": scalar(data.get("template"), "template") or DEFAULT_TEMPLATE,
        "lang": scalar(data.get("lang"), "lang") or "zh",
        "pages": scalar(data.get("pages"), "pages") or "1",
        "name": scalar(data.get("name"), "name", required=True),
        "headline": scalar(data.get("headline"), "headline"),
        "contacts": text_list(data.get("contacts"), "contacts"),
        "photo": None,
        "sections": [],
    }
    if spec["template"] not in TEMPLATE_ACCENTS:
        raise SourceError(f"template must be one of {', '.join(TEMPLATE_ACCENTS)}")
    if spec["lang"] not in LANGS:
        raise SourceError("lang must be zh or en")
    if spec["pages"] not in ("1", "2"):
        raise SourceError("pages must be 1 or 2")
    spec["pages"] = int(spec["pages"])
    # 不写强调色时由模板决定，所以换模板比较时跟着换。
    accent = spec["accent"] = scalar(data.get("accent"), "accent")
    if accent and not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise SourceError('accent must be a color such as "#1f4e79"')
    if photo := scalar(data.get("photo"), "photo"):
        file = (path.parent / photo).resolve()
        if not file.is_file():
            raise SourceError(f"photo not found: {photo} (relative to the source file)")
        spec["photo"] = file
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise SourceError("sections must be a non-empty list")
    for index, raw in enumerate(sections):
        spec["sections"].append(read_section(raw, f"sections[{index}]"))
    return spec


def read_section(raw, where):
    check_fields(raw, SECTION_FIELDS, where)
    section = {"title": scalar(raw.get("title"), f"{where}.title", required=True)}
    bodies = [key for key in BODIES if raw.get(key) is not None]
    if len(bodies) != 1:
        raise SourceError(f"{where} ({section['title']}) needs exactly one of {', '.join(BODIES)}")
    kind = section["kind"] = bodies[0]
    value = raw[kind]
    if kind == "text":
        section["text"] = scalar(value, f"{where}.text", required=True)
    elif kind == "bullets":
        section["bullets"] = text_list(value, f"{where}.bullets")
    elif kind == "items":
        if not isinstance(value, list):
            raise SourceError(f"{where}.items must be a list")
        section["items"] = []
        for index, item in enumerate(value):
            item_where = f"{where}.items[{index}]"
            if isinstance(item, str):
                section["items"].append({"label": None, "text": scalar(item, item_where, required=True)})
                continue
            check_fields(item, ITEM_FIELDS, item_where)
            section["items"].append({"label": scalar(item.get("label"), f"{item_where}.label"),
                                     "text": scalar(item.get("text"), f"{item_where}.text", required=True)})
    else:
        if not isinstance(value, list) or not value:
            raise SourceError(f"{where}.entries must be a non-empty list")
        section["entries"] = []
        for index, entry in enumerate(value):
            entry_where = f"{where}.entries[{index}]"
            check_fields(entry, ENTRY_FIELDS, entry_where)
            section["entries"].append({
                "title": scalar(entry.get("title"), f"{entry_where}.title", required=True),
                "subtitle": scalar(entry.get("subtitle"), f"{entry_where}.subtitle"),
                "location": scalar(entry.get("location"), f"{entry_where}.location"),
                "date": scalar(entry.get("date"), f"{entry_where}.date"),
                "note": scalar(entry.get("note"), f"{entry_where}.note"),
                "bullets": text_list(entry.get("bullets"), f"{entry_where}.bullets"),
            })
    return section


def all_text(spec):
    """(位置, 文字)：报告里的位置写成「分节 › 条目 › 第几条」，方便回到源文件里找。"""
    yield "header", spec["name"]
    if spec["headline"]:
        yield "header", spec["headline"]
    for contact in spec["contacts"]:
        yield "contacts", contact
    for section in spec["sections"]:
        title = section["title"]
        yield title, title
        if section["kind"] == "text":
            yield title, section["text"]
        for number, bullet in enumerate(section.get("bullets", []), 1):
            yield f"{title} › {number}", bullet
        for item in section.get("items", []):
            yield f"{title} › {item['label'] or item['text'][:12]}", (item["label"] or "") + item["text"]
        for entry in section.get("entries", []):
            place = f"{title} › {entry['title']}"
            for key in ("title", "subtitle", "location", "date", "note"):
                if entry[key]:
                    yield place, entry[key]
            for number, bullet in enumerate(entry["bullets"], 1):
                yield f"{place} › {number}", bullet


def contact_runs(text):
    if INLINE.search(text):
        return runs(text)
    if EMAIL.match(text):
        return [Run(text, url="mailto:" + text)]
    if DOMAIN.match(text) and not PHONE.fullmatch(text):
        return [Run(text, url=link_url(text))]
    return [Run(text)]


# ---------- HTML ----------

@dataclass
class Density:
    size: float  # 正文字号，磅
    leading: float
    margin_y: float  # mm
    margin_x: float

    @property
    def printable_mm(self):
        return PAGE_H - 2 * self.margin_y


def density(size):
    t = (size - FLOOR) / (CEILING - FLOOR)
    return Density(size, round(1.42 + 0.16 * t, 3), round(10 + 6 * t, 2), round(12 + 6 * t, 2))


def html_runs(items):
    parts = []
    for run in items:
        text = escape(run.text)
        if run.todo:
            text = f"<mark>{text}</mark>"
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.url:
            text = f'<a href="{escape(run.url)}">{text}</a>'
        parts.append(text)
    return "".join(parts)


def inline(text):
    return html_runs(runs(text))


def data_uri(path):
    kind = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{kind};base64,{base64.b64encode(path.read_bytes()).decode()}"


def document_html(spec, size):
    d = density(size)
    fonts = FONTS[spec["lang"]]
    css = (TEMPLATES / "base.css").read_text(encoding="utf-8") + (TEMPLATES / f"{spec['template']}.css").read_text(encoding="utf-8")
    root = (f":root{{--size:{d.size}pt;--leading:{d.leading};--sheet:{PAGE_W - 2 * d.margin_x}mm;"
            f"--margin-x:{d.margin_x}mm;--margin-y:{d.margin_y}mm;"
            f"--accent:{spec['accent']};--sans:{fonts['sans']};--serif:{fonts['serif']}}}")
    page = f"@page{{size:A4;margin:{d.margin_y}mm {d.margin_x}mm}}"
    head = [f'<h1 class="name">{inline(spec["name"])}</h1>']
    if spec["headline"]:
        head.append(f'<p class="headline">{inline(spec["headline"])}</p>')
    if spec["contacts"]:
        head.append('<p class="contacts">' + "".join(f"<span>{html_runs(contact_runs(c))}</span>" for c in spec["contacts"]) + "</p>")
    photo = f'<img class="photo" alt="" src="{data_uri(spec["photo"])}">' if spec["photo"] else ""
    body = [f'<header class="head{" has-photo" if photo else ""}"><div class="id">{"".join(head)}</div>{photo}</header>']
    for section in spec["sections"]:
        body.append(section_html(section))
    lang = "zh-CN" if spec["lang"] == "zh" else "en"
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f"<title>{escape(spec['name'])}</title><style>{page}{root}{css}</style></head>"
            f'<body><main class="sheet">{"".join(body)}</main></body></html>')


def bullets_html(items, place):
    return '<ul class="bullets">' + "".join(
        f'<li data-where="{escape(place)} › {number}">{inline(item)}</li>' for number, item in enumerate(items, 1)) + "</ul>"


def section_html(section):
    title = section["title"]
    parts = [f'<section class="section"><h2><span>{inline(title)}</span></h2><div class="body">']
    kind = section["kind"]
    if kind == "text":
        parts.append(f'<p class="text" data-where="{escape(title)}">{inline(section["text"])}</p>')
    elif kind == "bullets":
        parts.append(bullets_html(section["bullets"], title))
    elif kind == "items":
        rows = []
        for item in section["items"]:
            label = f'<span class="label">{inline(item["label"])}</span>' if item["label"] else ""
            rows.append(f"<li>{label}{inline(item['text'])}</li>")
        parts.append('<ul class="items">' + "".join(rows) + "</ul>")
    else:
        for entry in section["entries"]:
            place = f"{title} › {entry['title']}"
            main = [f'<span class="entry-title">{inline(entry["title"])}</span>']
            main += [f'<span class="entry-{key}">{inline(entry[key])}</span>' for key in ("subtitle", "location") if entry[key]]
            date = f'<span class="entry-date">{inline(entry["date"])}</span>' if entry["date"] else ""
            parts.append(f'<div class="entry"><div class="entry-head"><div class="entry-main">{"".join(main)}</div>{date}</div>')
            if entry["note"]:
                parts.append(f'<p class="entry-note" data-where="{escape(place)}">{inline(entry["note"])}</p>')
            if entry["bullets"]:
                parts.append(bullets_html(entry["bullets"], place))
            parts.append("</div>")
    parts.append("</div></section>")
    return "".join(parts)


# ---------- 浏览器排版与测量 ----------

# 按行的竖直中心归组：同一行里加粗和不同字体的片段上沿不齐，中心是齐的。
MEASURE = """() => {
  const sheet = document.querySelector('.sheet');
  const blocks = [];
  for (const el of document.querySelectorAll('[data-where]')) {
    const style = getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight);
    const box = el.getBoundingClientRect();
    const width = box.width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const range = document.createRange();
    range.selectNodeContents(el);
    const lines = [];
    for (const r of range.getClientRects()) {
      if (r.width < 0.5) continue;
      const center = (r.top + r.bottom) / 2;
      let line = lines.find((l) => Math.abs(l.center - center) < lineHeight / 2);
      if (!line) lines.push(line = { center, left: r.left, right: r.right });
      line.left = Math.min(line.left, r.left);
      line.right = Math.max(line.right, r.right);
    }
    lines.sort((a, b) => a.center - b.center);
    const last = lines[lines.length - 1];
    blocks.push({ where: el.dataset.where, bullet: el.tagName === 'LI', text: el.textContent,
                  lines: lines.length, last: last ? (last.right - last.left) / width : 1 });
  }
  return { height: sheet.getBoundingClientRect().height, blocks };
}"""


class Browser:
    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        executable = os.environ.get("RESUME_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
        try:
            self.browser = self._pw.chromium.launch(executable_path=executable, args=["--no-sandbox", "--disable-gpu"])
        except Exception as error:
            self._pw.stop()
            raise RuntimeError(f"Chromium could not start: {error}") from None
        self.page = self.browser.new_page(viewport={"width": 1000, "height": 1400})

    def load(self, html):
        self.page.set_content(html, wait_until="load")
        self.page.evaluate("document.fonts.ready.then(() => true)")

    def measure(self, html):
        self.load(html)
        return self.page.evaluate(MEASURE)

    def print(self, html, path):
        self.load(html)
        self.page.pdf(path=str(path), prefer_css_page_size=True, print_background=True)

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


def pdf_pages(path, margin_y):
    """页数和最后一页内容用到的高度占比（按文字和图片的下沿算）。"""
    import pymupdf

    with pymupdf.open(path) as document:
        pages = document.page_count
        last = document[-1]
        bottom = max((block[3] for block in last.get_text("blocks")), default=0)
        for image in last.get_image_info():
            bottom = max(bottom, image["bbox"][3])
    top = margin_y * PT_PER_MM
    printable = (PAGE_H - 2 * margin_y) * PT_PER_MM
    return pages, max(0.0, min(1.0, (bottom - top) / printable))


def fit(browser, spec, output):
    """取能排进目标页数的最大字号：先在屏幕上量高度二分查找，再打印核对页数，超出就降一档重印。"""
    target = spec["pages"]
    sizes = [round(FLOOR + i * STEP, 2) for i in range(round((CEILING - FLOOR) / STEP) + 1)]
    measured = {}

    def capacity(size):
        d = density(size)
        return (target * d.printable_mm + (d.margin_y if spec["template"] in BLEED else 0)) * PX_PER_MM

    def fits(index):
        size = sizes[index]
        if size not in measured:
            measured[size] = browser.measure(document_html(spec, size))
        return measured[size]["height"] <= capacity(size)

    low, high = 0, len(sizes) - 1
    if not fits(low):
        choice = None
    else:
        while low < high:
            middle = (low + high + 1) // 2
            low, high = (middle, high) if fits(middle) else (low, middle - 1)
        choice = low
    index = choice if choice is not None else 0
    while True:
        size = sizes[index]
        browser.print(document_html(spec, size), output)
        pages, fill = pdf_pages(output, density(size).margin_y)
        if pages <= target or index == 0:
            break
        index -= 1
    size = sizes[index]
    if size not in measured:
        measured[size] = browser.measure(document_html(spec, size))
    result = {"pages": pages, "target_pages": target, "font_pt": size, "fill": round(fill, 2)}
    if pages > target:
        d = density(size)
        over = measured[size]["height"] - capacity(size)
        line = d.size * d.leading * 96 / 72
        result["fit"] = "overflow"
        result["overflow_lines"] = max(1, math.ceil(over / line))
    elif pages < target or (size == sizes[-1] and fill < SPARSE[target]):
        result["fit"] = "sparse"
    else:
        result["fit"] = "ok"
    return result, measured[size]["blocks"]


def layout_warnings(blocks):
    warnings = []
    for block in blocks:
        if block["bullet"] and block["lines"] > LONG_LINES:
            warnings.append({"code": "long_bullet", "where": block["where"], "lines": block["lines"],
                             "message": "Split this bullet or cut it to at most three lines."})
        elif block["lines"] >= 2 and block["last"] < STUB:
            tail = block["text"].strip()[-6:]
            warnings.append({"code": "stub_line", "where": block["where"], "tail": tail,
                             "message": "The last line holds only a few characters; tighten the wording so it ends a line earlier, or add a few real words."})
    return warnings


def source_warnings(spec):
    warnings = []
    for where, text in all_text(spec):
        for match in re.finditer(r"【[^】\n]*】", text):
            warnings.append({"code": "placeholder", "where": where, "text": match.group(0),
                             "message": "Fill this from the user's answer or remove it before delivering."})
    contacts = " ".join(spec["contacts"])
    if not (re.search(r"[\w.+-]+@[\w-]+\.", contacts) or PHONE.search(contacts)):
        warnings.append({"code": "no_contact", "where": "contacts",
                         "message": "No phone number or email address; recruiters need at least one."})
    return warnings


# ---------- Word ----------

# ECMA-376 里 w:pPr、w:rPr、w:tblPr 和 w:tcPr 子元素的顺序：放错位置 Word 会提示文件损坏。
PPR_ORDER = (
    "w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr", "w:widowControl", "w:numPr",
    "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
    "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
    "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
    "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr",
    "w:sectPr", "w:pPrChange",
)
RPR_ORDER = (
    "w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike", "w:dstrike",
    "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof", "w:snapToGrid", "w:vanish", "w:webHidden",
    "w:color", "w:spacing", "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect",
    "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout",
    "w:specVanish", "w:oMath",
)
TBLPR_ORDER = (
    "w:tblStyle", "w:tblpPr", "w:tblOverlap", "w:bidiVisual", "w:tblStyleRowBandSize", "w:tblStyleColBandSize",
    "w:tblW", "w:jc", "w:tblCellSpacing", "w:tblInd", "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar",
    "w:tblLook", "w:tblCaption", "w:tblDescription", "w:tblPrChange",
)
TCPR_ORDER = (
    "w:cnfStyle", "w:tcW", "w:gridSpan", "w:hMerge", "w:vMerge", "w:tcBorders", "w:shd", "w:noWrap", "w:tcMar",
    "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark", "w:headers", "w:cellIns", "w:cellDel",
    "w:cellMerge", "w:tcPrChange",
)


def mix(color, ratio, base="#ffffff"):
    """颜色按比例混入底色（默认白色），和 CSS 的 color-mix(in srgb, color ratio, base) 一致，返回不带 # 的十六进制。"""
    pairs = ((int(color[i:i + 2], 16), int(base[i:i + 2], 16)) for i in (1, 3, 5))
    return "".join(f"{round(c * ratio + b * (1 - ratio)):02X}" for c, b in pairs)


def text_em(text):
    """粗估一行文字有几个字号宽。Word 没有按内容定宽的栏，时间轴的日期栏和侧栏的标题栏按它取宽度。"""
    width = 0.0
    for char in text:
        if re.match(f"[{CJK}]", char):
            width += 1.0
        elif char.isdigit():
            width += 0.58
        elif char.isupper():
            width += 0.68
        elif char.isalpha():
            width += 0.52
        elif char.isspace():
            width += 0.3
        else:
            width += 0.45
    return width


def docx_document(spec, size):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_TAB_ALIGNMENT
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor

    d = density(size)
    size = round(size * 2) / 2  # Word 字号以半磅为单位
    lang, template = spec["lang"], spec["template"]
    sans, serif = DOCX_FONTS[lang]["sans"], DOCX_FONTS[lang]["serif"]
    hex_accent = spec["accent"][1:].upper()
    accent = RGBColor.from_string(hex_accent)
    muted = RGBColor.from_string("4E5969")
    ink = RGBColor.from_string("1D2129")
    white = RGBColor.from_string("FFFFFF")

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(PAGE_W), Mm(PAGE_H)
    section.top_margin = section.bottom_margin = Mm(d.margin_y)
    section.left_margin = section.right_margin = Mm(d.margin_x)
    width = (PAGE_W - 2 * d.margin_x) * PT_PER_MM  # 版心宽度，磅

    def set_fonts(element, fonts):
        properties = element.get_or_add_rPr()
        names = properties.find(qn("w:rFonts"))
        if names is None:
            names = OxmlElement("w:rFonts")
            properties.insert(0, names)
        for key in ("w:ascii", "w:hAnsi", "w:cs"):
            names.set(qn(key), fonts[0])
        names.set(qn("w:eastAsia"), fonts[1])

    normal = document.styles["Normal"]
    normal.font.size = Pt(size)
    normal.font.color.rgb = ink
    set_fonts(normal.element, sans)
    normal.paragraph_format.space_before = normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = Pt(round(size * d.leading, 1))

    def add_property(properties, tag, order=PPR_ORDER, **values):
        # 属性元素有固定顺序，按 order 插到该在的位置。
        element = OxmlElement(tag)
        for key, value in values.items():
            element.set(qn(f"w:{key}"), str(value))
        properties.insert_element_before(element, *order[order.index(tag) + 1:])
        return element

    def line(borders, side, **values):
        # 边框容器里只放一条线，直接追加。
        element = OxmlElement(f"w:{side}")
        for key, value in values.items():
            element.set(qn(f"w:{key}"), str(value))
        borders.append(element)

    def sides(parent, values):
        """依次写上、左、下、右四边，用于单元格内边距（缇）。"""
        for side, value in zip(("top", "left", "bottom", "right"), values):
            element = OxmlElement(f"w:{side}")
            element.set(qn("w:w"), str(round(value * 20)))
            element.set(qn("w:type"), "dxa")
            parent.append(element)

    def add_runs(paragraph, items, fonts=None, color=None, scale=1.0, bold=False, shade=None):
        for item in items:
            run = paragraph.add_run(item.text)
            if bold or item.bold:
                run.bold = True
            if scale != 1.0:
                run.font.size = Pt(round(size * scale * 2) / 2)
            if color is not None:
                run.font.color.rgb = color
            if fonts:
                set_fonts(run._r, fonts)
            if shade:
                add_property(run._r.get_or_add_rPr(), "w:shd", RPR_ORDER, val="clear", color="auto", fill=shade)
            if item.todo:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            if item.url:
                link = OxmlElement("w:hyperlink")
                link.set(qn("r:id"), paragraph.part.relate_to(item.url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
                run._r.addprevious(link)
                link.append(run._r)

    def paragraph(container, before=0.0, align=None, indent=0.0):
        p = container.add_paragraph()
        p.paragraph_format.space_before = Pt(round(size * before, 1))
        if indent:
            p.paragraph_format.left_indent = Pt(indent)
        if align:
            p.alignment = align
        return p

    def bullet(container, text, indent=0.0):
        # 缩进直接写在段落上：列表编号自带的缩进会盖过样式里的缩进。
        p = container.add_paragraph(style="List Bullet")
        p.paragraph_format.left_indent = Pt(indent + size * 1.3)
        p.paragraph_format.first_line_indent = Pt(-size * 0.9)
        add_runs(p, runs(text))

    def grid_table(rows, widths, float_top=False):
        """固定列宽、无边框、默认单元格无内边距的表格；float_top 让它浮在页面左上角，正文从它下面开始。"""
        table = document.add_table(rows=rows, cols=len(widths))
        table.autofit = False
        properties = table._tbl.tblPr
        total = properties.find(qn("w:tblW"))
        total.set(qn("w:w"), str(round(sum(widths) * 20)))
        total.set(qn("w:type"), "dxa")
        if float_top:
            add_property(properties, "w:tblpPr", TBLPR_ORDER, leftFromText=0, rightFromText=0, topFromText=0,
                         bottomFromText=round(size * 20), vertAnchor="page", horzAnchor="page", tblpX=0, tblpY=0)
            add_property(properties, "w:tblOverlap", TBLPR_ORDER, val="never")
        sides(add_property(properties, "w:tblCellMar", TBLPR_ORDER), (0, 0, 0, 0))
        for column, value in zip(table.columns, widths):
            column.width = Pt(value)
        return table

    def cell(target, value, margins=(0, 0, 0, 0), shade=None, rule=None):
        """单元格宽度、内边距（磅，上左下右）、底色和左侧竖线；清掉自带的空段落，由调用方填内容。"""
        target.width = Pt(value)
        properties = target._tc.get_or_add_tcPr()
        if rule:
            line(add_property(properties, "w:tcBorders", TCPR_ORDER), "left", val="single", sz=4, space=0, color=rule)
        if shade:
            add_property(properties, "w:shd", TCPR_ORDER, val="clear", color="auto", fill=shade)
        sides(add_property(properties, "w:tcMar", TCPR_ORDER), margins)
        for p in target.paragraphs:
            p._p.getparent().remove(p._p)
        return target

    centered = template == "serif" and not spec["photo"]
    display_fonts = serif if template == "serif" else None  # 典雅模板的姓名、分节标题和条目标题用衬线
    gap = size * 0.9  # 侧栏的标题、竖线和内容之间的距离
    rail = 0.0  # 时间轴：日期栏加间距；侧栏：标题栏加间距
    if template == "timeline":
        dates = [text_em(e["date"]) for s in spec["sections"] for e in s.get("entries", []) if e["date"]]
        rail = (min(max(dates, default=0), 10) + 1.3) * size
    elif template == "sidebar":
        rail = min(max(text_em(s["title"]) for s in spec["sections"]) * 1.06, 8) * size + gap
    head_indent = rail + gap if template == "sidebar" else 0.0  # 侧栏的页头和内容左缘对齐

    body = document
    if template == "banner":
        # 色块页头浮在页面顶端、左右出血，和 PDF 一样；内边距让文字仍落在版心里。
        margin_x, margin_y = d.margin_x * PT_PER_MM, d.margin_y * PT_PER_MM
        top, bottom = margin_y + size * 0.3, size * 1.1
        photo_w = (31 * PT_PER_MM + margin_x) if spec["photo"] else 0
        band = grid_table(1, [PAGE_W * PT_PER_MM - photo_w] + ([photo_w] if photo_w else []), float_top=True)
        cells = band.rows[0].cells
        body = cell(cells[0], PAGE_W * PT_PER_MM - photo_w, (top, margin_x, bottom, 0 if photo_w else margin_x), hex_accent)
        if photo_w:
            # 照片格左边框用同色，盖住两格底色之间的细缝。
            picture = cell(cells[1], photo_w, (top, 0, bottom, margin_x), hex_accent, rule=hex_accent).add_paragraph()
    elif spec["photo"]:
        photo_w = 30 * PT_PER_MM
        cells = grid_table(1, [width - photo_w, photo_w]).rows[0].cells
        body = cell(cells[0], width - photo_w)
        picture = cell(cells[1], photo_w).add_paragraph()
    if spec["photo"]:
        # 正文是固定行距，照片段落要改回单倍行距，否则照片被裁成一行高。
        picture.paragraph_format.line_spacing = 1.0
        picture.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        picture.add_run().add_picture(str(spec["photo"]), width=Mm(25))
    on_band = template == "banner"
    align = WD_ALIGN_PARAGRAPH.CENTER if centered else None
    name_color = {"modern": accent, "banner": white}.get(template)
    name_scale = {"timeline": 2.2, "sidebar": 2.2, "banner": 2.3}.get(template, 2.1)
    add_runs(paragraph(body, align=align, indent=head_indent), runs(spec["name"]), display_fonts, name_color, name_scale, True)
    if spec["headline"]:
        add_runs(paragraph(body, 0.15, align, head_indent), runs(spec["headline"]), color=white if on_band else None, scale=1.05)
    if spec["contacts"]:
        p = paragraph(body, 0.25, align, head_indent)
        contact_color = RGBColor.from_string(mix("#ffffff", 0.82, spec["accent"])) if on_band else muted
        for index, contact in enumerate(spec["contacts"]):
            if index:
                add_runs(p, [Run("  |  ")], color=contact_color)
            add_runs(p, contact_runs(contact), color=contact_color)

    heading_color = ink if template == "modern" else accent
    rule_color = mix(spec["accent"], 0.45) if template in ("classic", "banner") else hex_accent
    entry_color = accent if template in ("modern", "timeline") else None
    indent = rail if template == "timeline" else 0.0  # 时间轴的内容都从日期栏右边开始
    inner = width - rail - gap if template == "sidebar" else width  # 条目日期右对齐的位置

    def heading_style(p):
        """经典和色块页头是浅色下划线，典雅是强调色下划线，时间轴是色签下的强调色粗线，现代是左侧色条加浅色底。"""
        properties = p._p.get_or_add_pPr()
        borders = add_property(properties, "w:pBdr")
        if template == "modern":
            line(borders, "left", val="single", sz=18, space=4, color=hex_accent)
            add_property(properties, "w:shd", val="clear", color="auto", fill=mix(spec["accent"], 0.09))
        elif template == "timeline":
            line(borders, "bottom", val="single", sz=12, space=0, color=hex_accent)
        else:
            line(borders, "bottom", val="single", sz=6, space=1, color=rule_color)

    if template == "sidebar":
        # 侧栏：每个分节一行，左格是右对齐的标题，右格左边框就是贯通的竖线。
        grid = grid_table(0, [rail, width - rail])
        rule = mix(spec["accent"], 0.3, "#d9d9d9")
    for number, section_spec in enumerate(spec["sections"]):
        title = section_spec["title"].upper() if template == "serif" and lang == "en" else section_spec["title"]
        if template == "sidebar":
            title_cell, container = grid.add_row().cells
            cell(title_cell, rail, (0, 0, 0, gap))
            cell(container, width - rail, (0, gap, 0, 0), rule=rule)
            heading = paragraph(title_cell, 1.0 if number == 0 else 0.85, WD_ALIGN_PARAGRAPH.RIGHT)
            add_runs(heading, runs(title), None, accent, 1.06, True)
        else:
            container = document
            heading = paragraph(document, 0.8)
            heading.paragraph_format.space_after = Pt(round(size * 0.3, 1))
            heading.paragraph_format.keep_with_next = True
            if template == "timeline":
                add_runs(heading, [Run("\u00a0\u00a0")] + runs(title) + [Run("\u00a0\u00a0")], None, white, 1.1, True, hex_accent)
            else:
                add_runs(heading, runs(title), display_fonts, heading_color, 1.1, True)
            heading_style(heading)
        kind = section_spec["kind"]
        if kind == "text":
            add_runs(paragraph(container, indent=indent), runs(section_spec["text"]))
        elif kind == "bullets":
            for text in section_spec["bullets"]:
                bullet(container, text, indent)
        elif kind == "items":
            for item in section_spec["items"]:
                p = paragraph(container, indent=indent)
                if item["label"]:
                    add_runs(p, [Run(item["label"] + ("：" if lang == "zh" else ": "), bold=True)])
                add_runs(p, runs(item["text"]))
        else:
            for count, entry in enumerate(section_spec["entries"]):
                p = paragraph(container, 0.45 if count else 0)
                p.paragraph_format.keep_with_next = True
                if template == "timeline":
                    # 日期在悬挂缩进里，制表位跳到日期栏右边的内容起点。
                    p.paragraph_format.left_indent = Pt(rail)
                    p.paragraph_format.first_line_indent = Pt(-rail)
                    p.paragraph_format.tab_stops.add_tab_stop(Pt(rail))
                    add_runs(p, runs(entry["date"] or "") + [Run("\t")], color=muted)
                else:
                    p.paragraph_format.tab_stops.add_tab_stop(Pt(inner), WD_TAB_ALIGNMENT.RIGHT)
                add_runs(p, runs(entry["title"]), display_fonts, entry_color, bold=True)
                extras = [entry[key] for key in ("subtitle", "location") if entry[key]]
                date = entry["date"] if template != "timeline" else None
                # 一行放不下时和 PDF 一样：日期留在第一行右端，副标题和地点换到第二行。
                wide = bool(date and extras) and size * (
                    text_em(entry["title"]) * 1.05 + sum(text_em(extra) + 1.2 for extra in extras) + text_em(date) + 1.5) > inner
                if wide:
                    add_runs(p, [Run("\t")] + runs(date), color=muted)
                    p.add_run().add_break()
                for index, extra in enumerate(extras):
                    add_runs(p, ([Run("    ")] if index or not wide else []) + runs(extra))
                if date and not wide:
                    add_runs(p, [Run("\t")] + runs(date), color=muted)
                if entry["note"]:
                    note = paragraph(container, indent=indent)
                    note.paragraph_format.keep_with_next = bool(entry["bullets"])
                    add_runs(note, runs(entry["note"]), color=muted)
                for text in entry["bullets"]:
                    bullet(container, text, indent)
        if template == "sidebar":
            container.paragraphs[0].paragraph_format.space_before = heading.paragraph_format.space_before
    core = document.core_properties
    core.title, core.author = spec["name"], spec["name"]
    return document


def render_docx(docx_path, pdf_path):
    """沙箱里用 render-office；本机开发时退回 soffice。没有 LibreOffice 时返回 False。"""
    tool = shutil.which("render-office")
    if tool:
        command = [tool, str(docx_path), str(pdf_path), "--timeout", "120"]
    else:
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if not office:
            return False
        command = [office, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    produced = pdf_path if tool else pdf_path.parent / (docx_path.stem + ".pdf")
    if result.returncode != 0 or not produced.is_file():
        raise RuntimeError("LibreOffice could not render the DOCX: " + (result.stderr or result.stdout).strip()[-400:])
    if produced != pdf_path:
        produced.replace(pdf_path)
    return True


def write_docx(spec, path, size):
    """Word 版用 PDF 选定的字号；能用 LibreOffice 预览时核对页数，超出就每次减半磅，最多到下限。"""
    import pymupdf

    with tempfile.TemporaryDirectory() as work:
        preview = Path(work) / "preview.pdf"
        while True:
            docx_document(spec, size).save(path)
            if not render_docx(path, preview):
                return {"output": str(path), "font_pt": round(size * 2) / 2, "pages": None}
            with pymupdf.open(preview) as document:
                pages = document.page_count
            if pages <= spec["pages"] or size - 0.5 < FLOOR:
                return {"output": str(path), "font_pt": round(size * 2) / 2, "pages": pages}
            size -= 0.5


# ---------- 入口 ----------

def build(source, output, docx_output=None, template=None):
    spec = read_source(source)
    spec["template"] = template or spec["template"]
    spec["accent"] = spec["accent"] or TEMPLATE_ACCENTS[spec["template"]]
    output.parent.mkdir(parents=True, exist_ok=True)
    browser = Browser()
    try:
        result, blocks = fit(browser, spec, output)
    finally:
        browser.close()
    warnings = source_warnings(spec) + layout_warnings(blocks)
    if result["fit"] == "ok" and result["font_pt"] < DENSE:
        warnings.append({"code": "dense", "where": "page",
                         "message": f"Body text is {result['font_pt']} pt; cut or shorten the weakest lines so it can grow."})
    report = {"ok": True, "output": str(output), "template": spec["template"], **result, "warnings": warnings}
    if docx_output:
        docx_output.parent.mkdir(parents=True, exist_ok=True)
        report["docx"] = write_docx(spec, docx_output, result["font_pt"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path, help="resume source (.yaml)")
    parser.add_argument("--output", type=Path, required=True, help="PDF path to write")
    parser.add_argument("--docx", type=Path, help="also write a Word version here")
    parser.add_argument("--template", choices=sorted(TEMPLATE_ACCENTS), help="override the source's template, to compare looks")
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"source not found: {args.source}")
    if args.output.suffix.lower() != ".pdf":
        parser.error("--output must end with .pdf")
    if args.docx and args.docx.suffix.lower() != ".docx":
        parser.error("--docx must end with .docx")
    try:
        report = build(args.source, args.output, args.docx, args.template)
    except (SourceError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
