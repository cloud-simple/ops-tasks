# Plan: {{TITLE}}

Task: [TODO.md](TODO.md). Facts checked on {{DATE}}.

## Goal

<The end state in one or two sentences, and how to tell it is reached.>

## Facts

<Current facts the steps rely on: value, checked at (date, time, zone), how it was measured, and when to check it again. Older values move to the Log.>

## Connections

| ID | Kind | Target | Settings and credentials from | Allowed actions |
|---|---|---|---|---|
| <id> | <system, repo or pipeline> | <exact identity: host, API URL or cluster context; hosting project; pipeline project, job and environment> | <env file and variable names, "hidden prompt, from the password manager", or "typed in step N.M"> | <what the user authorized, with scope: read; push branch ops/NN-slug; open MR; run job deploy for revision X> |

Managed systems: <for each system whose state a repo declares: which repo declares which part, and which pipeline applies it; or "unknown">.

## Stop conditions

- <A state in which the work must not start, or must stop.>

## Steps

<Number every step N.M: N is the phase, M the step within it. A short plan can have one phase with one or more steps; a long plan can group them under `## Phase N: <title>` headings instead. Never renumber a step that already ran.>

### 1.1 <Read-only check or preparation>

<Why this step exists, in one sentence.>

- [ ] <Action that only reads or prepares, for example "Record the current state".>

  ```bash
  <command>          # what it shows
  ```

  Expected: <observable result>. When ticked, add under the item: `Result (YYYY-MM-DD): <measured values>`.

### 1.2 <Step that changes infrastructure>

Uses: <Connections IDs; optional, for a step whose target is easy to confuse>

<Why this step exists, in one sentence.>

**Before** (read-only):

```bash
<command>          # what it shows
```

Expected: <observable result>.

**Do:**

- [ ] <First action.>

  ```bash
  <command>        # what it changes
  ```

- [ ] <Second action, only after the first one succeeded.>

  ```bash
  <command>        # what it changes
  ```

**After** (read-only):

```bash
<command>          # what it shows
```

Expected: <observable result>.

- [ ] After check passed.

  Result (YYYY-MM-DD): <measured values>.

### 2.1 <Decision or phone call>

- [ ] <Who decides or confirms what.>

  Acceptance: <the answer or confirmation to record>.

<A GUI action that changes something is a changing step: Before, Do with the click path (**Menu → Item → Button**), After.>

### 2.2 <Step that cannot be undone>

<Why this step exists, and the gate it waits for, for example "only after the owner agrees in 2.1".>

**Before** (read-only): <command and expected result>.

**Do:**

- [ ] <Action.> **Cannot be undone.**

  ```bash
  <command>        # what it changes
  ```

**After** (read-only): <command and expected result>.

- [ ] After check passed.

### 2.3 <...>

...

### 2.4 <...>

...

### 3.1 <...>

...

## Rollback

- 1.2: <how to undo it>.
- 2.2: cannot be undone.
- 2.3: ...
- 3.1: ...

## Not used

- <Alternative that was not needed: date and reason.>

## Log

- <YYYY-MM-DD: a deviation, failed attempt or event that spans steps. Name the step ID.>
