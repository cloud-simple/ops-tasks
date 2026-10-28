# Proposal: `lint` checks the Managed systems note

`tasks.py lint` must check that a plan with a filled Connections table has the `Managed systems:` note. Today it does not check the note.

Four plans in a user repo passed `lint` without the note. That is how the gap was missed.

## The check

- **Error** when `## Connections` has a table with at least one real row but no `Managed systems:` line under it.
- **Error** when the line still holds the template placeholder `<...>`.
- **No check** for plans without a Connections section, or with only the template's placeholder row, as in a new task.

`lint` cannot check whether the answer is true, only that someone answered. This limit is the same as for Allowed actions. The `lint` paragraph in `SKILL.md` must say so.

## Error, not warning

A missing note means nobody asked whether a manual change is safe. After the plugin update, older plans in other repos fail `lint` until someone adds the line. The fix is one line per plan.

## Where the change goes

In `cloud-simple/ops-tasks`:

- `tasks.py`: the check and a self-test.
- `SKILL.md`: one sentence in the `lint` paragraph.
- A version bump to 0.4.1, then a squash pull request and the release tag.
