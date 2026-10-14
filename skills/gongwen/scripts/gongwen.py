"""Typeset a Chinese official document (公文) source into a GB/T 9704-2012 DOCX and print a JSON report.

The source is Markdown with a YAML header; see the skill instructions. When LibreOffice is
available, the script renders the document, places the 版记 at the bottom of an even page and
checks the layout.
"""

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# 版面（GB/T 9704-2012 5.2）：A4，天头 37 mm、订口 28 mm，版心 156 mm × 225 mm，每面 22 行、每行 28 字。
MM = 56.6929  # twips
TOP, BOTTOM, INSIDE, OUTSIDE = 37, 35, 28, 26
LINES = 22
# 225 mm / 22 行 = 579.8 twips；取 579，Word 按网格计算行数时仍能排下 22 行。
PITCH = 579
PITCH_MM = PITCH / MM
# 字符网格：156 mm / 28 字 比 3 号字宽少 0.207 磅，以 1/4096 磅为单位。
CHAR_SPACE = -849
CHAR3 = 316  # 3 号一字（网格字距），twips
CHAR4 = 280  # 4 号一字，twips
TEXT_WIDTH = round(156 * MM)
# 页脚距页面下边缘：使页码一字线约在版心下边缘之下 7 mm（7.5）。
FOOTER = round(25 * MM)
# 发文机关标志上边缘至版心上边缘 35 mm（7.2.4）：标志从第 4 行起排，行高取字号的 MARK_LEADING 倍，
# 字形上边缘距行顶约 MARK_INK 倍字号（LibreOffice 实测），据此算段前距。
MARK_LEADING = 1.1
MARK_INK = 0.1
# 版头分隔线位于发文字号之下 4 mm（7.2.7）：画在下一行段落的上边框，段前距把它推到位置。
RULE_BEFORE = 100
RULE_SIZE = 12  # 线宽，1/8 磅

FANGSONG, KAITI, HEITI, XIAOBIAOSONG, SONGTI = "仿宋_GB2312", "楷体_GB2312", "黑体", "方正小标宋简体", "宋体"
LATIN = "Times New Roman"
# 缺字体时 Word / WPS 按 fontTable 的 altName 替换，常见电脑没有 GB2312 版仿宋、楷体和方正小标宋。
ALT_NAMES = {FANGSONG: "仿宋", KAITI: "楷体", XIAOBIAOSONG: "华文中宋"}
RED = "FF0000"
SIZE2, SIZE3, SIZE4 = 22, 16, 14

FIELDS = (
    "份号", "密级", "紧急程度", "发文机关标志", "发文机关标志字号", "发文字号", "签发人", "标题", "主送机关",
    "附件", "出席", "请假", "列席", "署名", "成文日期", "印章", "附注", "抄送", "印发机关", "印发日期",
)
NUMERALS = "一二三四五六七八九十百零〇"
HEADINGS = [
    (1, re.compile(rf"^[{NUMERALS}]+、")),
    (2, re.compile(rf"^（[{NUMERALS}]+）")),
    (3, re.compile(r"^\d+\.(?!\d)")),
    (4, re.compile(r"^（\d+）")),
]
# 常见的层次序数写法错误，统一改成标准写法。
ORDINAL_FIXES = [
    (re.compile(rf"^([{NUMERALS}]+)[.．]\s*"), r"\1、"),
    (re.compile(rf"^[(（]\s*([{NUMERALS}]+)\s*[)）]\s*"), r"（\1）"),
    (re.compile(r"^(\d+)(?:、|．|\.\s+)(?!\d)"), r"\1."),
    (re.compile(r"^[(（]\s*(\d+)\s*[)）]\s*"), r"（\1）"),
]
DATE = re.compile(r"\d{4}年(?:1[0-2]|[1-9])月(?:3[01]|[12]\d|[1-9])日")


class SourceError(Exception):
    pass


def width(text):
    """按汉字宽度计的长度：全角和中文标点算 1，半角数字字母算 0.5。"""
    return sum(1 if unicodedata.east_asian_width(char) in "WFA" else 0.5 for char in text)


def chinese_date(text):
    """把「二〇二六年十月十四日」改成阿拉伯数字；不是这种写法时原样返回。"""
    digits = dict(zip("〇零一二三四五六七八九", "00123456789"))
    match = re.fullmatch(r"([〇零一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日", text)
    if not match:
        return text

    def number(value):
        if "十" not in value:
            return int(digits[value])
        tens, _, ones = value.partition("十")
        return int(digits[tens] if tens else 1) * 10 + (int(digits[ones]) if ones else 0)

    return f"{''.join(digits[c] for c in match[1])}年{number(match[2])}月{number(match[3])}日"


def normalize_date(label, value, fixes, warnings):
    if isinstance(value, date):
        # YAML 会把 2026-10-14 读成日期对象。
        converted = f"{value.year}年{value.month}月{value.day}日"
        fixes.append(f"{label}：{value.isoformat()} → {converted}")
        return converted
    text = re.sub(r"\s+", "", str(value))
    converted = chinese_date(text)
    converted = re.sub(r"(?<=年)0(?=\d月)|(?<=月)0(?=\d日)", "", converted)
    if converted != text:
        fixes.append(f"{label}：{text} → {converted}")
    if not DATE.fullmatch(converted):
        warnings.append(f"{label}「{converted}」应写成「2026年1月5日」：阿拉伯数字，年份写全，月、日不编虚位")
    return converted


