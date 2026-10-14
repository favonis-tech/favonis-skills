import datetime
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/gongwen/scripts/gongwen.py"
spec = importlib.util.spec_from_file_location("gongwen", SCRIPT)
gongwen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gongwen)

# 版面实测需要沙箱的 render-office；本机可以把一个同名包装脚本放进 PATH（要能渲染中文字体）。
HAS_RENDERER = shutil.which("render-office") is not None

HEADER = {
    "发文机关标志": "××市人民政府办公室文件",
    "发文字号": "×政办发〔2026〕12号",
    "标题": "关于开展安全生产检查的通知",
    "主送机关": "各区人民政府",
    "署名": "××市人民政府办公室",
    "成文日期": "2026年10月14日",
    "抄送": "市委办公室",
    "印发机关": "××市人民政府办公室",
    "印发日期": "2026年10月14日",
}
LINE = "为切实防范化解重大安全风险现决定在全市开展安全检查工作啊"[:26]


def source(directory, header, body, name="公文.md"):
    lines = ["---"]
    for key, value in header.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines += ["---", "", body]
    path = Path(directory, name)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_script(directory, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=directory, capture_output=True, text=True, timeout=600)


def document_xml(path, part="word/document.xml"):
    with zipfile.ZipFile(path) as archive:
        return archive.read(part).decode("utf-8")


class PrepareTests(unittest.TestCase):
    def prepare(self, header, body="正文。"):
        return gongwen.prepare(dict({"标题": "关于测试的通知"}, **header), body, Path("."))

    def test_normalizes_number_dates_and_punctuation(self):
        spec, fixes, warnings = self.prepare({
            "份号": 1, "发文字号": "×政发[2026]第012号", "主送机关": "各部门:", "成文日期": "二〇二六年十月四日",
            "印发日期": datetime.date(2026, 1, 5), "印发机关": "办公室", "抄送": "甲单位，乙单位，", "附注": "此件公开发布",
            "附件": ["工作方案。", {"名称": "汇总表"}], "签发人": "张三、李四", "印章": "是",
        })
        self.assertEqual(spec["份号"], "000001")
        self.assertEqual(spec["发文字号"], "×政发〔2026〕12号")
        self.assertEqual(spec["主送机关"], "各部门：")
        self.assertEqual(spec["成文日期"], "2026年10月4日")
        self.assertEqual(spec["印发日期"], "2026年1月5日")
        self.assertEqual(spec["抄送"], "甲单位，乙单位。")
        self.assertEqual(spec["附注"], "（此件公开发布）")
        self.assertEqual([item["名称"] for item in spec["附件"]], ["工作方案", "汇总表"])
        self.assertTrue(spec["印章"])
        self.assertEqual(spec["签发人"], [], "签发人 without a 版头 is dropped")
        self.assertEqual(len(fixes), 5)
        self.assertTrue(any("签发人只在有版头" in warning for warning in warnings))

    def test_warns_about_wrong_formats_but_keeps_minutes_numbers(self):
        _, _, warnings = self.prepare({"发文字号": "第12期", "成文日期": "2026年13月1日", "标题": "关于测试的通知。"})
        self.assertTrue(any("发文字号" in warning for warning in warnings))
        self.assertTrue(any("成文日期" in warning for warning in warnings))
        self.assertTrue(any("标题末尾不加标点" in warning for warning in warnings))
        _, _, warnings = self.prepare({"发文机关标志": "××会议纪要", "发文字号": "第12期"})
        self.assertFalse(any("发文字号" in warning for warning in warnings))

    def test_body_ordinals_and_markdown(self):
        spec, fixes, warnings = self.prepare({}, "## 一. 总体要求\n(一)目标。内容\n1、第一项\n1.5亿元已到位。\n(2)第二项\n- 列表项\n![图](a.png)\n\n**加粗**正文\n"
                                             "| 单位 | 时限 |\n| --- | --- |\n| 甲 | 1月 |")
        paragraphs = [value for kind, value in spec["正文"] if kind == "para"]
        self.assertEqual(paragraphs, ["一、总体要求", "（一）目标。内容", "1.第一项", "1.5亿元已到位。", "（2）第二项", "列表项", "加粗正文"])
        self.assertEqual(spec["正文"][-1], ("table", [["单位", "时限"], ["甲", "1月"]]))
        self.assertEqual([gongwen.heading_level(text) for text in paragraphs], [1, 2, 3, 0, 4, 0, 0])
        self.assertEqual(len([fix for fix in fixes if "层次序数" in fix]), 4)
        self.assertTrue(any("列表符号" in warning for warning in warnings))
        self.assertTrue(any("图片" in warning for warning in warnings))

    def test_rejects_invalid_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            for text, message in [
                ("正文", "YAML header"),
                ("---\n标题: 测试\n作者: 张三\n---\n正文", "unknown header fields"),
                ("---\n- 列表\n---\n正文", "mapping"),
            ]:
                path = Path(directory, "a.md")
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(gongwen.SourceError, message):
                    gongwen.read_source(path)
        for header, message in [
            ({"标题": ""}, "标题 is required"),
            ({"印章": "可能"}, "印章 must be"),
            ({"发文机关标志字号": "42pt"}, "point size"),
            ({"附件": [{"文件": "a.md"}]}, "needs 名称"),
            ({"附件": [{"名称": "方案", "文件": "missing.md"}]}, "attachment file not found"),
        ]:
            with self.assertRaisesRegex(gongwen.SourceError, message):
                gongwen.prepare(dict({"标题": "关于测试的通知"}, **header), "正文。", Path("."))
        with self.assertRaisesRegex(gongwen.SourceError, "正文 is empty"):
            gongwen.prepare({"标题": "关于测试的通知"}, "\n\n", Path("."))


