#!/usr/bin/env python3
"""Create a GitHub epic + child issues from a JSON spec, using the gh CLI.

Usage:
    create_issues.py spec.json [--dry-run] [--repo owner/name] [--output result.json]

The spec schema is documented in ../SKILL.md. The script is deliberately
fail-fast: on the first API error it prints what has already been created so a
rerun can resume from a trimmed spec instead of duplicating issues.
"""

import argparse
import json
import re
import subprocess
import sys


class GhError(RuntimeError):
    pass


def gh(*args, stdin=None):
    try:
        proc = subprocess.run(
            ("gh",) + args, input=stdin, capture_output=True, text=True
        )
    except FileNotFoundError:
        raise GhError(
            "the gh CLI is not installed; use the GitHub MCP fallback described in SKILL.md"
        ) from None
    if proc.returncode != 0:
        raise GhError(f"gh {' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def issue_number(url):
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        raise GhError(f"could not parse an issue number out of {url!r}")
    return int(match.group(1))


def ensure_labels(repo, spec, dry_run):
    """Create any label the spec uses that doesn't exist yet.

    A missing label makes `gh issue create` fail outright, so this keeps a
    typo or a new convention from blocking the whole run.
    """
    wanted = set(spec.get("epic", {}).get("labels") or [])
    for issue in spec.get("issues", []):
        wanted.update(issue.get("labels") or [])
    if not wanted:
        return
    try:
        existing = {
            label["name"]
            for label in json.loads(gh("label", "list", "--repo", repo, "--limit", "200", "--json", "name"))
        }
    except GhError:
        if not dry_run:
            raise
        # A dry run should still be useful without gh auth or network.
        print("[dry-run] could not list existing labels; assuming none exist")
        existing = set()
    definitions = spec.get("label_definitions") or {}
    for name in sorted(wanted - existing):
        definition = definitions.get(name, {})
        args = ["label", "create", name, "--repo", repo]
        if definition.get("color"):
            args += ["--color", definition["color"]]
        if definition.get("description"):
            args += ["--description", definition["description"]]
        if dry_run:
            print(f"[dry-run] would create label {name}")
        else:
            gh(*args)
            print(f"created label {name}")


def create_issue(repo, issue, dry_run, epic_number=None):
    body = issue.get("body", "")
    if epic_number is not None:
        body = body.replace("#EPIC", f"#{epic_number}")
    args = ["issue", "create", "--repo", repo, "--title", issue["title"], "--body-file", "-"]
    for label in issue.get("labels") or []:
        args += ["--label", label]
    for assignee in issue.get("assignees") or []:
        args += ["--assignee", assignee]
    if issue.get("milestone"):
        args += ["--milestone", issue["milestone"]]
    if dry_run:
        print(f"\n[dry-run] would create: {issue['title']}")
        print(f"  labels: {', '.join(issue.get('labels') or []) or '(none)'}")
        print("  body:")
        print("\n".join("    " + line for line in body.splitlines()))
        return None
    url = gh(*args, stdin=body)
    print(f"created {url}  {issue['title']}")
    return url


def link_sub_issues(repo, epic, children):
    """Attach children as native sub-issues; degrade to the task list if unsupported."""
    for number in children:
        try:
            child_id = gh("api", f"repos/{repo}/issues/{number}", "--jq", ".id")
            gh("api", "--method", "POST", f"repos/{repo}/issues/{epic}/sub_issues",
               "-F", f"sub_issue_id={child_id}")
            print(f"linked #{number} as a sub-issue of #{epic}")
        except GhError as err:
            print(f"note: could not link #{number} as a sub-issue ({err.args[0].splitlines()[-1]}); "
                  "the epic's task list still tracks it", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", help="path to the issue spec JSON")
    parser.add_argument("--dry-run", action="store_true", help="print what would be created, touch nothing")
    parser.add_argument("--repo", help="owner/name, overriding the spec")
    parser.add_argument("--output", help="write created issue URLs to this JSON file")
    args = parser.parse_args()

    with open(args.spec) as handle:
        spec = json.load(handle)

    repo = args.repo or spec.get("repo")
    if not repo:
        repo = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    epic_spec = spec.get("epic") or {}
    issues = spec.get("issues") or []
    if not issues:
        sys.exit("spec contains no issues")

    created = {"repo": repo, "epic": None, "issues": []}
    try:
        ensure_labels(repo, spec, args.dry_run)

        # The epic goes first so every child body can point at a real number.
        if epic_spec.get("existing"):
            epic_number = int(epic_spec["existing"])
            epic_url = f"https://github.com/{repo}/issues/{epic_number}"
            print(f"using existing epic {epic_url}")
        elif epic_spec:
            epic_url = create_issue(repo, epic_spec, args.dry_run)
            # A dry run has no real number, so child bodies keep the #EPIC placeholder.
            epic_number = issue_number(epic_url) if epic_url else None
        else:
            epic_url, epic_number = None, None
        created["epic"] = epic_url

        for issue in issues:
            url = create_issue(repo, issue, args.dry_run, epic_number)
            created["issues"].append({"title": issue["title"], "url": url})

        if args.dry_run:
            if epic_spec:
                print(f"\n[dry-run] would add a {len(issues)}-item task list to the epic "
                      "and link each child as a sub-issue")
        elif epic_number:
            numbers = [issue_number(i["url"]) for i in created["issues"] if i["url"]]
            if numbers:
                body = gh("issue", "view", str(epic_number), "--repo", repo, "--json", "body", "--jq", ".body")
                tasks = "\n".join(f"- [ ] #{n}" for n in numbers)
                gh("issue", "edit", str(epic_number), "--repo", repo, "--body-file", "-",
                   stdin=f"{body}\n\n## Tasks\n{tasks}\n")
                print(f"\nupdated #{epic_number} with a task list of {len(numbers)} issues")
                link_sub_issues(repo, epic_number, numbers)
    except GhError as err:
        print(f"\nfailed: {err}", file=sys.stderr)
        print("already created:", json.dumps(created, indent=2), file=sys.stderr)
        print("rerun with a spec trimmed to the remaining issues.", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w") as handle:
            json.dump(created, handle, indent=2)
    if not args.dry_run:
        print("\nepic:", created["epic"] or "(none)")
        for item in created["issues"]:
            print(f"  {item['url']}  {item['title']}")


if __name__ == "__main__":
    main()