def text_list(value, separators="\n"):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(f"[{separators}]", str(value)) if item.strip()]


def flag(label, value):
    """YAML 的 是/否 不是布尔值，按中文写法解析。"""
    if isinstance(value, bool) or value is None:
        return bool(value)
    text = str(value).strip()
    if text in ("是", "加盖", "有", "true", "True"):
        return True
    if text in ("否", "不加盖", "无", "false", "False", ""):
        return False
    raise SourceError(f"{label} must be true or false, got {text}")


def read_source(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.S)
    if not match:
        raise SourceError("the source must start with a YAML header between --- lines")
    try:
        meta = yaml.safe_load(match[1]) or {}
    except yaml.YAMLError as error:
        raise SourceError(f"invalid YAML header: {error}") from error
    if not isinstance(meta, dict):
        raise SourceError("the YAML header must be a mapping")
    unknown = [key for key in meta if key not in FIELDS]
    if unknown:
        raise SourceError(f"unknown header fields {unknown}; allowed: {', '.join(FIELDS)}")
    return meta, match[2]


def parse_body(text, label, fixes, warnings):
    """正文每个非空行是一段；以 | 开头的连续行是表格。去掉 Markdown 标记并规范层次序数。"""
    blocks = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line.startswith("|"):
            rows = [line]
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
            cells = [row for row in cells if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in row)]
            blocks.append(("table", cells))
            continue
        if re.match(r"!\[.*\]\(.*\)", line):
            warnings.append(f"{label}的图片不会排进公文：{line[:30]}")
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"\*\*|__", "", line)
        if re.match(r"^[-*+]\s+", line):
            line = re.sub(r"^[-*+]\s+", "", line)
            warnings.append(f"{label}用了列表符号，公文应改用「一、」「（一）」「1.」「（1）」序数：{line[:20]}")
        for pattern, replacement in ORDINAL_FIXES:
            fixed = pattern.sub(replacement, line, count=1)
            if fixed != line:
                fixes.append(f"{label}层次序数：{line[:12]} → {fixed[:12]}")
                line = fixed
                break
        if line:
            blocks.append(("para", line))
    return blocks


def heading_level(text):
    for level, pattern in HEADINGS:
        if pattern.match(text):
            return level
    return 0


def prepare(meta, body, source_dir):
    """校验并规范化源稿，返回排版用的结构、自动修正和提醒。"""
    fixes, warnings = [], []
    spec = {key: meta.get(key) for key in FIELDS}
    title = text_list(spec["标题"])
    if not title:
        raise SourceError("标题 is required")
    for line in title:
        if re.search(r"[。．，；：！？]$", line):
            warnings.append(f"标题末尾不加标点：{line}")
        if width(line) > 20:
            warnings.append(f"标题一行超过 20 字会自动回行：{line}；请在标题里按词意分行，排成梯形或菱形")
    if len(title) > 3:
        warnings.append("标题超过三行，考虑压缩")
    spec["标题"] = title

    if spec["份号"] is not None:
        number = re.sub(r"\D", "", str(spec["份号"]))
        if number and len(number) < 6:
            fixes.append(f"份号：{spec['份号']} → {number.zfill(6)}")
            number = number.zfill(6)
        spec["份号"] = number or None

    if spec["发文字号"]:
        value = re.sub(r"\s+", "", str(spec["发文字号"]))
        fixed = re.sub(r"[\[［(（【〔]\s*(\d{4})\s*[\]］)）】〕]", r"〔\1〕", value)
        fixed = re.sub(r"〕第", "〕", fixed)
        fixed = re.sub(r"〕0+(\d)", r"〕\1", fixed)
        if fixed != value:
            fixes.append(f"发文字号：{value} → {fixed}")
        minutes = str(spec["发文机关标志"] or "").strip().endswith("纪要")
        if not minutes and not re.fullmatch(r".+〔\d{4}〕[1-9]\d*号", fixed):
            warnings.append(f"发文字号「{fixed}」应由机关代字、〔年份〕和序号加「号」组成，例如「X政发〔2026〕12号」")
        spec["发文字号"] = fixed

    spec["签发人"] = text_list(spec["签发人"], r"\n、，,；;\s")
    if spec["签发人"] and not spec["发文机关标志"]:
        warnings.append("签发人只在有版头（发文机关标志）的上行文中编排，已忽略")
        spec["签发人"] = []

    if spec["主送机关"]:
        value = str(spec["主送机关"]).strip().rstrip("：:，,。；;")
        spec["主送机关"] = value + "："

    attachments = []
    raw = spec["附件"] or []
    if not isinstance(raw, list):
        raw = [raw]
    for item in raw:
        name, file = (item.get("名称"), item.get("文件")) if isinstance(item, dict) else (item, None)
        if not name:
            raise SourceError("each 附件 needs 名称")
        name = str(name).strip()
        stripped = re.sub(r"[。．.，,；;：:]+$", "", name)
        if stripped != name:
            fixes.append(f"附件名称后不加标点：{name} → {stripped}")
        if "《" in stripped:
            warnings.append(f"附件名称一般不加书名号：{stripped}")
        content = None
        if file:
            path = (source_dir / str(file)).resolve()
            if not path.is_file():
                raise SourceError(f"attachment file not found: {file}")
            content = parse_body(path.read_text(encoding="utf-8").replace("\r\n", "\n"), f"附件「{stripped}」", fixes, warnings)
        attachments.append({"名称": stripped, "内容": content})
    spec["附件"] = attachments

    for key in ("成文日期", "印发日期"):
        if spec[key]:
            spec[key] = normalize_date(key, spec[key], fixes, warnings)
    if spec["附注"]:
        note = str(spec["附注"]).strip()
        if not (note.startswith("（") and note.endswith("）")):
            note = "（" + note.strip("()（）") + "）"
        spec["附注"] = note
    if spec["抄送"]:
        value = str(spec["抄送"]).strip().rstrip("，,。；;")
        spec["抄送"] = value + "。"
    if bool(spec["印发机关"]) != bool(spec["印发日期"]):
        warnings.append("印发机关和印发日期要同时填写")
    for key in ("出席", "请假", "列席"):
        if spec[key]:
            spec[key] = str(spec[key]).strip()
    spec["印章"] = flag("印章", spec["印章"])
    if spec["发文机关标志字号"] is not None:
        size = spec["发文机关标志字号"]
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not 22 <= size <= 96:
            raise SourceError("发文机关标志字号 must be a point size between 22 and 96")
    if spec["印章"] and not spec["成文日期"]:
        warnings.append("加盖印章的公文需要成文日期")

    spec["正文"] = parse_body(body, "正文", fixes, warnings)
    if not any(kind == "para" for kind, _ in spec["正文"]):
        raise SourceError("正文 is empty")
    return spec, fixes, warnings


