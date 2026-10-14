"""Check that an edited Markdown file kept the parts a prose edit must not change, and print a JSON report.

Adapted from Humanizer-zh tests/check_structure.py (MIT).
"""

import argparse
import json
import re
import sys
from pathlib import Path


def protected_parts(text):
    """润色只改散文；这些部分必须原样保留。编号列表的文字属于散文，可以润色，不在其中。"""
    text = text.replace("\r\n", "\n")
    frontmatter = re.match(r"\A---\n.*?\n---\n", text, re.S)
    blocks = re.findall(r"^(?:`{3,}|~{3,})[^\n]*\n.*?^(?:`{3,}|~{3,})[ \t]*$", text, re.M | re.S)
    prose = re.sub(r"^(?:`{3,}|~{3,})[^\n]*\n.*?^(?:`{3,}|~{3,})[ \t]*$", "", text, flags=re.M | re.S)
    return {
        "frontmatter": [frontmatter.group(0)] if frontmatter else [],
        "fenced_code": blocks,
        "inline_code": re.findall(r"(?<!`)`([^`\n]+)`(?!`)", prose),
        "headings": re.findall(r"^#{1,6} .+$", prose, re.M),
        "link_targets": re.findall(r"\]\(([^\s)]+)[^)]*\)", prose),
        "table_rows": re.findall(r"^\|.*\|$", prose, re.M),
        "explicit_ids": re.findall(r'<[^>]+\bid="[^"]+"[^>]*>', prose),
    }


def compare(source, edited):
    before, after = protected_parts(source), protected_parts(edited)
    report = {"passed": True, "changed": {}}
    for key in before:
        if before[key] != after[key]:
            report["passed"] = False
            missing = [item for item in before[key] if item not in after[key]]
            added = [item for item in after[key] if item not in before[key]]
            # 只回显前几项，避免把长代码块整段打印出来。
            report["changed"][key] = {"missing": [item[:200] for item in missing[:5]],
                                      "added": [item[:200] for item in added[:5]],
                                      "count_before": len(before[key]), "count_after": len(after[key])}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path, help="copy of the file before editing")
    parser.add_argument("edited", type=Path, help="the edited file")
    args = parser.parse_args()
    for path in (args.source, args.edited):
        if not path.is_file():
            parser.error(f"file not found: {path}")
    report = compare(args.source.read_text(encoding="utf-8"), args.edited.read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
