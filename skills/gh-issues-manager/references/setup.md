# Setting up a record: the wizard

> Commands on this page write `scripts/<name>` for short. That is the `scripts` folder of this skill, next to `SKILL.md`; call it by its full path.

A project's goal usually does not exist as files yet (a manuscript is written during the work), so setup is a short set of questions asked with the user, not a file scan. Detection only pre-selects answers.

## When it runs

- In the first session after install in a project without `.gh-issues-manager.json`, after the one-line notice from the SessionStart hook, when the user agrees.
- Whenever the user asks to set up the record, and again when they ask to change the setup.

## How it runs

1. `python3 scripts/setup.py detect` (read-only, local). It looks only at file and folder names at the top of the project and one level down, and prints suggestions with their evidence, for example "suggested: software (profile software), because pyproject.toml, tests/". An empty project gets no suggestion. In a large folder it stops after the first few hundred names.
2. Ask the questions below with the session's multiple-choice question tool, a few at a time, each with an "other" answer. Pre-select what detection suggested and show its evidence next to it.
3. Show a summary of all answers and ask for one final confirmation. Nothing is written before it.
4. Write the answers to a file, then run `python3 scripts/setup.py apply --answers <file> --dry-run`, show its output, and run it again with `--yes`.

## Questions

| Question | Answer becomes |
|---|---|
| What will this project produce? (several allowed) Paper or manuscript; thesis or report chapters; software or library release; dataset or resource; analysis report; prototype or demo; grant or proposal; documentation or website; other | `deliverables`: `paper`, `thesis`, `software`, `dataset`, `report`, `prototype`, `proposal`, `docs`, `other`. Each maps to a profile (`manuscript`, `thesis`, `software`, `dataset`, `research`, `prototyping`, `proposal`, `docs`, `custom`) |
| For each deliverable: its sections, starting from the profile's default, editable (add, rename, reorder; for example a journal's required sections or thesis chapters) | `sections`: the `## ` headings of the topic bodies, and the section labels |
| Where does the record live: this repository's issues, another existing repository, a new private repository? | `record`: `this`, `other`, `new`, and `repo` |
| Who decides: the names or handles whose words count as decisions | `decision_makers` |
| Time zone for event times | `timezone` |
| Is there earlier work to catch up on? May this project's local Claude Code transcripts be read for it? | `catch_up`, `read_transcripts` (see [catch-up.md](catch-up.md)) |
| Optional: the GitHub triage labeler workflow; the CLAUDE.md snippet; the prompt reminder line and how often | `triage_workflow`, `claude_md`, `prompt_hook` |
| May this repository be added to your trusted list, so the hooks print its brief? | `trust` |

An answers file:

```json
{"repo": "owner/name", "record": "this",
 "project": "A small library that reads CSV files, and a short benchmark note.",
 "deliverables": [{"kind": "software"},
                  {"kind": "paper", "sections": ["Background", "Methods", "Results", "Data availability"]}],
 "decision_makers": ["Sam Rivera"], "timezone": "US Pacific time, written as 2026-03-04 14:10 PST",
 "topics": ["reader"], "catch_up": false, "read_transcripts": false,
 "triage_workflow": true, "claude_md": true, "prompt_hook": {"enabled": true, "every": 10}, "trust": true}
```

`setup.py` checks every value against a strict form (names, headings, numbers in range) and refuses the file otherwise. Each kind is listed once; a second deliverable of a kind is kind `other` with its own name. Section headings must be distinct (ignoring case), give distinct labels, and may not be "Sources", which is the sources table of every body. A deliverable of kind `other` keeps its name in the setup, and its labels start with that name (`sec:lab-handbook-safety`), so two such deliverables never share a label. When `apply` runs again on an existing setup, the values it keeps (time zone, topics, decision makers, profiles, hub) must fit the same forms; otherwise it stops and names them.

## What `apply` does

- Checks first that none of the files it may write (the setup file, the hub drafts, the workflow, `CLAUDE.md`) or the folders on the way to them is a symlink, and stops before any change if one is. Each file is written through a fresh temporary file in its folder, then moved into place.
- Writes `.gh-issues-manager.json`: the repository, the profiles (a profile with edited sections is stored with its section labels and headings), topics, decision makers, time zone and options.
- Creates the labels: role labels, the core `type:` labels, the chosen profiles' section and type labels, and topic labels.
- Creates the hub with its deliverable tables in the chosen order and posts its first resume comment, for a project that has no hub yet.
- Adds the repository to the user's trusted list when `trust` is true; with `false`, the list is not touched.
- Writes `.github/workflows/ghim-triage.yml` when asked for and the record is this repository's issues. A workflow acts only on the repository it is committed to, so for a record in another repository (`record`: `other` or `new`) `apply` writes nothing and says to commit `templates/ghim-triage.yml` in the record repository.
- Writes the CLAUDE.md snippet when asked for.
- Runs the first `index.py sync` in the foreground, so the first session already has a brief.
- Records the kinds of deliverable that the project's files already suggest, so the hooks mention only what appears later.

## Later changes

The deliverable can change mid-project. Run `apply` again with the new answers: it adds profiles, sections and labels and never removes what is there; for an existing hub it prints the table rows to add, for the session to post with `post_verified.py body`. The SessionStart brief and the `record-auditor` agent notice when files suggest a deliverable the setup does not cover (for example the first `.tex` file in a project set up only for software) and ask once whether to add it. Files present when `apply` ran, and the plugin's own workflow file, never cause that line.
