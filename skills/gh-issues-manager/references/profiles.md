# Profiles per project type

A profile sets three things: the deliverable and its sections (which become section labels), what counts as an event, and what the templates should emphasize. The model itself does not change. A project may combine profiles; list them all in `profiles` in `.gh-issues-manager.json` and `setup_labels.py` creates the union.

Label definitions live in `profiles/*.json`. The `core` profile (role labels) is always applied.

## Software development (`software`)

Deliverable: a release, meaning its changelog, documentation and known issues.

| Section label | Feeds |
|---|---|
| `rel:added` | Release notes: new behavior |
| `rel:changed` | Release notes: changed or removed behavior |
| `rel:fixed` | Release notes: fixes |
| `rel:docs` | Documentation |
| `rel:known-issues` | Known issues and limits |

Topics are components or features (`topic:parser`, `topic:cli`). Use GitHub milestones for versions, since that is what they are for; the hub's deliverable tables are then per release.

Events: a merged pull request; a release or tag; a design decision; a benchmark or test campaign; an incident or regression; a change of dependency or public interface.

Emphasis: in final records, "Methods and settings" describes the design and its interfaces; "Results" holds test and benchmark outcomes with the commit they were measured at; "Not established" lists untested platforms, inputs and scales.

## Research and development (`research`)

Deliverable: a report or internal write-up of what was learned.

| Section label | Feeds |
|---|---|
| `rd:question` | Question and background |
| `rd:methods` | Methods and settings |
| `rd:results` | Results |
| `rd:limitations` | Limits and negative results |
| `rd:next` | Recommended next work |

Topics are questions or lines of work. Events: a finished experiment or analysis; a decision on direction or method; a failed or abandoned approach; a new version of data or of a resource; a merged change to analysis code.

Emphasis: the number-sources table and the "Configuration" field of result comments. Research projects rerun things; every rerun gets its own result comment and never overwrites an earlier one.

## Scientific prototyping (`prototyping`)

Deliverable: a go or no-go recommendation with the evidence behind it.

| Section label | Feeds |
|---|---|
| `proto:hypothesis` | What the prototype is meant to show |
| `proto:setup` | Setup and settings |
| `proto:results` | Measurements |
| `proto:limitations` | Limits and untested cases |
| `proto:go-no-go` | The recommendation |

Topics are the prototype's parts or the alternatives being compared. Events: a prototype run with its measurements; a go, no-go or pivot decision; a failed attempt and its cause; a change of test data or of the acceptance criterion.

Emphasis: write the acceptance criterion into the final record's "Methods and settings" before the first run, and record a change of criterion as a decision. Prototypes are small-sample by nature, so "Not established" carries much of the weight: what was tried once, on what, and what was not tried.

## Publication preparation (`manuscript`)

Deliverable: a paper, with main text, figures, tables and supplement.

| Section label | Feeds |
|---|---|
| `ms:background` | Introduction and background |
| `ms:methods` | Methods |
| `ms:results` | Results, figures and tables |
| `ms:limitations` | Limitations and discussion |
| `ms:supplement` | Supplement |

Topics are analyses, figures, tables or claims. Events: a result that enters a figure, table or sentence; a decision on a claim, an analysis or wording; a reviewer or co-author comment and its response; a frozen version of data or code; a submission, revision or resubmission.

Emphasis: each figure and table has a topic whose "Code and evidence" names the script, commit and input files that produce it, and each number in the text has a row in the hub's number-sources table. Reviewer comments are quoted word for word, like decisions.

## Mixed projects

A method paper with a software package uses `manuscript` and `software`; an exploratory project that may become a paper starts with `research` and adds `manuscript` when writing begins. An issue may carry section labels from more than one profile. The hub then has one group of deliverable tables per deliverable.

## Adding a profile

Copy a file in `profiles/`, change the name, deliverable, events and labels, and pass its path or name to `setup_labels.py --profile`. Label names are at most 50 characters and descriptions at most 100.
