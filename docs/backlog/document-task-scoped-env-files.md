---
worth: yes
where: plugins/ops-tasks/skills/ops-tasks/SKILL.md:29
added: 2026-10-16
---
# SKILL.md does not say how to scope a credential to one task

The skill supports an env file per connection, `<ops-dir>/.env.<name>`: `Layout.env` in `scripts/tasks.py` is `<ops-dir>/.env*`, `init` adds the gitignore rule `/<ops-dir>/.env*`, and `lint` checks every matching file is ignored. Verified in a throwaway repo with `ops/.env.07-migrate-dns`. SKILL.md does not say that a connection only one task uses can get such a file, or that the file must go when the task ends. A per-task folder file (`tasks/NN-slug/.env`) was considered and rejected: the ignore rule and lint do not cover it, and copying shared credentials into every task multiplies secret files.

Text change only, no code or template change. Wording agreed after a Codex review (2026-10-16), which found four problems in the first draft: the load path must keep the `OPS_ENV_FILE` override or the offline tests read real credentials; the rule must apply only when the connection uses an env file, since a password manager or hidden prompt is allowed; two task-only connections need distinct names; cleanup must cover `dropped` tasks, not only `done`. A second review (same day) confirmed all four resolved and added one: the per-connection suffix must be filename-safe, because lint does not restrict Connections IDs.

Append to the env file rule (line 29):

> If a connection uses an env file and only one task uses that connection, keep its settings in `<ops-dir>/.env.<NN-slug>`. When a task has several such connections, each gets `<ops-dir>/.env.<NN-slug>.<name>`, where `<name>` is distinct within the task and holds only lowercase letters, digits and hyphens. The helper loads that file through `${OPS_ENV_FILE:-$HERE/../../../<file name>}`, for example `${OPS_ENV_FILE:-$HERE/../../../.env.07-migrate-dns.dns-api}`.

Append to Workflow step 4, Close (line 174):

> When closing a task as `done` or `dropped`, delete the env files that only this task used.

The Connection rule (line 137) stays as it is. Ships with the next version bump.
