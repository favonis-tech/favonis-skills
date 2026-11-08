import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

SCRIPT = Path(__file__).resolve().parents[1] / "skills/resume/scripts/resume.py"
spec = importlib.util.spec_from_file_location("resume", SCRIPT)
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)

CHROMIUM = os.environ.get("RESUME_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
HAS_BROWSER = bool(CHROMIUM and all(importlib.util.find_spec(m) for m in ("playwright", "pymupdf")))
HAS_DOCX = importlib.util.find_spec("docx") is not None
HAS_OFFICE = bool(shutil.which("render-office") or shutil.which("soffice") or shutil.which("libreoffice"))

SOURCE = """\
name: 林晓
headline: 求职意向：后端开发工程师
contacts: [186-0000-1234, linxiao@example.com, 杭州, github.com/linxiao-dev]
sections:
  - title: 教育背景
    entries:
      - title: 浙江工业大学
        subtitle: 计算机科学与技术 · 本科
        date: 2022.10 – 2026.06
        note: GPA 3.70/4.0
  - title: 实习经历
    entries:
      - title: 某电商平台
        subtitle: 后端开发实习生
        date: 2025.07 – 2025.12
        bullets:
          - "**订单查询提速**：改为游标分页并补齐覆盖索引，P99 延迟由 820 ms 降到 160 ms，已全量上线"
          - 把每日对账脚本拆成按商户分片的定时任务，夜间任务时长从 3 小时缩短到 50 分钟
  - title: 专业技能
    items:
      - label: 语言
        text: Go、Java、Python、SQL
      - 熟悉 Linux 与 Docker
  - title: 荣誉奖项
    bullets: [2024 年 CCPC 省赛银奖]
"""
BULLET = "定位订单详情接口慢查询的根因是联表加深分页，改为游标分页并补齐覆盖索引，P99 延迟由 820 ms 降到 160 ms，已全量上线"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def write(directory, text, name="简历.yaml"):
    path = Path(directory, name)
    path.write_text(text, encoding="utf-8")
    return path


def run_script(directory, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=directory, capture_output=True, text=True, timeout=600)


def with_bullets(count):
    lines = "\n".join(f"          - 第 {n} 条：{BULLET}" for n in range(count))
    return SOURCE.replace("        bullets:\n          - \"**订单查询提速**", f"        bullets:\n{lines}\n          - \"**订单查询提速**", 1)


class SourceTests(unittest.TestCase):
    def test_reads_values_as_written(self):
        with tempfile.TemporaryDirectory() as directory:
            source = resume.read_source(write(directory, SOURCE + "pages: 2\n"))
        education = source["sections"][0]["entries"][0]
        self.assertEqual(education["date"], "2022.10 – 2026.06")
        self.assertEqual(education["note"], "GPA 3.70/4.0")
        self.assertEqual(source["template"], "serif")
        self.assertIsNone(source["accent"], "the template supplies the accent when none is written")
        self.assertEqual(source["pages"], 2)
        skills = source["sections"][2]["items"]
        self.assertEqual(skills[0], {"label": "语言", "text": "Go、Java、Python、SQL"})
        self.assertEqual(skills[1], {"label": None, "text": "熟悉 Linux 与 Docker"})

    def test_keeps_leading_zeros_and_joins_wrapped_lines(self):
        text = "name: 林晓\ncontacts: [057188886666]\nsections:\n  - title: 自我评价\n    text: |\n      做过三个\n      上线项目，\n      熟悉 Go\n      and Kafka\n"
        with tempfile.TemporaryDirectory() as directory:
            source = resume.read_source(write(directory, text))
        self.assertEqual(source["contacts"], ["057188886666"])
        self.assertEqual(source["sections"][0]["text"], "做过三个上线项目，熟悉 Go and Kafka")

    def test_rejects_invalid_sources(self):
        cases = [
            ("name: 林晓\nsections: []\n", "sections must be a non-empty list"),
            ("name: 林晓\ncompany: x\nsections: [{title: a, text: b}]\n", "unknown field company"),
            ("sections: [{title: a, text: b}]\n", "name is required"),
            ("name: 林晓\nsections: [{title: 技能, text: b, bullets: [c]}]\n", "exactly one of"),
            ("name: 林晓\nsections: [{title: 经历, entries: [{subtitle: x}]}]\n", r"entries\[0\].title is required"),
            ("name: 林晓\ntemplate: fancy\nsections: [{title: a, text: b}]\n", "template must be one of"),
            ("name: 林晓\npages: 3\nsections: [{title: a, text: b}]\n", "pages must be 1 or 2"),
            ("name: 林晓\naccent: blue\nsections: [{title: a, text: b}]\n", "accent must be a color"),
            ("name: 林晓\nphoto: me.jpg\nsections: [{title: a, text: b}]\n", "photo not found"),
            ("name: [林晓\n", "invalid YAML"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for text, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(resume.SourceError, message):
                    resume.read_source(write(directory, text))

    def test_inline_runs(self):
        runs = resume.runs("用 **[MiniMQ](github.com/a/b) 与 【待补充：QPS】** 做到")
        self.assertEqual([(r.text, r.bold, r.url, r.todo) for r in runs], [
            ("用 ", False, None, False),
            ("MiniMQ", True, "https://github.com/a/b", False),
            (" 与 ", True, None, False),
            ("【待补充：QPS】", True, None, True),
            (" 做到", False, None, False),
        ])
        self.assertEqual(resume.inline("a < b **c**"), "a &lt; b <strong>c</strong>")

    def test_contact_links(self):
        def link(text):
            return [run.url for run in resume.contact_runs(text)]
        self.assertEqual(link("linxiao@example.com"), ["mailto:linxiao@example.com"])
        self.assertEqual(link("github.com/linxiao"), ["https://github.com/linxiao"])
        self.assertEqual(link("https://linxiao.dev"), ["https://linxiao.dev"])
        self.assertEqual(link("186-0000-1234"), [None])
        self.assertEqual(link("杭州"), [None])

    def test_source_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = resume.read_source(write(directory, SOURCE.replace("GPA 3.70/4.0", "GPA 【待补充：排名】")))
            no_contact = resume.read_source(write(directory, SOURCE.replace("186-0000-1234, linxiao@example.com, ", "")))
        warnings = resume.source_warnings(source)
        self.assertEqual([(w["code"], w["where"], w["text"]) for w in warnings],
                         [("placeholder", "教育背景 › 浙江工业大学", "【待补充：排名】")])
        self.assertEqual([w["code"] for w in resume.source_warnings(no_contact)], ["no_contact"])

    def test_layout_warnings(self):
        blocks = [
            {"where": "a › 1", "bullet": True, "text": "x" * 200, "lines": 4, "last": 0.05},
            {"where": "a › 2", "bullet": True, "text": "一二三四五六七八九十工单", "lines": 2, "last": 0.06},
            {"where": "a › 3", "bullet": True, "text": "y", "lines": 2, "last": 0.5},
            {"where": "a", "bullet": False, "text": "z", "lines": 1, "last": 0.05},
        ]
        warnings = resume.layout_warnings(blocks)
        self.assertEqual([(w["code"], w["where"]) for w in warnings], [("long_bullet", "a › 1"), ("stub_line", "a › 2")])
        self.assertEqual(warnings[1]["tail"], "七八九十工单")

    def test_density_and_colors(self):
        floor, ceiling = resume.density(resume.FLOOR), resume.density(resume.CEILING)
        self.assertLess(floor.leading, ceiling.leading)
        self.assertLess(floor.margin_y, ceiling.margin_y)
        self.assertEqual(resume.mix("#1f4e79", 1), "1F4E79")
        self.assertEqual(resume.mix("#000000", 0.5), "80" * 3)
        self.assertEqual(resume.mix("#ffffff", 0.5, "#000000"), "80" * 3)

    def test_text_width_estimate(self):
        self.assertEqual(resume.text_em("教育背景"), 4)
        self.assertTrue(8 < resume.text_em("2024.07 – 2025.06") < 10)
        self.assertLess(resume.text_em("Skills"), resume.text_em("SKILLS"))


ORDERS = {"pPr": resume.PPR_ORDER, "rPr": resume.RPR_ORDER, "tblPr": resume.TBLPR_ORDER, "tcPr": resume.TCPR_ORDER}


def fills(root, path):
    return {element.get(W + "fill") for element in root.iterfind(path)}


@unittest.skipUnless(HAS_DOCX, "needs python-docx")
class DocxTests(unittest.TestCase):
    def word(self, directory, source, template):
        source.update(template=template, accent=resume.TEMPLATE_ACCENTS[template])
        path = Path(directory, f"{template}.docx")
        resume.docx_document(source, 10.4).save(path)
        with zipfile.ZipFile(path) as archive:
            return archive.read("word/document.xml").decode(), archive.read("word/_rels/document.xml.rels").decode()

    def assert_property_order(self, root):
        # 属性元素的子元素顺序错了 Word 会报文件损坏。
        for element in root.iter():
            name = element.tag.removeprefix(W)
            if name in ORDERS:
                children = ["w:" + child.tag.removeprefix(W) for child in element]
                positions = [ORDERS[name].index(child) for child in children]
                self.assertEqual(positions, sorted(positions), f"{name}: {children}")

    def test_word_version_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = resume.read_source(write(directory, SOURCE.replace("GPA 3.70/4.0", "GPA 【待补充】")))
            for template, accent in resume.TEMPLATE_ACCENTS.items():
                xml, rels = self.word(directory, source, template)
                root = ElementTree.fromstring(xml)
                with self.subTest(template=template):
                    self.assertIn("<w:hyperlink", xml)
                    self.assertIn("https://github.com/linxiao-dev", rels)
                    self.assertIn('w:highlight w:val="yellow"', xml)
                    self.assert_property_order(root)
                    accent = accent[1:].upper()
                    # 底纹只出现在各自的位置：现代的标题底带、时间轴的色签、色块页头的单元格。
                    self.assertEqual(bool(fills(root, f".//{W}pPr/{W}shd")), template == "modern")
                    self.assertEqual(fills(root, f".//{W}rPr/{W}shd"), {accent} if template == "timeline" else set())
                    self.assertEqual(fills(root, f".//{W}tcPr/{W}shd"), {accent} if template == "banner" else set())
                    floating = root.find(f".//{W}tblpPr")
                    self.assertEqual(floating is not None and floating.get(W + "vertAnchor"), template == "banner" and "page")
                    self.assertEqual(root.find(f".//{W}tcBorders/{W}left") is not None, template == "sidebar")

    def test_word_photo_keeps_its_size(self):
        # 正文是固定行距，照片段落要单倍行距才不被裁成一行高；表格要写列宽，LibreOffice 按列宽排。
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "me.png").write_bytes(PNG)
            source = resume.read_source(write(directory, "photo: me.png\n" + SOURCE))
            for template in resume.TEMPLATE_ACCENTS:
                root = ElementTree.fromstring(self.word(directory, source, template)[0])
                with self.subTest(template=template):
                    holders = [p for p in root.iter(W + "p") if p.find(f".//{W}drawing") is not None]
                    self.assertEqual(len(holders), 1)
                    self.assertEqual(holders[0].find(f"{W}pPr/{W}spacing").get(W + "lineRule"), "auto")
                    text, photo = (int(column.get(W + "w")) for column in root.find(f".//{W}tblGrid"))
                    self.assertGreater(text, 3 * photo)

    def test_long_entry_head_moves_the_subtitle_down(self):
        # 标题行放不下时日期留在第一行右端，副标题换到第二行，不让日期被挤断。
        long = SOURCE.replace("subtitle: 后端开发实习生", "subtitle: 后端开发实习生 · 交易中台订单查询与夜间对账任务方向 · 浙江杭州滨江区")
        with tempfile.TemporaryDirectory() as directory:
            wide = self.word(directory, resume.read_source(write(directory, long)), "sidebar")[0]
            short = self.word(directory, resume.read_source(write(directory, SOURCE)), "classic")[0]
        head = next(chunk for chunk in wide.split("<w:p>") if "某电商平台" in chunk)
        self.assertLess(head.index("2025.07"), head.index("<w:br/>"))
        self.assertLess(head.index("<w:br/>"), head.index("交易中台"))
        self.assertNotIn("<w:br/>", next(chunk for chunk in short.split("<w:p>") if "某电商平台" in chunk))


@unittest.skipUnless(HAS_BROWSER, "needs Chromium (RESUME_CHROMIUM or chromium on PATH), Playwright and PyMuPDF")
class BuildTests(unittest.TestCase):
    def build(self, text, *args):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, text)
            result = run_script(directory, "简历.yaml", "--output", "out/简历.pdf", *args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(Path(directory, "out/简历.pdf").is_file())
            return report

    def test_fills_one_page_and_shrinks_for_more_content(self):
        normal = self.build(with_bullets(8))
        heavy = self.build(with_bullets(16))
        for report in (normal, heavy):
            self.assertEqual((report["fit"], report["pages"]), ("ok", 1), report)
            self.assertGreater(report["fill"], 0.85)
        self.assertLess(heavy["font_pt"], normal["font_pt"])
        self.assertEqual(normal["template"], "serif")

    def test_reports_overflow_and_sparse(self):
        over = self.build(with_bullets(60))
        self.assertEqual(over["fit"], "overflow")
        self.assertEqual(over["font_pt"], resume.FLOOR)
        self.assertGreater(over["overflow_lines"], 10)
        sparse = self.build(SOURCE)
        self.assertEqual((sparse["fit"], sparse["font_pt"]), ("sparse", resume.CEILING))
        two = self.build(SOURCE + "pages: 2\n")
        self.assertEqual((two["fit"], two["pages"], two["target_pages"]), ("sparse", 1, 2))
        self.assertTrue(any(w["code"] == "long_bullet" for w in self.build(SOURCE.replace("50 分钟", "50 分钟。" + BULLET * 3))["warnings"]))

    def test_template_override_and_failure(self):
        report = self.build(with_bullets(8), "--template", "modern")
        self.assertEqual(report["template"], "modern")
        with tempfile.TemporaryDirectory() as directory:
            write(directory, "name: 林晓\nsections: []\n")
            result = run_script(directory, "简历.yaml", "--output", "简历.pdf")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["ok"])
            self.assertEqual(run_script(directory, "简历.yaml", "--output", "简历.docx").returncode, 2)

    def test_screen_width_matches_the_page(self):
        # 字号先按屏幕上量的高度挑选：模板若改了版心宽度，量出的行数和打印出来的就对不上。
        with tempfile.TemporaryDirectory() as directory:
            source = resume.read_source(write(directory, SOURCE))
        expected = (resume.PAGE_W - 2 * resume.density(10.4).margin_x) * resume.PX_PER_MM
        browser = resume.Browser()
        try:
            for template, accent in resume.TEMPLATE_ACCENTS.items():
                source.update(template=template, accent=accent)
                browser.load(resume.document_html(source, 10.4))
                width = browser.page.evaluate("""() => {
                  const sheet = document.querySelector('.sheet'), style = getComputedStyle(sheet);
                  return sheet.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
                }""")
                self.assertAlmostEqual(width, expected, delta=1, msg=template)
        finally:
            browser.close()

    def test_column_layouts(self):
        """时间轴的日期和条目各成一列，侧栏的分节标题在内容左侧并与页头对齐，色块页头铺到纸边；三者都排满一页。"""
        import pymupdf

        def lines(path):
            """每行文字 → (左缘, 底边, 右缘)。中文逐字成段，个别字形的竖直范围不准，所以左缘和底边取首字、右缘取末字。"""
            with pymupdf.open(path) as document:
                page = document[0]
                corner = page.get_pixmap(clip=pymupdf.Rect(0, 0, 4, 4)).pixel(1, 1)
                found = {}
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        first, last = line["spans"][0]["bbox"], line["spans"][-1]["bbox"]
                        found.setdefault("".join(span["text"] for span in line["spans"]).strip(), (first[0], first[3], last[2]))
            return found, corner

        with tempfile.TemporaryDirectory() as directory:
            write(directory, with_bullets(10))
            pages = {}
            for template in ("timeline", "sidebar", "banner"):
                result = run_script(directory, "简历.yaml", "--output", f"{template}.pdf", "--template", template)
                report = json.loads(result.stdout)
                self.assertEqual((report["fit"], report["pages"]), ("ok", 1), report)
                self.assertGreater(report["fill"], 0.85, template)
                pages[template] = lines(Path(directory, f"{template}.pdf"))
        timeline, _ = pages["timeline"]
        self.assertAlmostEqual(timeline["2022.10 – 2026.06"][0], timeline["2025.07 – 2025.12"][0], delta=0.5)
        self.assertAlmostEqual(timeline["浙江工业大学"][0], timeline["某电商平台"][0], delta=0.5)
        self.assertGreater(timeline["浙江工业大学"][0], timeline["2022.10 – 2026.06"][2])
        sidebar, _ = pages["sidebar"]
        self.assertLess(sidebar["教育背景"][2], sidebar["浙江工业大学"][0])
        self.assertAlmostEqual(sidebar["教育背景"][1], sidebar["浙江工业大学"][1], delta=2)
        self.assertAlmostEqual(sidebar["林晓"][0], sidebar["浙江工业大学"][0], delta=1)
        _, corner = pages["banner"]
        accent = bytes.fromhex(resume.TEMPLATE_ACCENTS["banner"][1:])
        self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(corner, accent)), f"the band reaches the paper's corner: {corner}")

    @unittest.skipUnless(HAS_DOCX and HAS_OFFICE, "needs python-docx and LibreOffice")
    def test_word_version_fits_the_pages(self):
        report = self.build(with_bullets(8), "--docx", "out/简历.docx")
        self.assertEqual(report["docx"]["pages"], 1)
        self.assertLessEqual(report["docx"]["font_pt"], report["font_pt"])


if __name__ == "__main__":
    unittest.main()
