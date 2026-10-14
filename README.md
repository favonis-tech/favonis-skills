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