class LocateTests(unittest.TestCase):
    def test_matches_paragraphs_in_order_and_skips_tables(self):
        lines = [(1, 0, "标题"), (1, 2, "第一段前半"), (1, 3, "后半"), (1, 4, "表头甲乙"), (1, 5, "数据"),
                 (2, 0, "标题"), (2, 1, "署名")]
        marks = [("title", "标题"), ("body", "第一段前半后半"), ("body", None), ("body", "标题"), ("signature", "署名")]
        found = gongwen.locate(marks, lines)
        self.assertEqual(found["title"], ((1, 0), (1, 0)))
        self.assertEqual(found["body"], ((1, 2), (2, 0)))
        self.assertEqual(found["signature"], ((2, 1), (2, 1)))
        self.assertIsNone(gongwen.locate([("title", "别的标题")], lines))

    def test_record_plan_uses_the_end_of_content(self):
        same_page = {"body": ((1, 0), (2, 10)), "record": ((2, 11), (2, 12))}
        self.assertEqual(gongwen.plan_record(same_page), {"filler": 9, "break": False, "blank_page": False, "page": 2})
        odd_page = {"body": ((1, 0), (1, 10)), "record": ((1, 11), (1, 12))}
        self.assertEqual(gongwen.plan_record(odd_page), {"filler": 20, "break": True, "blank_page": False, "page": 2})
        # 偶数页只剩一行：版记已被挤到第 3 页，仍按内容结束在第 2 页来规划。
        full = {"body": ((1, 0), (2, 20)), "record": ((3, 0), (3, 1))}
        self.assertEqual(gongwen.plan_record(full), {"filler": 20, "break": True, "blank_page": True, "page": 4})