# ---------------------------------------------------------------- DOCX 结构


def element(tag, **attributes):
    node = OxmlElement(tag)
    for key, value in attributes.items():
        node.set(qn(f"w:{key}"), str(value))
    return node


def run_properties(font, size, color=None, bold=False):
    # 仿宋、楷体正文里的数字和字母用 Times New Roman；标题、黑体和页码沿用同一字体。
    latin = LATIN if font in (FANGSONG, KAITI) else font
    properties = element("w:rPr")
    properties.append(element("w:rFonts", ascii=latin, hAnsi=latin, eastAsia=font, cs=latin, hint="eastAsia"))
    if bold:
        properties.append(element("w:b"))
    if color:
        properties.append(element("w:color", val=color))
    properties.append(element("w:sz", val=round(size * 2)))
    properties.append(element("w:szCs", val=round(size * 2)))
    return properties


def run(text, font, size, color=None, bold=False):
    node = element("w:r")
    node.append(run_properties(font, size, color, bold))
    for index, piece in enumerate(text.split("\t")):
        if index:
            node.append(element("w:tab"))
        if piece:
            content = element("w:t")
            content.text = piece
            content.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            node.append(content)
    return node


def paragraph_properties(align="both", left=0.0, right=0.0, first=0.0, unit=CHAR3, line=PITCH, before=0, after=0,
                         snap=True, page_break=False, tabs=(), rule=None):
    """按 OOXML 规定的子元素顺序生成段落属性；缩进以字为单位，行距一律为固定值。"""
    properties = element("w:pPr")
    if page_break:
        properties.append(element("w:pageBreakBefore"))
    properties.append(element("w:widowControl", val=0))
    if rule:
        borders = element("w:pBdr")
        borders.append(element("w:top", val="single", sz=rule[0], space=0, color=rule[1]))
        properties.append(borders)
    if tabs:
        stops = element("w:tabs")
        for kind, position in tabs:
            stops.append(element("w:tab", val=kind, pos=round(position)))
        properties.append(stops)
    # 公文中汉字与数字、字母之间不加额外间距（Word 默认会自动加）。
    properties.append(element("w:autoSpaceDE", val=0))
    properties.append(element("w:autoSpaceDN", val=0))
    if not snap:
        properties.append(element("w:snapToGrid", val=0))
    properties.append(element("w:spacing", before=round(before), after=round(after), line=round(line), lineRule="exact"))
    indent = {"left": round(left * unit), "right": round(right * unit)}
    if first >= 0:
        indent["firstLine"] = round(first * unit)
    else:
        indent["hanging"] = round(-first * unit)
    properties.append(element("w:ind", **indent))
    properties.append(element("w:jc", val=align))
    return properties


