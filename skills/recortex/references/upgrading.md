# Upgrading from gh-issues-manager

The plugin was named gh-issues-manager (short `ghim`) before version 0.5.0. A project, a machine and a record set up under that name keep working with recortex as they are: nothing has to be edited, rebuilt or moved, and the brief shows as before. This page says what changed, what still reads the earlier names, and the optional steps to move to the new ones.

## The one step Claude Code needs

For an install from the `mr-eyes-skills` marketplace, run both commands, one after the other:

```bash
claude plugin marketplace update mr-eyes-skills
claude plugin install recortex@mr-eyes-skills
```

Then start a new session. If the brief and the skill stopped appearing without your doing anything, the marketplace was updated for you: `claude plugin list` no longer shows the plugin, and the second command brings it back. Add `--scope project` or `--scope local` if that is how you installed it.

The marketplace lists the plugin under its new name and maps the old one to it (`renames` in `marketplace.json`), so Claude Code moves the enabled entry in your settings to `recortex@mr-eyes-skills`. It does not install the new name on its own: between the two commands the plugin is not loaded, and no hook runs. `claude plugin update gh-issues-manager@mr-eyes-skills` fails with "not found" once the marketplace is updated; install the new name instead. Until you update the marketplace you stay on the installed 0.4.x, which keeps working. Run `claude plugin list` afterwards: it shows `recortex@mr-eyes-skills`, version 0.5.0 or later. The old plugin folder, `~/.claude/plugins/cache/mr-eyes-skills/gh-issues-manager/`, is left behind and can be deleted.

A copy of the plugin installed another way (a folder under `~/.claude/skills/` with hooks from `templates/settings-hook-snippet.json`, or a second plugin entry) stays as it is. Copy the new `skills/recortex` folder in, remove the old folder, and change the four hook commands to `$HOME/.claude/skills/recortex/scripts/`. Two copies enabled at once print two briefs, so disable or uninstall the other one.

## What keeps working with no action

| Thing | Current name | Earlier name, still read | When both are there |
|---|---|---|---|
| Configuration file at the project root | `.recortex.json` | `.gh-issues-manager.json` | The current file is read; the earlier one is ignored, and `hooks.py --doctor` says so |
| Index top folder | `$XDG_CACHE_HOME/recortex` | `$XDG_CACHE_HOME/gh-issues-manager`, used in place | The current folder; the earlier one is not touched |
| State and key top folder | `$XDG_STATE_HOME/recortex` | `$XDG_STATE_HOME/gh-issues-manager`, used in place | The current folder |
| Trusted list | `~/.config/recortex/trusted-repos` | `~/.config/gh-issues-manager/trusted-repos` | Both are read; a repository listed in either is trusted, with the logins of both |
| Settings (`"discovery": false`) | `~/.config/recortex/settings.json` | `~/.config/gh-issues-manager/settings.json` | The current file |
| Environment variables | `RECORTEX_GH`, `RECORTEX_CONFIG`, `RECORTEX_TRUSTED_FILE`, `RECORTEX_TRUSTED_REPOS`, `RECORTEX_HOOK_TIMEOUT`, `RECORTEX_DISCOVERY`, `RECORTEX_SYNC_PAGE` | the same with `GHIM_` | The `RECORTEX_` one when it is set and not empty |
| Triage workflow | `.github/workflows/recortex-triage.yml` | `.github/workflows/ghim-triage.yml`, left alone | `setup.py apply` writes no second labeler when the earlier one is there |
| Markers in comments | `<!-- ghim:event ... -->`, `<!-- ghim:resume:start -->`, `<!-- ghim:resume:end -->` | | Not renamed: they are the record format, and old and new comments are one format |

Everything on GitHub keeps working: labels, hub and topic bodies, event and resume comments. The plugin edits no posted text; a hub body that says "from the gh-issues-manager skill" can stay. `setup.py apply` run again in a project with `.gh-issues-manager.json` adds to that file and makes no second one.

Each storage folder is chosen by itself: the folder with the current name when anything is at that path, else the one with the earlier name when it exists, else a new folder with the current name. The earlier folders are used in place, never moved: an index carries a mark made over its path, so a moved index would be refused and built again, and an older copy of the plugin still running on the same machine shares the same index, lock and key. Every check on the storage applies to whichever folder is chosen; a symlink or a file at the current name is refused, and the earlier folder is then not used instead.

The session-start and subagent briefs carry one fixed sentence that the skill was named gh-issues-manager before 0.5.0, for projects whose CLAUDE.md still names the old skill. No brief says which earlier names this machine uses; `hooks.py --doctor` does.

## What to change by hand

- Names that point at the plugin's parts: the agents are now `recortex:record-drafter`, `recortex:record-reviewer` and `recortex:record-auditor`, and the skill is `/recortex:recortex` (plugin) or `/recortex` (folder install). Edit permission rules, your own agents and notes that use the old prefix; there is no alias for it. Permission rules that hold the plugin's path (under `~/.claude/plugins/cache/` or a folder install's folder) need the new path in the same way.
- A project's CLAUDE.md snippet that names the `gh-issues-manager` skill: replace the name. `setup.py apply` does not rewrite it and prints a note when it sees it.
- A folder install's folder and hook paths (see above).

## Optional renames

- The configuration file: rename `.gh-issues-manager.json` to `.recortex.json` once everyone on the project has recortex 0.5.0 or later. The file is committed, and a collaborator on 0.4.x cannot read the new name: their hooks would go silent and the setup line would appear. A record set up with 0.5.0 gets `.recortex.json` from the start, so collaborators on such a project need 0.5.0 or later too.
- The storage folders, with no session running and only once no copy of 0.4.x is used on this machine (a folder install or another Claude Code profile would make the earlier folders again with another key, and the two versions would then refuse each other's index): delete `~/.cache/gh-issues-manager` (the next session builds a new index under `~/.cache/recortex` in the background; moving it instead gains nothing, because an index is refused at a path other than the one it was made at), and move `~/.local/state/gh-issues-manager` to `~/.local/state/recortex` to keep the key and the hook state. A key in the earlier state folder also works with an index in the new cache folder.
- The trusted list and settings: move them to `~/.config/recortex/`. Until then both lists are read, so a repository is no longer trusted only once it is gone from both.
- Environment variables: rename `GHIM_*` to `RECORTEX_*`.
- An installed `.github/workflows/ghim-triage.yml` needs nothing; it labels new issues as before.

## How long the earlier names are read

Through every 0.x release, and at least twelve months from 0.5.0. Reading an earlier name is removed only in a major version, after one minor version in which `hooks.py --doctor` reports it as a problem with the fix. The storage folders used in place and the `ghim:` markers have no end date. Until then `hooks.py --doctor` lists, as notes, every earlier name in use: the configuration file, the storage folders, the trusted list that names the repository and each `GHIM_` variable that is set (by name, never its value).

The upgrade was checked on Claude Code 2.1.325. A client too old to know `renames` is likely to keep the installed 0.4.x under the old name and report that the marketplace no longer lists it; this is not documented by Claude Code.
