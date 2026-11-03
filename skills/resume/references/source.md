# Resume source format

The source is one YAML file per version, such as `简历/林晓-后端开发.yaml`. The script reads every value as text, so dates like `2024.10`, phone numbers and GPAs need no quotes. Unknown fields are rejected with the allowed list.

## Top level

| Field | Meaning |
| --- | --- |
| `name` | Required. |
| `headline` | One line under the name: the target role, such as `求职意向：后端开发工程师（2026 届校招）` or `Data Analyst`. |
| `contacts` | List shown on one line: phone, email, city, links. Email addresses and web addresses become links. |
| `photo` | Image path relative to the source; shown at the top right at 25 × 33 mm. Only when the user supplies one and the target expects it. |
| `template` | `serif` (default), `classic` or `modern`; see below. |
| `accent` | Optional color such as `"#1f4e79"`, replacing the template's accent (quote it: YAML reads `#` as a comment). |
| `lang` | `zh` (default) or `en`: fonts and label punctuation. |
| `pages` | `1` (default) or `2`. |
| `sections` | Required list, in page order. |

Each section has a `title` and exactly one body:

| Body | Use for | Shape |
| --- | --- | --- |
| `entries` | education, work, internships, projects, research | list of entries |
| `items` | skills and other label rows | list of `label` + `text`, or plain strings |
| `bullets` | honours, certificates, short lists | list of strings |
| `text` | summary or 自我评价 | one paragraph |

An entry has `title` (required: school, company or project), `subtitle` (degree and major, role, or role and stack), `location`, `date` (right-aligned, for example `2024.07 – 2025.06` or `2024.07 – 至今`), `note` (one muted line under the heading, such as GPA, courses or team) and `bullets`.

## Inline text

- `**加粗**` for the words a reader should catch while skimming.
- `[文字](github.com/name)` for a link; prefer the visible address as the text, since printed links cannot be clicked.
- `【待补充：GPA 与排名】` marks a gap: it prints with a yellow highlight and the report lists it. A final version has none.
- A long value may wrap over several YAML lines; Chinese lines are joined without a space.

## Templates

All three are single-column, so applicant tracking systems read them in order. Use `serif` unless the user asks for another look.

| Template | Look |
| --- | --- |
| `serif` | Serif name, section and entry titles, centered header, near-black full-width rules; the default |
| `classic` | Sans-serif throughout, left-aligned header, navy section titles over a light rule |
| `modern` | Name and entry titles in the accent color, section titles on a tinted band with a side bar |

When the user wants to choose, build the same source with `--template` into separate files (for example `简历/样式-classic.pdf`), view and present them, then write the chosen one into the source and delete the other previews.

## Example

```yaml
name: 林晓
headline: 求职意向：后端开发工程师（2026 届校招）
contacts: [186-0000-1234, linxiao@example.com, 杭州, github.com/linxiao-dev]
sections:
  - title: 教育背景
    entries:
      - title: 浙江工业大学
        subtitle: 计算机科学与技术 · 本科
        date: 2022.09 – 2026.06
        note: GPA 3.72/4.0（专业前 10%）· 主修：操作系统、计算机网络、数据库系统
  - title: 实习经历
    entries:
      - title: 某电商平台
        subtitle: 后端开发实习生 · 交易中台
        date: 2025.07 – 2025.12
        bullets:
          - "**订单查询提速**：定位订单详情接口慢查询的根因是深分页，改为游标分页并补齐覆盖索引，P99 延迟由 820 ms 降到 160 ms，已全量上线"
          - "**对账任务改造**：把每日对账脚本拆成按商户分片的定时任务，接入失败重试和告警，夜间任务时长从 3 小时缩短到 50 分钟"
  - title: 项目经历
    entries:
      - title: 轻量消息队列 MiniMQ
        subtitle: 个人项目 · Go · github.com/linxiao-dev/minimq
        date: 2024.10 – 2025.03
        bullets:
          - 用 Go 实现基于追加写日志的消息存储，支持按偏移量消费和消费组，单机写入 5 万条/秒（8 核笔记本，1 KB 消息）
  - title: 专业技能
    items:
      - label: 语言
        text: Go（主力）、Java、Python、SQL
      - label: 后端
        text: MySQL 索引与事务、Redis、Kafka、gRPC
  - title: 荣誉奖项
    bullets:
      - 2024 年中国大学生程序设计竞赛（CCPC）省赛银奖
```

A bullet that starts with `**` must be quoted, since YAML reads a leading `*` as an alias.