class Writer:
    """按顺序写段落和表格，同时记下每段的纯文本，供渲染后定位。"""

    def __init__(self):
        self.doc = Document()
        self.body = self.doc.element.body
        self.marks = []  # (key, 去掉空白的文本)；表格记为 (key, None)
        configure(self.doc)

    def _append(self, node):
        self.body.find(qn("w:sectPr")).addprevious(node)
        return node

    def paragraph(self, runs=(), key=None, **layout):
        node = element("w:p")
        node.append(paragraph_properties(**layout))
        text = ""
        for item in runs:
            node.append(run(*item))
            text += item[0]
        plain = re.sub(r"\s+", "", text)
        if plain:
            self.marks.append((key, plain))
        return self._append(node)

    def blank(self, count=1):
        for _ in range(count):
            self.paragraph()

    def table(self, rows, columns, borders, padding, key=None, skip=False):
        """rows 是二维 [(runs, layout)]；borders 是表格级线宽 {边: 1/8 磅}，padding 是单元格左右边距。
        skip 为真时，渲染后定位跳过表格内容（普通表格各列的行无法逐段对应）。"""
        table = element("w:tbl")
        properties = element("w:tblPr")
        properties.append(element("w:tblW", w=TEXT_WIDTH, type="dxa"))
        properties.append(element("w:tblInd", w=0, type="dxa"))
        lines = element("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            size = borders.get(side)
            lines.append(element(f"w:{side}", val="single", sz=size, space=0, color="000000") if size
                         else element(f"w:{side}", val="nil"))
        properties.append(lines)
        properties.append(element("w:tblLayout", type="fixed"))
        margins = element("w:tblCellMar")
        for side, value in (("top", 0), ("left", padding), ("bottom", 0), ("right", padding)):
            margins.append(element(f"w:{side}", w=value, type="dxa"))
        properties.append(margins)
        properties.append(element("w:tblLook", val="0000"))
        table.append(properties)
        grid = element("w:tblGrid")
        for column in columns:
            grid.append(element("w:gridCol", w=column))
        table.append(grid)
        for cells in rows:
            row = element("w:tr")
            row_properties = element("w:trPr")
            row_properties.append(element("w:cantSplit"))
            row.append(row_properties)
            for column, (runs, layout) in zip(columns, cells):
                cell = element("w:tc")
                cell_properties = element("w:tcPr")
                cell_properties.append(element("w:tcW", w=column, type="dxa"))
                cell.append(cell_properties)
                paragraph = element("w:p")
                paragraph.append(paragraph_properties(**layout))
                for item in runs:
                    paragraph.append(run(*item))
                cell.append(paragraph)
                row.append(cell)
            table.append(row)
        text = "".join(re.sub(r"\s+", "", item[0]) for cells in rows for runs, _ in cells for item in runs)
        self.marks.append((key, None if skip else text))
        return self._append(table)


def configure(doc):
    """页面、网格、默认字体与奇偶页页码。"""
    styles = doc.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    character = defaults.find(qn("w:rPrDefault"))
    character.remove(character.find(qn("w:rPr")))
    defaults_run = run_properties(FANGSONG, SIZE3)
    defaults_run.append(element("w:lang", val="en-US", eastAsia="zh-CN", bidi="ar-SA"))
    character.append(defaults_run)
    paragraph = defaults.find(qn("w:pPrDefault"))
    paragraph.remove(paragraph.find(qn("w:pPr")))
    paragraph.append(paragraph_properties())
    # 默认样式集里的 Normal 也带字号和段后，清掉以免覆盖文档默认值。
    normal = doc.styles["Normal"].element
    for child in list(normal):
        if child.tag in (qn("w:pPr"), qn("w:rPr")):
            normal.remove(child)

    section = doc.sections[0]
    properties = section._sectPr
    for child in list(properties):
        if child.tag in (qn("w:pgSz"), qn("w:pgMar"), qn("w:cols"), qn("w:docGrid")):
            properties.remove(child)
    properties.append(element("w:pgSz", w=round(210 * MM), h=round(297 * MM)))
    properties.append(element("w:pgMar", top=round(TOP * MM), right=round(OUTSIDE * MM), bottom=round(BOTTOM * MM),
                              left=round(INSIDE * MM), header=851, footer=FOOTER, gutter=0))
    properties.append(element("w:cols", space=425))
    properties.append(element("w:docGrid", type="linesAndChars", linePitch=PITCH, charSpace=CHAR_SPACE))

    settings = doc.settings.element
    # 双面印刷时背面版心与正面对齐：对称页边距让偶数页的订口在右侧。schema 规定它排在 zoom 之后。
    zoom = settings.find(qn("w:zoom"))
    if zoom is not None:
        zoom.addnext(element("w:mirrorMargins"))
    else:
        settings.insert(0, element("w:mirrorMargins"))
    doc.settings.odd_and_even_pages_header_footer = True
    page_number(section.footer, "right")
    page_number(section.even_page_footer, "left")

    # 模板自带的作者、日期等属性不属于这份公文。
    core = doc.core_properties
    core.author = core.last_modified_by = core.comments = core.keywords = core.subject = core.category = ""
    core.created = core.modified = datetime.now(timezone.utc).replace(microsecond=0)


def page_number(footer, side):
    """4 号半角宋体，数字左右各一条一字线；单页码居右空一字，双页码居左空一字。"""
    footer.is_linked_to_previous = False
    container = footer._element
    for child in list(container):
        container.remove(child)
    node = element("w:p")
    node.append(paragraph_properties(align=side, unit=CHAR4, line=360, snap=False,
                                     left=1 if side == "left" else 0, right=1 if side == "right" else 0))
    node.append(run("— ", SONGTI, SIZE4))
    field = element("w:fldSimple", instr=" PAGE ")
    field.append(run("1", SONGTI, SIZE4))
    node.append(field)
    node.append(run(" —", SONGTI, SIZE4))
    container.append(node)


def finish_package(path):
    """在 fontTable 里声明替代字体，再原子写回。"""
    path = Path(path)
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(path) as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]
    fonts = "".join(
        f'<w:font w:name="{name}"><w:altName w:val="{alt}"/><w:charset w:val="86"/>'
        f'<w:family w:val="{"roman" if name == XIAOBIAOSONG else "modern"}"/><w:pitch w:val="fixed"/></w:font>'
        for name, alt in ALT_NAMES.items()
    )
    staged = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as target:
        for item, data in entries:
            if item.filename == "word/fontTable.xml":
                text = data.decode("utf-8")
                for name in ALT_NAMES:
                    text = re.sub(rf'<w:font w:name="{re.escape(name)}">.*?</w:font>', "", text, flags=re.S)
                text = text.replace(f'xmlns:w="{namespace}">', f'xmlns:w="{namespace}">{fonts}', 1)
                if fonts not in text:
                    text = re.sub(r"(<w:fonts\b[^>]*>)", r"\1" + fonts, text, count=1)
                data = text.encode("utf-8")
            target.writestr(item, data)
    staged.replace(path)


