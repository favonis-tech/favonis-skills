# Upstream

- Original repository: https://github.com/op7418/Humanizer-zh
- Original commit: `f4518a8eab97b8bfebc66a89d34320a89bef6930` (revision 2026-09-23)
- License: MIT; see LICENSE.

Adapted for Favonis:

- The frontmatter uses the Favonis fields (English `description` for the model, interface text in `localizations`); upstream `allowed-tools` and `metadata` are dropped.
- 「输出与文件保护」 is replaced by 「在 Favonis 中处理文本和文件」, which maps the same rules onto Favonis tools: targeted `project_edit` edits with a backup and `project_diff` review for Markdown, batched `docx` `replace_text` edits for Word files, and a new file for PDF or image text.
- One line about the fixed phrases of 公文 and legal documents is added to 「文体与作者声音」.
- `scripts/check_markdown.py` is adapted from upstream `tests/check_structure.py`: it reports which protected parts changed, ignores code inside fenced blocks when collecting inline code, links and headings, and no longer freezes the text of numbered list items.
- The pattern catalogue (A–F), constraints, workflow, checklist and example are unchanged.

Upstream sources credited by Humanizer-zh:

- [blader/humanizer v3.0.0](https://github.com/blader/humanizer/blob/v3.0.0/SKILL.md): categories A–E, voice calibration and file mode.
- [Humanizer-zh PR 39](https://github.com/op7418/Humanizer-zh/pull/39): the Chinese categories and group F.
- [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop): concise wording and editing checks.
- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing): the original observations; not a basis for judging authorship or detector accuracy.
