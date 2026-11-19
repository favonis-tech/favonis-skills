# Favonis Skills

Favonis 官方技能库。

技能位于 `skills/`，第三方技能的来源和许可证见各自目录。

## 界面文案

`SKILL.md` 的 `description` 是给模型判断何时使用技能的说明，保持英文。技能库、「/」菜单和消息里给用户看的名称、简介和常用叫法写在 frontmatter 的 `localizations` 里，按界面语言（`zh-CN`、`zh-TW`、`zh-HK`、`en-US`）各写一份，官方技能四种都要写：

```yaml
localizations:
  zh-CN:
    display-name: Manim 数学动画
    description: 给用户看的简介。
    keywords: [动画, 数学视频]
```

每种语言的 `display-name` 和 `description` 必填，`keywords` 可省。模型读取技能时只拿到正文，看不到这些文案。`answer-me-with-html` 由 `scripts/sync-skills.py` 从维护 fork 整包同步，它的文案改在 fork 里。

## 命令写法

技能在云端电脑上跑，也在文件夹项目里用户自己的电脑上跑，命令要两边原样能用，不写只在云端电脑上成立的路径：

- 技能包的位置写 `$SKILLS_DIR/<name>/`，不写 `/skills/<name>/`。
- Python 脚本用 `$FAVONIS_PYTHON` 运行（云端是 `python`，用户电脑上是 Favonis 自带的 Python），不写裸的 `python`。
- 中间文件放 `$TMPDIR`，不写 `/tmp`；项目里的文件写相对路径，不写 `/project`。
- 脚本按自己所在的位置找包里的其他文件。

技能要用外部程序（FFmpeg、LaTeX 这类）时，在 frontmatter 里声明程序名：

```yaml
programs: [ffmpeg, xelatex]
```

用户电脑上没有其中某个程序时，Favonis 会告诉模型把那一步放到云端电脑上做。

## 测试

在装有技能依赖的环境（Favonis 沙箱或同等的 Python 环境）里运行：

```sh
python -m unittest discover -s scripts
```

需要渲染的用例按依赖自动跳过：Manim 渲染要有 Manim 和 FFmpeg；公文的版面实测要有沙箱的 `render-office`，本机可以在 `PATH` 里放一个同名脚本，用能显示中文字体的 LibreOffice 渲染。动画短片的浏览器用例要有 Playwright、fontTools、Pillow、FFmpeg 和 Chromium（`PATH` 里的 `chromium`，或用 `PROMO_CHROMIUM` 指定可执行文件）；中文字体通过 `fc-match` 查找，本机没有 fontconfig 时可以放一个同名脚本返回 Noto CJK 字体路径。简历的排版用例要有 Playwright、PyMuPDF 和 Chromium（`PATH` 里的 `chromium`，或用 `RESUME_CHROMIUM` 指定），Word 版的页数核对还要有 python-docx 和 LibreOffice；用例只核对适配结果，不依赖具体字体。