# ---------------------------------------------------------------- 排版


def body_blocks(writer, blocks, key):
    """正文与附件内容：段首空二字；一、（一）层次分别用黑体、楷体，1.（1）用仿宋。"""
    for kind, value in blocks:
        if kind == "table":
            body_table(writer, value, key)
            continue
        font = {1: HEITI, 2: KAITI}.get(heading_level(value))
        runs = [(value, font or FANGSONG, SIZE3)]
        # 标题后接正文时（「（一）加强领导。各单位要……」），只有标题部分换字体。
        split = re.search(r"[。！？：]", value) if font else None
        if split and split.end() < len(value):
            runs = [(value[:split.end()], font, SIZE3), (value[split.end():], FANGSONG, SIZE3)]
        writer.paragraph(runs, key=key, first=2)


def body_table(writer, rows, key):
    count = max(len(row) for row in rows)
    rows = [row + [""] * (count - len(row)) for row in rows]
    # 列宽按各列最长内容分配，每列至少 3 字宽。
    needs = [max(3, max(width(row[index]) for row in rows)) for index in range(count)]
    total = sum(needs)
    columns = [round(TEXT_WIDTH * need / total) for need in needs]
    columns[-1] = TEXT_WIDTH - sum(columns[:-1])
    padding = 57
    cells = []
    for row_index, row in enumerate(rows):
        # LibreOffice 把横线线宽（0.5 磅 = 10 twips）计入行高，按估算的行数从行距里扣掉，后面的正文才留在网格上。
        lines = max(-(-width(text) // max(1, (column - 2 * padding) // CHAR4)) for text, column in zip(row, columns))
        border = 20 if row_index == 0 else 10
        layout = {"align": "center", "unit": CHAR4, "snap": False, "line": PITCH - -(-border // max(1, lines))}
        cells.append([([(text, HEITI if row_index == 0 else FANGSONG, SIZE4)], layout) for text in row])
    grid = {side: 4 for side in ("top", "left", "bottom", "right", "insideH", "insideV")}
    writer.table(cells, columns, grid, padding, key=key, skip=True)


def title_lines(writer, lines, key):
    for index, line in enumerate(lines):
        writer.paragraph([(line, XIAOBIAOSONG, SIZE2)], key=key if index == 0 else None, align="center", snap=False)


def compose(spec, plan=None, seal_lines=3):
    """按 GB/T 9704-2012 第 7 章的顺序写出版头、主体和版记。plan 为空时版记紧接内容，用于实测。"""
    writer = Writer()
    writer.doc.core_properties.title = "".join(spec["标题"])
    paragraph, blank = writer.paragraph, writer.blank

    # 版头：份号、密级和保密期限、紧急程度自上而下，3 号黑体顶格。
    marks = [value for value in (spec["份号"], spec["密级"], spec["紧急程度"]) if value]
    for value in marks:
        paragraph([(str(value), HEITI, SIZE3)], align="left", snap=False)
    mark_text = spec["发文机关标志"]
    if mark_text:
        mark_text = str(mark_text).strip()
        size = spec["发文机关标志字号"] or min(48, int(440 / max(width(mark_text), 1)))
        size = max(SIZE2, min(int(size), 96))
        # 行高贴近字号，字形位置就不依赖各软件分配多余行距的方式；段前、段后补足整行。
        line = round(size * 20 * MARK_LEADING)
        before = max(0, round(35 * MM) - 3 * PITCH - round(size * 20 * MARK_INK))
        height = -(-(before + line) // PITCH)
        blank(3 - len(marks))
        paragraph([(mark_text, XIAOBIAOSONG, size, RED)], align="center", snap=False,
                  before=before, line=line, after=height * PITCH - before - line)
        blank(2)
        number_lines(writer, spec)
        # 分隔线下空二行编排标题：第一行空行的上边框就是红色分隔线。
        paragraph(before=RULE_BEFORE, line=PITCH - RULE_BEFORE - RULE_SIZE * 20 // 8, rule=(RULE_SIZE, RED))
        blank()
    elif marks:
        blank()

    title_lines(writer, spec["标题"], "title")
    blank()
    if spec["主送机关"]:
        paragraph([(spec["主送机关"], FANGSONG, SIZE3)], key="recipients")
    body_blocks(writer, spec["正文"], "body")

    attachments = spec["附件"]
    if attachments:
        blank()
        many = len(attachments) > 1
        for index, item in enumerate(attachments):
            number = f"{index + 1}." if many else ""
            hang = width(number)
            label = "附件：" if index == 0 else ""
            # 回行时与上一行附件名称的首字对齐。
            paragraph([(label + number + item["名称"], FANGSONG, SIZE3)], key="attachment_note",
                      left=5 + hang, first=-(hang + (3 if index == 0 else 0)))

    people = [(key, spec[key]) for key in ("出席", "请假", "列席") if spec[key]]
    if people:
        blank()
        for key, value in people:
            paragraph([(key + "：", HEITI, SIZE3), (value, FANGSONG, SIZE3)], key="people", left=5, first=-3)

    signature(writer, spec, seal_lines)
    if spec["附注"]:
        paragraph([(spec["附注"], FANGSONG, SIZE3)], key="note", first=2)

    for index, item in enumerate(attachments):
        if not item["内容"]:
            continue
        label = f"附件{index + 1}" if len(attachments) > 1 else "附件"
        paragraph([(label, HEITI, SIZE3)], key="attachment", align="left", page_break=True)
        blank()
        title_lines(writer, [item["名称"]], "attachment_title")
        blank()
        body_blocks(writer, item["内容"], "attachment_body")

    record(writer, spec, plan)
    return writer


def number_lines(writer, spec):
    """发文字号居中；上行文时居左空一字，与最后一个签发人姓名同行，签发人居右空一字。"""
    number = spec["发文字号"] or ""
    signers = spec["签发人"]
    if not signers:
        writer.paragraph([(number, FANGSONG, SIZE3)], key="number", align="center")
        return
    rows = [signers[index:index + 2] for index in range(0, len(signers), 2)]
    names = [("　".join(row)) for row in rows]
    block = 4 + max(width(name) for name in names)
    start = (28 - 1 - block) * CHAR3
    for index, name in enumerate(names):
        last = index == len(names) - 1
        runs = [(number if last else "", FANGSONG, SIZE3), ("\t", FANGSONG, SIZE3)]
        if index == 0:
            runs.append(("签发人：", FANGSONG, SIZE3))
        runs.append((name, KAITI, SIZE3))
        position = start if index == 0 else start + 4 * CHAR3
        writer.paragraph(runs, key="number", align="left", left=1, tabs=[("left", position)])


def signature(writer, spec, seal_lines):
    """发文机关署名和成文日期（7.3.5）：加盖印章时日期右空四字、署名以日期为准居中；不加盖时署名右空二字。"""
    name, day = spec["署名"], spec["成文日期"]
    if not name and not day:
        return
    name = str(name).strip() if name else ""
    if spec["印章"]:
        writer.blank(seal_lines)  # 留出印章位置：印章顶端距正文一行之内，署名和日期居印章中心偏下
        date_right = 4
        name_right = max(0, date_right + (width(day) - width(name)) / 2) if day else 4
    else:
        writer.blank()
        if name and day:
            date_right = max(2, width(name) - width(day))
            name_right = date_right + width(day) + 2 - width(name)
        else:
            date_right = name_right = 2
    if name:
        writer.paragraph([(name, FANGSONG, SIZE3)], key="signature", align="right", right=name_right)
    if day:
        writer.paragraph([(day, FANGSONG, SIZE3)], key="signature" if not name else "date", align="right",
                         right=date_right)


def record(writer, spec, plan):
    """版记（7.4）：抄送与印发机关和印发日期，粗线在上下，中间细线；末条分隔线与版心下边缘重合。"""
    rows = []
    if spec["抄送"]:
        rows.append([([("抄送：" + spec["抄送"], FANGSONG, SIZE4)],
                      {"align": "both", "unit": CHAR4, "left": 4, "right": 1, "first": -3, "snap": False})])
    if spec["印发机关"] and spec["印发日期"]:
        tab = TEXT_WIDTH - CHAR4
        rows.append([([(f"{spec['印发机关']}\t{spec['印发日期']}印发", FANGSONG, SIZE4)],
                      {"align": "left", "unit": CHAR4, "left": 1, "snap": False, "tabs": [("right", tab)]})])
    if not rows:
        return
    if plan:
        if plan["blank_page"]:
            new_section(writer)
            writer.blank()
        for index in range(max(plan["filler"], 1 if plan["break"] else 0)):
            writer.paragraph(page_break=plan["break"] and index == 0)
    # 首条和末条分隔线用粗线（推荐 0.35 mm），中间用细线（推荐 0.25 mm）。
    borders = {"top": 8, "bottom": 8, "insideH": 6}
    # LibreOffice 把边框线宽计入行高；从最后一行的行距里扣掉，末条线才能落在版心下边缘而不溢出到下一页。
    lines = 1 if spec["印发机关"] and spec["印发日期"] else -(-width("抄送：" + spec["抄送"]) // 29)
    border = (borders["top"] + borders["bottom"] + borders["insideH"] * (len(rows) - 1)) * 20 / 8
    rows[-1][0][1]["line"] = PITCH - -(-(border + 4) // lines)
    writer.table(rows, [TEXT_WIDTH], borders, 0, key="record")


def new_section(writer):
    """版记页前有空白页时，空白页和版记页都不编页码：另起一节，页脚留空。"""
    body = writer.body
    final = body.find(qn("w:sectPr"))
    last = final.getprevious()
    if last is None or last.tag != qn("w:p"):
        last = writer.paragraph(line=20)
    clone = OxmlElement("w:sectPr")
    for child in final:
        clone.append(copy.deepcopy(child))
    last.find(qn("w:pPr")).append(clone)
    for child in list(final):
        if child.tag in (qn("w:footerReference"), qn("w:type")):
            final.remove(child)
    final.insert(0, element("w:type", val="nextPage"))
    section = writer.doc.sections[-1]
    for footer in (section.footer, section.even_page_footer):
        footer.is_linked_to_previous = False
        for child in list(footer._element):
            footer._element.remove(child)
        footer._element.append(element("w:p"))


# ---------------------------------------------------------------- 渲染与实测


# 沙箱没有方正、GB2312 字体，渲染时让 LibreOffice 用相近的开源字体代替，预览里才看得出层次字体的区别。
# Fandol 仿宋、楷体随 TeX Live 中文包安装；字形和字宽与正式字体不同，只用于版面检查。
PREVIEW_FONTS = {
    FANGSONG: ["FandolFang", "Noto Serif CJK SC"], "仿宋": ["FandolFang", "Noto Serif CJK SC"],
    KAITI: ["FandolKai", "Noto Serif CJK SC"], "楷体": ["FandolKai", "Noto Serif CJK SC"],
    HEITI: ["Noto Sans CJK SC", "FandolHei"], XIAOBIAOSONG: ["Noto Serif CJK SC"],
    SONGTI: ["Noto Serif CJK SC", "FandolSong"],
}
FANDOL = "/usr/share/texlive/texmf-dist/fonts/opentype/public/fandol"


def preview_environment(directory):
    """只在使用系统 fontconfig 的 Linux 沙箱里生效；本机 macOS 渲染不受影响。"""
    if not Path("/etc/fonts/fonts.conf").is_file():
        return None
    rules = []
    for family, substitutes in PREVIEW_FONTS.items():
        names = "".join(f"<string>{name}</string>" for name in substitutes)
        weight = '<edit name="weight" mode="assign"><const>bold</const></edit>' if family == XIAOBIAOSONG else ""
        rules.append(f'<match target="pattern"><test name="family"><string>{family}</string></test>'
                     f'<edit name="family" mode="prepend" binding="strong">{names}</edit>{weight}</match>')
    config = directory / "fonts.conf"
    config.write_text(
        '<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>'
        f'<dir>{FANDOL}</dir><cachedir>{directory / "font-cache"}</cachedir>{"".join(rules)}'
        '<include ignore_missing="yes">/etc/fonts/fonts.conf</include></fontconfig>\n', encoding="utf-8")
    return dict(os.environ, FONTCONFIG_FILE=str(config))


def render(docx, pdf):
    """沙箱里用 render-office；本机开发时退回 soffice。没有 LibreOffice 时返回 None。"""
    tool = shutil.which("render-office")
    if tool:
        command = [tool, str(docx), str(pdf), "--timeout", "180"]
    else:
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if not office:
            return None
        command = [office, "--headless", "--convert-to", "pdf", "--outdir", str(pdf.parent), str(docx)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=240,
                            env=preview_environment(pdf.parent))
    produced = pdf if tool else pdf.parent / (docx.stem + ".pdf")
    if result.returncode != 0 or not produced.is_file():
        raise RuntimeError("LibreOffice could not render the document: " + (result.stderr or result.stdout).strip()[-500:])
    if produced != pdf:
        produced.replace(pdf)
    return Path(tool or command[0]).name


def pdf_lines(pdf):
    """版心内的文字行 (页码, 行号, 文本)：同一基线的片段合并，页码等版心外的文字不计。"""
    import pymupdf

    points = 25.4 / 72
    lines = []
    with pymupdf.open(pdf) as document:
        pages = document.page_count
        for number, page in enumerate(document, 1):
            pieces = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = re.sub(r"\s+", "", "".join(span["text"] for span in line["spans"]))
                    if text:
                        x0, y0, _, y1 = line["bbox"]
                        pieces.append(((y0 + y1) / 2 * points, x0, text))
            pieces.sort()
            groups = []
            for center, x0, text in pieces:
                if groups and center - groups[-1][0] < 2.5:
                    groups[-1][1].append((x0, text))
                else:
                    groups.append([center, [(x0, text)]])
            for center, parts in groups:
                if TOP <= center <= TOP + 225:
                    lines.append((number, int((center - TOP) // PITCH_MM), "".join(text for _, text in sorted(parts))))
    return lines, pages


def locate(marks, lines):
    """把写入的段落按顺序对到 PDF 行上，返回每个 key 的首行与末行 (页码, 行号)。表格内容跳过。"""
    found = {}
    position = 0
    skipping = False
    for key, text in marks:
        if text is None:
            skipping = True
            continue
        if skipping:
            head = text[:6]
            while position < len(lines) and not lines[position][2].startswith(head):
                position += 1
            skipping = False
        start = position
        joined = ""
        while position < len(lines) and len(joined) < len(text):
            joined += lines[position][2]
            position += 1
        if joined != text:
            return None
        if key and key not in found:
            found[key] = (lines[start][:2], lines[position - 1][:2])
        elif key:
            found[key] = (found[key][0], lines[position - 1][:2])
    return found


def measure(spec, plan, directory, name, seal_lines=3):
    writer = compose(spec, plan, seal_lines)
    docx = directory / f"{name}.docx"
    writer.doc.save(docx)
    finish_package(docx)
    pdf = directory / f"{name}.pdf"
    renderer = render(docx, pdf)
    if renderer is None:
        return writer, docx, None, None
    lines, pages = pdf_lines(pdf)
    return writer, docx, pdf, {"renderer": renderer, "pages": pages, "found": locate(writer.marks, lines)}


def plan_record(found):
    """版记放在偶数页的最后几行：内容结束页是偶数页且排得下就同页，否则移到下一个偶数页。
    内容结束位置取版记前最后一段的末行；版记自己可能因为排不下已被挤到下一页。"""
    keys = list(found)
    (first_page, first_line), (last_page, last_line) = found["record"]
    height = (last_line - first_line + 1) if last_page == first_page else (LINES - first_line) + last_line + 1
    page, line = found[keys[keys.index("record") - 1]][1] if keys.index("record") else (1, -1)
    free = LINES - 1 - line
    if page % 2 == 0 and height <= free:
        return {"filler": free - height, "break": False, "blank_page": False, "page": page}
    if page % 2 == 1:
        return {"filler": LINES - height, "break": True, "blank_page": False, "page": page + 1}
    return {"filler": LINES - height, "break": True, "blank_page": True, "page": page + 2}


def build(source, output, pdf_output=None):
    meta, body = read_source(source)
    spec, fixes, warnings = prepare(meta, body, source.parent)
    report = {"ok": True, "output": str(output), "fixes": fixes, "warnings": warnings}
    with tempfile.TemporaryDirectory(prefix="gongwen-") as temporary:
        directory = Path(temporary)
        has_record = bool(spec["抄送"] or (spec["印发机关"] and spec["印发日期"]))
        seal_lines = 3
        writer, docx, pdf, layout = measure(spec, None, directory, "probe3", seal_lines)
        if spec["印章"] and layout and layout["found"] and orphan_signature(layout["found"]):
            # 署名页没有正文时，按 7.3.5.5 压缩印章位置的空行；压到 1 行仍不行就保持原样并提醒。
            for lines in (2, 1):
                attempt = measure(spec, None, directory, f"probe{lines}", lines)
                if attempt[3]["found"] and not orphan_signature(attempt[3]["found"]):
                    seal_lines = lines
                    writer, docx, pdf, layout = attempt
                    fixes.append(f"为让署名页带正文，印章位置的空行由 3 行减为 {lines} 行（7.3.5.5）")
                    break
        if layout is None:
            warnings.append("没有 LibreOffice，未实测版面；版记紧接在内容之后，没有压到偶数页底部")
        elif layout["found"] is None:
            warnings.append("渲染结果和源稿对不上，未能实测版面；请用 docx view 逐页检查")
        elif has_record:
            plan = plan_record(layout["found"])
            for _ in range(2):
                writer, docx, pdf, layout = measure(spec, plan, directory, "final", seal_lines)
                found = layout["found"]
                if found is None:
                    break
                end_page, end_line = found["record"][1]
                if end_page == plan["page"] and end_line == LINES - 1:
                    break
                # 行数估计偏差时按实测差值再调一次。
                if end_page == plan["page"]:
                    plan = dict(plan, filler=max(0, plan["filler"] + LINES - 1 - end_line))
                else:
                    plan = dict(plan, filler=max(0, plan["filler"] - 1))
            if not found:
                warnings.append("渲染结果和源稿对不上，未能核对版记位置；请用 docx view 检查最后一页")
            else:
                end_page, end_line = found["record"][1]
                report["record"] = {"page": end_page, "bottom_aligned": end_line == LINES - 1,
                                    "blank_page_before": plan["blank_page"]}
                if end_line != LINES - 1 or end_page % 2:
                    warnings.append("版记没有对齐到偶数页版心底部，请用 docx view 检查最后一页")
        if layout and layout["found"]:
            check_layout(layout["found"], warnings)
            report["pages"] = layout["pages"]
            report["renderer"] = layout["renderer"]
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(docx, output)
        if pdf_output:
            if not pdf:
                raise RuntimeError("cannot write --pdf without LibreOffice")
            pdf_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf, pdf_output)
            report["pdf"] = str(pdf_output)
    return report


def orphan_signature(found):
    """署名、日期和附注没有排在同一页，或那一页上没有正文（只有附件说明也不行）。"""
    if "signature" not in found:
        return False
    page = found["signature"][0][0]
    pages = {found[key][1][0] for key in ("signature", "date", "note") if key in found}
    return pages != {page} or found["body"][1][0] != page


def check_layout(found, warnings):
    body = found.get("body")
    if body and body[0][0] != 1:
        warnings.append("公文首页必须显示正文（7.3.3）：压缩版头、标题或主送机关")
    if orphan_signature(found):
        warnings.append("发文机关署名、成文日期和附注没有和正文排在同一页（7.3.5.5）：精简正文或附件说明，让署名页带正文")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path, help="Markdown source with a YAML header")
    parser.add_argument("--output", type=Path, required=True, help="DOCX path to write")
    parser.add_argument("--pdf", type=Path, help="also save the rendered PDF here")
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"source not found: {args.source}")
    if args.output.suffix.lower() != ".docx":
        parser.error("--output must end with .docx")
    if args.pdf and args.pdf.suffix.lower() != ".pdf":
        parser.error("--pdf must end with .pdf")
    try:
        report = build(args.source, args.output, args.pdf)
    except (SourceError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
