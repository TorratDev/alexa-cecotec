---
name: plan-to-issues
description: Turn an implementation plan, design doc, roadmap, or TODO breakdown into real GitHub issues — a parent epic plus one child issue per task, with acceptance criteria, affected files, and labels. Use this whenever the user has a plan (in a file, in plan mode output, or just agreed in the conversation) and wants it tracked on GitHub: "file issues for this", "create tickets from the plan", "break this down into issues", "put this on the board", "open an epic for X". Also use it when the user asks to split one oversized issue into sub-issues. Prefer this skill over ad-hoc `gh issue create` calls, even when the user only says "make an issue" after a planning discussion — the decomposition and the confirmation step are the point.
---

# Plan → GitHub issues

Turn a plan into issues someone else could pick up cold. The value is not in
calling the GitHub API — it's in the decomposition (right-sized, independently
mergeable units) and in never creating issues the user hasn't seen first.

Creating issues is outward-facing and noisy to undo. Always show the proposed
set and get an explicit go-ahead before anything is created.

## Workflow

### 1. Get the plan

Sources, in order of preference: a file the user names, plan-mode output or a
plan agreed in this conversation, an existing issue to split, or a doc URL.
If the plan is one vague paragraph, don't invent a twelve-issue backlog from
it — ask what the actual scope is first.

### 2. Establish repo context

```bash
git remote -v                  # derive owner/repo from origin
gh auth status                 # is gh present and authenticated?
gh label list --limit 100      # what labels already exist
gh issue list --state open --limit 30   # avoid filing duplicates
```

If an open issue already covers a task, link it instead of duplicating it.

### 3. Decompose

Aim for issues that are each **one reviewable PR**. A useful test: could a
contributor who has never seen the plan open this issue, understand what
"done" means, and know where in the codebase to start? If not, the issue is
underspecified. If it would take a week and touch three subsystems, split it.

Good boundaries follow the code and the dependency order — a data layer before
the handler that uses it, a schema before a migration consumer. Group work
that must land together into one issue rather than filing artificial halves
that can't be merged separately.

Bad boundaries: "phase 1 / phase 2 / phase 3", one issue per file touched, or
one issue per sentence in the plan.

Sequence matters: order the children so the list reads as an execution order,
and note blockers explicitly (`Blocked by #N`) rather than leaving readers to
infer them.

### 4. Draft the spec

Write a JSON spec to the scratchpad (never into the repo). Schema:

```json
{
  "repo": "owner/name",
  "epic": {
    "title": "Support Cecotec Conga via Alexa smart-home skill",
    "body": "markdown body — problem, scope, non-goals, links",
    "labels": ["epic"]
  },
  "issues": [
    {
      "title": "Add OAuth token refresh for the Cecotec cloud client",
      "body": "markdown body — see template below",
      "labels": ["enhancement"],
      "assignees": []
    }
  ],
  "label_definitions": {
    "epic": { "color": "5319E7", "description": "Tracking issue for a multi-issue effort" }
  }
}
```

`label_definitions` is optional and only needed for labels that don't exist
yet — the script creates those, so a typo'd label never silently drops work on
the floor.

Use this body template for each child issue. It exists so the issue survives
without the conversation that produced it:

```markdown
## Context
Why this is needed, one or two sentences. Link the epic: part of #EPIC.

## Scope
What to change, concretely.

## Acceptance criteria
- [ ] Observable, checkable outcome
- [ ] Another one

## Affected files
- `path/to/file.py` — what changes here

## Notes
Gotchas, dependencies (`Blocked by #N`), links to docs or prior art.
```

Keep bodies factual. Don't pad with restated plan prose, and don't invent file
paths — if you haven't confirmed a path exists, say "likely in `src/…`" or
leave it out.

### 5. Confirm with the user

Show a compact preview — titles, labels, and the one-line intent of each —
plus the total count, and ask for the go-ahead. This is where the user catches
a bad split cheaply. Offer `--dry-run` if they want to see the exact bodies.

### 6. Create

```bash
python3 .claude/skills/plan-to-issues/scripts/create_issues.py <spec.json> --dry-run
python3 .claude/skills/plan-to-issues/scripts/create_issues.py <spec.json>
```

The script creates the epic first, then each child (each body gets the epic
number substituted for `#EPIC`), appends a task list to the epic, and links
children as native sub-issues where the repo supports them. It stops on the
first failure and reports what was already created, so a rerun never needs to
guess — trim the spec to the remaining issues.

**When `gh` is unavailable** (Claude Code on the web, a container without the
CLI), fall back to the GitHub MCP tools with the same spec and the same order:
`issue_write` to create the epic, `issue_write` per child, `issue_write` again
to update the epic body with the task list, `sub_issue_write` to link each
child. Create labels first if they're missing. The confirmation step in §5 is
not optional in this path either.

### 7. Report

Give the epic URL and a numbered list of child URLs with titles, as markdown
links. Then stop — don't start implementing an issue unless asked.

## Splitting an existing issue

Same flow, with the existing issue as the epic: read it with
`gh issue view N --json title,body,labels`, draft children from its content,
confirm, then run the script with `"epic": {"existing": N}` in the spec. The
script skips creation and only appends the task list and links sub-issues.
