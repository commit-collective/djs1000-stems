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