class DocumentTests(unittest.TestCase):
    def build(self, header, body):
        spec, _, _ = gongwen.prepare(header, body, Path("."))
        writer = gongwen.compose(spec)
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        path = Path(directory, "out.docx")
        writer.doc.save(path)
        gongwen.finish_package(path)
        return path

    def test_page_setup_fonts_and_page_numbers(self):
        path = self.build(dict(HEADER, 签发人=["张三"]), "一、总体要求\n（一）加强领导。各单位要落实责任。\n正文段落。")
        document = document_xml(path)
        self.assertIn('<w:pgSz w:w="11906" w:h="16838"/>', document)
        self.assertRegex(document, r'<w:pgMar w:top="2098" w:right="1474" w:bottom="1984" w:left="1587"')
        self.assertIn('<w:docGrid w:type="linesAndChars" w:linePitch="579" w:charSpace="-849"/>', document)
        settings = document_xml(path, "word/settings.xml")
        self.assertIn("<w:evenAndOddHeaders/>", settings)
        self.assertRegex(settings, r"<w:zoom [^>]*/><w:mirrorMargins/>")
        fonts = document_xml(path, "word/fontTable.xml")
        self.assertIn('<w:font w:name="仿宋_GB2312"><w:altName w:val="仿宋"/>', fonts)
        self.assertIn('<w:font w:name="方正小标宋简体"><w:altName w:val="华文中宋"/>', fonts)
        core = document_xml(path, "docProps/core.xml")
        self.assertIn("<dc:creator></dc:creator>", core)
        self.assertIn("<dc:title>关于开展安全生产检查的通知</dc:title>", core)
        # 标志红色小标宋；第一层黑体；第二层只有标题部分用楷体。
        self.assertRegex(document, r'w:eastAsia="方正小标宋简体"[^>]*/><w:color w:val="FF0000"/>')
        self.assertRegex(document, r'w:eastAsia="黑体"[^<]*/>(?:<[^>]+>)*<w:t xml:space="preserve">一、总体要求</w:t>')
        self.assertRegex(document, r'w:eastAsia="楷体_GB2312"[^<]*/>(?:<[^>]+>)*<w:t xml:space="preserve">（一）加强领导。</w:t>')
        self.assertRegex(document, r'w:eastAsia="仿宋_GB2312"[^<]*/>(?:<[^>]+>)*<w:t xml:space="preserve">各单位要落实责任。</w:t>')
        self.assertIn('<w:t xml:space="preserve">签发人：</w:t>', document)
        self.assertRegex(document, r'<w:autoSpaceDE w:val="0"/><w:autoSpaceDN w:val="0"/>')
        footers = [name for name in zipfile.ZipFile(path).namelist() if name.startswith("word/footer")]
        texts = [document_xml(path, name) for name in footers]
        self.assertEqual(len(texts), 2)
        self.assertEqual(sorted(re.search(r'<w:jc w:val="(\w+)"/>', text)[1] for text in texts), ["left", "right"])
        self.assertTrue(all('w:instr=" PAGE "' in text for text in texts))
        # 版记粗线在上下、细线在中间。
        self.assertRegex(document, r'<w:top w:val="single" w:sz="8"[^>]*/>.*<w:bottom w:val="single" w:sz="8"[^>]*/>'
                                   r'.*<w:insideH w:val="single" w:sz="6"')

    def test_plain_document_has_no_header_or_record(self):
        path = self.build({"标题": "关于国庆节放假的通知", "主送机关": "各部门", "署名": "综合部", "成文日期": "2026年9月20日"},
                          "现将放假安排通知如下。")
        document = document_xml(path)
        self.assertNotIn("FF0000", document)
        self.assertNotIn("<w:tbl>", document)


