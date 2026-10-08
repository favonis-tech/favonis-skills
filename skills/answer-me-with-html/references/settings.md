# Settings, scratch cleanup and updates in Favonis

Use the `shell` tool in `/project`. For each CLI command, use:

```bash
AM_HOME=/tmp/answer-me-with-html AM_NO_OPEN=1 AM_NO_UPDATE_CHECK=1 node /skills/answer-me-with-html/scripts/am.mjs
```

- Prefer per-document `theme:`, `mode:` and `style:` settings in the draft. Preserve the original themes and the user's requested visual style.
- `config` lists settings; `config set <key> <value>` changes the scratch configuration for this sandbox. It is temporary and may disappear when the sandbox is replaced. Do not promise account-wide persistence.
- Keep automatic browser opening and upstream update checks disabled. Favonis owns preview and package updates.
- `clean --dry-run` reports scratch cleanup. Only run `clean` after the user requests that cleanup. It does not clean saved project deliverables; use the project file workflow for those.
- Package updates are performed by an administrator using **Sync official repository** in Favonis. Do not run package installers, `git pull`, plugin update commands or write into `/skills` from a conversation.
