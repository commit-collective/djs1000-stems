# djs1000-stems: working rules

- This repository is public. It is the computer side of the `stems` mod of djs1000-mods: keep the exchange in
  `stemd/protocol.py` the same as the mod's (`mods/stems.c`) and its stand-in (`tests/stems_fake_pc.py` there). A change
  to it is a change on both sides: say so in the reply.
- Nothing from Pioneer DJ or AlphaTheta goes in this repository: no firmware, no samples or projects from the unit.
  Test audio is made by the tests. No audio, model weights or environments are committed.
- The service is installed on the user's own computer, not on the one an agent works on. Do not install PyTorch,
  Demucs or the model on the development machine unless the user asks. The tests run with the standard library and
  numpy (`python -m unittest discover -s tests -v`). `STEMD_TEST_DEMUCS=1` runs a real separation where Demucs is
  installed.
- Always commit completed changes locally on `main`. Ask before pushing, tagging or adding a remote, and never amend a
  pushed commit. Amending the latest commit is fine while it is not pushed and the change iterates on it.
- Commit subjects: an action verb, under 50 characters. Body optional, otherwise a blank line and lines under 72
  characters. No semicolons in prose, emojis or attribution.
- Demucs is pinned (the project is archived). A new version of it or of PyTorch is checked with a real separation
  before the pin moves.

## The changelog

`CHANGELOG.md` tells someone upgrading from the last release what changed for them, not the history of the work.

- The file opens with `# Changelog` and the line "Newest first. A release is a tagged commit."
- What is not released yet goes under `## Not yet released`. A release renames that heading to `## vX.Y.Z`.
- An entry opens with one or two plain sentences: what the release brings, for the person who installs it.
- Its items go under `###` headings: `Compatibility changes` first when there are any, then the repository's own
  areas, then `Fixes` last.
- One short line per item, in plain words for the person who uses it: what changed, not how it was found, why it
  broke or how it was tested. No internal formats or maintainer tooling. A compatibility note may take a second
  sentence.
- A feature new in the coming release is described as it works now. A fix to it, or a change of it, before the
  release amends that feature's line. It never gets a line of its own.
- A fix line is only for a bug that was in a published release.
- A behaviour that changes from the last release goes under `Compatibility changes`.
- Nothing that is not checked yet ("untried", "pending", "experimental") goes in unless the owner wants it said.

In this repository too: a tag makes a GitHub release with its entry as the notes (`.github/workflows/release.yml`).
Actions, release, Run workflow writes the notes of a tag again after a correction.