@unittest.skipUnless(HAS_RENDERER, "needs render-office with Chinese fonts")
class LayoutTests(unittest.TestCase):
    def typeset(self, directory, header, body, *extra):
        path = source(directory, header, body)
        result = run_script(directory, path.name, "--output", "out/公文.docx", "--pdf", "out/公文.pdf", *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        lines, pages = gongwen.pdf_lines(Path(directory, "out/公文.pdf"))
        return report, lines, pages

    def test_full_document_grid_header_and_record(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "附件1.md").write_text("一、工作目标\n全面排查安全隐患。\n| 单位 | 时限 |\n| --- | --- |\n| 甲 | 1月 |\n"
                                                 "| 乙 | 2月 |\n二、工作步骤\n分三个阶段进行。", encoding="utf-8")
            header = dict(HEADER, 份号="000001", 附件=[{"名称": "工作方案", "文件": "附件1.md"}], 印章=True)
            report, lines, pages = self.typeset(directory, header, "\n".join([LINE] * 12))
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["record"], {"page": pages, "bottom_aligned": True, "blank_page_before": False})
            self.assertEqual(pages % 2, 0)
            first_page = [line for line in lines if line[0] == 1]
            self.assertEqual(first_page[-1][1], gongwen.LINES - 1, "page 1 holds 22 lines")
            self.assertTrue(all(len(text) <= 29 for page, _, text in lines if text.startswith(LINE[:5])))
            # 正文表格之后的段落仍在网格上：附件第二部分紧接表格。
            table_end = next((page, index) for page, index, text in lines if text.startswith("乙"))
            self.assertEqual(next((page, index) for page, index, text in lines if text == "二、工作步骤"),
                             (table_end[0], table_end[1] + 1))
            with pymupdf.open(Path(directory, "out/公文.pdf")) as document:
                page = document[0]
                pixels = page.get_pixmap(dpi=150)
                red = [y for y in range(round(100 / 25.4 * 150)) for x in range(0, pixels.width, 4)
                       if (lambda r, g, b: r > 180 and g < 90 and b < 90)(*pixels.pixel(x, y))]
                top = min(red) * 25.4 / 150
                # 标志上边缘距版心上边缘 35 mm（容差覆盖替代字体的差别）。
                self.assertAlmostEqual(top - gongwen.TOP, 35, delta=1.5)
                last = document[-1]
                rules = [item["rect"] for item in last.get_drawings() if item["rect"].width * 25.4 / 72 > 150]
                bottom = max(rect.y1 for rect in rules) * 25.4 / 72
                self.assertAlmostEqual(bottom, gongwen.TOP + 225, delta=1.0)

    def test_blank_page_before_record_has_no_page_numbers(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as directory:
            header = {key: HEADER[key] for key in ("标题", "主送机关", "署名", "成文日期", "抄送", "印发机关", "印发日期")}
            for count in range(36, 40):
                report, lines, pages = self.typeset(directory, header, "\n".join([LINE] * count))
                if report["record"]["blank_page_before"]:
                    break
            else:
                self.fail("no body length produced a blank page before the record")
            self.assertEqual(pages, 4)
            self.assertTrue(report["record"]["bottom_aligned"])
            self.assertFalse([line for line in lines if line[0] == 3])
            with pymupdf.open(Path(directory, "out/公文.pdf")) as document:
                numbers = ["—" in document[index].get_text() for index in range(4)]
            self.assertEqual(numbers, [True, True, False, False])

    def test_reports_signature_without_body_text(self):
        with tempfile.TemporaryDirectory() as directory:
            header = {key: HEADER[key] for key in ("标题", "主送机关", "署名", "成文日期")}
            # 正文刚好排满第 1 页：署名和日期只能落到第 2 页。
            report, lines, pages = self.typeset(directory, header, "\n".join([LINE] * 19))
            self.assertEqual(pages, 2)
            self.assertTrue(any("署名" in warning for warning in report["warnings"]))


class ArgumentTests(unittest.TestCase):
    def test_rejects_bad_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = source(directory, HEADER, "正文。")
            for args, message in [(["missing.md", "--output", "a.docx"], "source not found"),
                                  ([path.name, "--output", "a.pdf"], "--output must end with .docx"),
                                  ([path.name, "--output", "a.docx", "--pdf", "a.png"], "--pdf must end with .pdf")]:
                result = run_script(directory, *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
            Path(directory, "bad.md").write_text("---\n作者: 张三\n---\n正文", encoding="utf-8")
            result = run_script(directory, "bad.md", "--output", "a.docx")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["ok"])



if __name__ == "__main__":
    unittest.main()
