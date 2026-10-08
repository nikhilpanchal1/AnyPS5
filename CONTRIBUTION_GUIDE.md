# AnyPS5 contribution guide

Updated: 2026-10-08. Start with this guide, then [TESTING.md](TESTING.md).

## Keep the knowledge in the fork

Use a dedicated `contribution-notes` branch in the fork for these two documents.
It has independent history and contains only the notes. Read it with `git show`;
keep the source checkout on main or an issue branch.
Keep fork `main` aligned with upstream `main`. Start each issue branch from that
updated main. Keep knowledge changes on the notes branch; never merge that branch
into main or a fix branch, never cherry-pick its commits into a fix, and never
include these documents in an upstream PR. Check that the PR diff excludes both
files before publication; TESTING.md includes a guard for this.

Inspect remotes first: `origin` should identify the fork. If an upstream remote is
absent, establish which repository and main ref to use. Establish the notes branch
once before using these read commands. Preserve local work before switching
branches. In a prepared cloud environment, read its startup instructions and use
its existing checkout.

Before investigating, fetch both remotes and read the latest notes without
switching the working checkout:

```bash
git fetch origin
git fetch upstream
git show origin/contribution-notes:CONTRIBUTION_GUIDE.md
git show origin/contribution-notes:TESTING.md
```

With a clean checkout, fast-forward fork main and start a new issue branch:

```bash
git switch main
git merge --ff-only upstream/main
git push origin main
git switch -c fix/issue-name
```

If fast-forwarding fails, inspect the divergence before proceeding. Do not merge
fork-only notes into main or discard unrelated work to make the command pass.

## Working on an issue

1. Read applicable `AGENTS.md`, `CONTRIBUTING.md`, `docs/dev/CONVENTIONS.md`,
   `.github/pull_request_template.md` and relevant workflows. Current repository
   rules and the user's task instructions govern the work.
2. Check open issues and PRs for duplicate work or dependencies. Reproduce the
   problem and write down the expected behavior and the test that will prove it.
3. Make a focused, general fix on its own branch. Follow naming conventions;
   unimplemented behavior throws. Follow the repository's strict comment rules.
   Changes to shader semantics need the required hardware or exact-source evidence.
4. Use the testing pathways as starting points. Actively explore important risks
   they do not cover. Review correctness, failure handling, unrelated behavior and
   test coverage. Retest changes made during review.
5. Before publication, verify the exact diff, commit identity, Conventional Commit
   title, contribution checks and PR checklist. Include OS, device, test results,
   skips and coverage limits. Complete the required assistance disclosure.
   Publish only within the user's authorization.

## Improve the reference after each investigation

Update the smallest relevant section of TESTING.md with a reusable finding:
what it tests, a working command, prerequisites, an evidence link or run record,
and its limits. Date the finding. Separate locally verified results from external
reports and hypotheses. Replace obsolete advice when evidence changes.

Save those edits on `contribution-notes`; use a dedicated checkout where the
environment permits one, or edit that branch through GitHub. Keep a fix checkout
undisturbed. Resolve concurrent notes edits.
Keep raw logs, secrets and branch-specific task histories out of these documents.
The issue or PR holds the full investigation history.
