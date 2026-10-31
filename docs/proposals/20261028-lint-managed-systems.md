# Proposal: `lint` checks the Managed systems note

`tasks.py lint` must check that a plan with a filled Connections table has the `Managed systems:` note. Today it does not check the note.

Four plans in a user repo passed `lint` without the note. That is how the gap was missed.

## The check

- **Error** when `## Connections` has a table with at least one real row but no `Managed systems:` line after it. A real row has a non-empty ID that does not start with `<`. Every Kind counts: a repo or a pipeline can change managed infrastructure too.
- **Error** when the line is empty or still holds the template placeholder: the value starts with `<`.
- **Error** when the line is not exactly one line, at the start of a line, after the table, in the Connections section. A note above the table, a second note, a note under another heading or inside a code fence does not count.
- **Error** for a Connections row with an empty ID, including a fully blank row. Today such a row is accepted silently.
- **Error** for a second `## Connections` section. A plan has one, so a note in one section cannot answer for a table in another.
- **No check** for plans without a Connections section, with only the template's placeholder row, as in a new task, or whose table is missing or has the wrong columns. A table with a real row still needs the note when other rows have errors (a wrong Kind, a duplicate ID or a wrong number of cells).

The answer is a mapping (which repo declares which part, which pipeline applies it), `none` when the author established that no managed system is involved, or `unknown` when that is not established yet. Plans of done and dropped tasks are not exempt; an old plan gets `unknown` with the date the line was added.

`lint` cannot check whether the answer is true, only that someone answered. This limit is the same as for Allowed actions. A note inside an HTML comment still counts, as for every other `lint` check.

## Error, not warning

A missing note means the plan does not record whether a repo declares the systems it changes. After the plugin update, older plans in other repos fail `lint` until someone adds the line. The fix is one line per plan.

## Where the change goes

In `cloud-simple/ops-tasks`:

- `tasks.py`: the check and its self-tests.
- `SKILL.md`: the Managed systems bullet (the answers) and the `lint` paragraph (the check and its limit).
- `assets/PLAN.md`: the template line names `none` and `unknown`.
- A version bump to 0.5.0, because `lint` now rejects plans it accepted. The release notes state the new error and the one-line fix.
