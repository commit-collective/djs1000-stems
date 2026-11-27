# Changelog

Newest first. A release is a tagged commit.

## v0.1.0

For the `stems` mod of DJS-1000 mods v0.6.0.

- `stemd serve`: the service the DJS-1000's stems mod sends its samples to, with Demucs (2 or 4 stems) on an NVIDIA
  GPU or the processor. Each stem has its sample's format and exact length. It sends progress at least every 5
  seconds, with the percentage done, takes one sample at a time and checks a token and the sample's size before
  it takes the sample in. `--fake` answers with filtered copies, with no model.
- `stemd check`, `stemd separate` and `stemd send`: what it runs on, stems of a local file, and a request as the unit
  sends it, to check a service from another computer.
- `scripts\install.ps1` installs it on Windows, with PyTorch for the computer's GPU, and `scripts\serve.cmd` starts it,
  also from the Startup folder.
