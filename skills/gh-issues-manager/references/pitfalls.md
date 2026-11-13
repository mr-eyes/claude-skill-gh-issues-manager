# Pitfalls: GitHub, Mermaid and record-keeping

Each of these happened in a real project. The table says what the skill does about it.

## References and links

| Pitfall | Rule | Enforced by |
|---|---|---|
| Text copied between repositories keeps a bare `#N`, which GitHub links to the wrong item | Outside the current repository write `owner/repo#N` or a full URL | Linter: bare `#N` must exist in the target repository |
| A bare `#N` that exists in both repositories links to the wrong one and passes any check | Review every reference by eye during a migration | Human or reviewer |
| Issues that link to each other cannot know each other's numbers before they exist | Draft with `NEW-<key>`, create, substitute, edit | `create_issues.py` |
| `#N` inside a Mermaid block breaks rendering | Inside Mermaid write `Issue N` | Linter; `create_issues.py` substitutes `Issue N` there |

## Mermaid on GitHub

| Rule | Reason |
|---|---|
| Double-quote every node label: `A["Methods"]` | Unquoted labels break on punctuation and reserved words such as `end` |
| No `#` anywhere in the block | Read as an entity or comment marker |
| No parentheses anywhere in the block | Read as node-shape syntax, even inside some labels |
| Node identifiers from letters, digits and underscores | Hyphens collide with arrow syntax |
| Define every node with a label, and use every node in an edge | An undefined node renders as its bare identifier; an unused one is a leftover |
| Quote edge labels too: `A -->|"feeds"| B` | Same reasons as node labels |

A broken diagram shows as a red error box in place of the map, and the preview in a local editor is not the same renderer. After posting a hub, look at it once in the browser.

## GitHub limits and behavior

| Fact | Consequence |
|---|---|
| An issue or comment body holds at most 65,536 characters | A final record that needs more is split into two topics, a long comment into two comments; the linter warns within 5,000 characters of the limit |
| The API and `gh` report times in UTC | Convert to the tracker's convention before writing; a merge at 01:30 UTC is the previous day in the Americas |
| Stored bodies may come back with different line endings | Read-back comparison ignores line-ending style and trailing whitespace only |
| Up to three issues can be pinned per repository | One hub per repository |
| Label names hold at most 50 characters, descriptions 100 | `setup_labels.py` checks before writing |
| Editing an issue body does not notify watchers the way a comment does | The comment that caused a change is what people see; always post it |
| Many writes in a short time can hit secondary rate limits | `create_issues.py` can be rerun; it resumes from its state file |

## Numbers

| Pitfall | Rule |
|---|---|
| Numbers from different runs or configurations combined in one statement | One run per table in result comments; in a body, every number's source under "Sources", and a consistency pass over all bodies before assembly |
| A superseded number presented as current | The body is edited in place when the number changes; the comment that caused the change says why |
| A number without its denominator | Value and denominator, every time |
| A number typed from memory or from a summary | Read it from the source file while drafting, and name the path |
| "Missing" read as zero, "not tested" read as negative | Every result and failure comment has a "Not established" field that may not be empty; in a body, an untested case is a stated limitation |

## Deliverable bodies

| Pitfall | Rule | Enforced by |
|---|---|---|
| History mixed into a deliverable body: "As of" lines, dated status, decision tables, open work, provenance, job identifiers. Whoever assembles the deliverable copies it, or has to cut it out by hand | The body is the current text only; history goes into comments, work in development into `active` issues | Linter: no "As of" line, no heading for decisions, open work, provenance or next steps, no dated heading |
| Folded "Replaced on" blocks keep old text in the body, where it is read as current or copied by mistake | Edit in place; GitHub's edit history and the dated comment are the trail | Linter: no `<details>` block in a final record |
| Numbers repeated on the hub drift from the bodies after the next edit | The hub lists issues per section and holds no numbers from bodies; each number lives in one body | Review of the hub |
| A long record shortened into deliverable text loses its limitations, because they read like history | Every limitation of the final method or result stays, as a property of the result; the reviewer audits exclusions hardest | Independent review per batch |
| The same quantity, or the same term, differs between bodies written at different times | One consistency pass over all bodies together before assembly and after a batch of conversions | Review |
| A section label stays after its text left the body, and the assembler finds an empty or missing section | Labels follow the `## ` headings | Linter: headings against labels; `post_verified.py body` and `convert_body.py` set the labels from the headings |
| A heading mistyped as `### Results`, `##Results`, indented, underlined or caught in an unclosed code block reads as a section that left, and its label is removed | A line that looks like a section heading but is not one is an error; a run that would remove a section label prints `removes:` and needs `--allow-label-removal` | Linter: `near-heading`; both scripts |
| A deliverable body written into a task, the hub or an issue of another profile | Only an issue labeled `final-record`, and not `hub` or `active`, gets a deliverable body; section labels of profiles not in use stop the run | `post_verified.py body`, `convert_body.py` |
| A body converted while someone else was editing it loses their edit | Draft from a saved copy of the live body; stop if the live body differs | `convert_body.py --expected` |

## Decisions and people

| Pitfall | Rule |
|---|---|
| A paraphrased decision drifts from what was said, and later work follows the paraphrase | Quote the exact words with date, time and zone; the linter requires a quote block in decision comments |
| A decision recorded without where it was made | "Where recorded" says how to find the original |
| Pronouns guessed from a name | Use the name or role, or "they" |

## Posting

| Pitfall | Rule |
|---|---|
| A scratch file in the drafts folder gets posted by a command that globs the folder | Post only from explicit file names or a manifest; keep scratch elsewhere |
| A body built inside a shell command loses backticks or dollar signs | Always `--body-file` |
| A post assumed to have succeeded | Read back from the API and compare |
| A partial run repeated from the start creates duplicate issues | The state file records what exists; rerun the same command |
| A secret or restricted identifier pasted from a log | Linter patterns for common tokens and the project's `restricted_patterns`; read logs before quoting them |

## Time

Pick one convention at bootstrap, write it in the hub and in `.gh-issues-manager.json`, and use it everywhere: date, 24-hour time, zone abbreviation. When quoting a time from another system, convert it and, if useful, keep the original in parentheses: `2026-03-04 17:30 PST (2026-03-05 01:30 UTC)`.
