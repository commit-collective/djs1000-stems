# Changelog

Newest first. A release is a tagged commit.

## v0.1.0

The first release: a computer on the network that splits the DJS-1000's samples into stems, for the `stems` mod of
DJS-1000 mods v0.6.0.

### The service

- `stemd serve` separates each sample it is sent with Demucs, into 2 or 4 stems, on an NVIDIA GPU or the processor.
- Each stem has its sample's format and exact length.
- The unit sees how far a separation is, and samples wait their turn one at a time.
- A token keeps other computers out, and a request is checked before its sample is taken in.
- `--fake` answers with filtered copies of the sample, with no model.

### Tools

- `stemd check` says what it runs on, and `stemd separate` makes the stems of a local file.
- `stemd send` sends a sample as the unit does, to check a service from another computer.

### Windows

- `scripts\install.ps1` installs it with PyTorch for the computer's GPU, and `scripts\serve.cmd` starts it, also from
  the Startup folder.
