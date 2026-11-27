# djs1000-stems

`stemd` runs on a computer on the same network as a DJS-1000 and splits its samples into stems for the `stems` mod
of [djs1000-mods](https://github.com/commit-collective/djs1000-mods). On the unit, STEMS on a sample track's menu
opens a page whose SPLIT sends the track's sample. The computer separates it with [Demucs](https://github.com/facebookresearch/demucs) and sends back
2 stems (vocals, instrumental) or 4 (drums, bass, vocals, other). They land next to the sample, in the same format and
exactly as long, so a pattern or a loop set on the sample fits them too.

The `stems` mod is in beta from mods v0.6.0, off until it is turned on. Separate only samples
you have the right to use.

## What it needs

- A computer on the unit's network: a cable to the same switch or router as the DJS-1000, which has only Ethernet. The
  computer itself may be on Wi-Fi of that router.
- Windows 10 or 11 for the install script. Linux and macOS work with the [manual steps](#without-the-script).
- [Python](https://www.python.org/downloads/) 3.10 or later. On Windows, tick "Add python.exe to PATH" when installing it.
- An NVIDIA GPU is optional. Without one, the processor does it, slower: on a recent desktop processor a 60 second
  sample took about 20 seconds, and a mid-range NVIDIA GPU about 5. An older processor can take a minute or more.
- About 3 GB of disk with a GPU (PyTorch for CUDA), under 1 GB without.

## Install on Windows

1. Get this repository on the computer: `git clone`, or download it as a ZIP and unpack it.
2. In that folder, run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
   ```
   It makes a Python environment in `.venv`, installs PyTorch for the computer's NVIDIA GPU if it has one (else for
   the processor), Demucs and `stemd`, then downloads the model (80 MB, once) and checks that it loads. Nothing
   outside the folder changes, apart from pip's and PyTorch's caches in your user folder. `-Torch cpu` installs for the
   processor even with a GPU. Run it again to update.
3. Let the unit reach the computer, once, in a PowerShell opened as administrator:
   ```powershell
   New-NetFirewallRule -DisplayName stemd -Direction Inbound -Protocol TCP -LocalPort 4790 -Action Allow -Profile Private,Public -RemoteAddress LocalSubnet
   ```
   A cable straight to the unit, or a network with no internet, is often an "unidentified network", which Windows
   counts as public: that is why the rule covers both. `LocalSubnet` lets in only the computers of the networks this
   one is on, the unit's included.

## Run it

Pick a word only you know, and start the service with it:

```powershell
.venv\Scripts\stemd serve --token YOURWORD
```

It says which address to give the unit, and logs each request: the sample's name, its length and format, and how
long it took. Ctrl+C stops it.

On the unit, in `djs1000-mods/djs1000-mods.txt` on the USB stick (mods v0.3.0 and earlier keep it at the top):

```
stems = on
stems-host = 192.168.1.20
stems-token = YOURWORD
stems-count = 4
```

`stems-host` is the computer's address on the unit's network (`stemd serve` prints it). Add `:port` if the service
uses another one than 4790 (`--port`). Then open a sample track's menu, tap STEMS, then SPLIT. The STEMS page shows
SENDING, then SEPARATING with how far it is (SEPARATING TRACK 5: 42%), then a button for each stem. The mods'
[settings](https://github.com/commit-collective/djs1000-mods/blob/main/docs/settings.md) list the others.

### With the emulator

The [DJS-1000 emulator](https://github.com/commit-collective/djs1000-emulator) runs the app in WSL, and the mod reaches
the network from there. With `stemd` running on the same Windows computer, `stems-host` in the emulator's settings
(`~/djs/usb/djs1000-mods/djs1000-mods.txt` in WSL) is Windows's address as WSL sees it: the one `ip route show default`
gives in WSL. It can change when the computer restarts. The firewall rule above lets it in. With `stemd` installed in
WSL instead, `stems-host = 127.0.0.1` is enough, with no firewall rule.

### Start it with Windows

Keep the word in your user's environment once, then put `scripts\serve.cmd` in the Startup folder. In PowerShell,
in this folder:

```powershell
setx STEMD_TOKEN YOURWORD
$link = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\stemd.lnk")
$link.TargetPath = "$PWD\scripts\serve.cmd"; $link.WindowStyle = 7; $link.Save()
```

At each login the service starts in a minimized window, and also writes its log to `stemd.log` in this folder.
Deleting `stemd.lnk` from the Startup folder (Win+R, `shell:startup`) undoes it. `scripts\serve.cmd` also starts it
by hand, with the same log.

## Check it without the unit

From any computer with this repository installed (even with `--fake` only), send a WAV as the unit does:

```powershell
.venv\Scripts\stemd send 192.168.1.20 "C:\Samples\Loop.wav" --token YOURWORD --count 4
```

The stems are written next to the file, in `Loop (stems)`. `stemd separate FILE.wav --count 4` makes them on this
computer without the network, and `stemd check` says what it runs on (PyTorch, the GPU).

`stemd serve --fake --token YOURWORD` answers with simple filtered copies of the sample, with no model: it tries the
unit and the network on a computer without PyTorch.

## When it does not work

| On the unit | What to look at |
|---|---|
| NO COMPUTER ANSWERS | Is `stemd serve` running? Is `stems-host` its address on the unit's network? Is the firewall rule there? From another computer on that network, `stemd send` tells the same. |
| REFUSED BY COMPUTER | The service's log says why: most often `wrong token` (`stems-token` is not the word given to `--token`). |
| CONNECTION LOST | The computer went away mid-request. The service's log says if it failed. |

A GPU that is not used: `stemd check` says whether PyTorch sees it. An old NVIDIA driver can be too old for PyTorch's
CUDA build: update the driver, or install with `-Torch cpu`. An RTX 50 card needs `-Torch cu130`, which the script
picks by itself.

## Without the script

On Linux or macOS, or to choose each part:

```sh
python3 -m venv .venv
.venv/bin/pip install torch torchaudio        # or the command pytorch.org gives for your GPU
.venv/bin/pip install -e ".[demucs]"
.venv/bin/stemd check --download
.venv/bin/stemd serve --token YOURWORD
```

On Linux, open TCP 4790 in the firewall if it has one.

## Options

`stemd serve --help` lists them. Those worth knowing:

- `--model htdemucs_ft`: Demucs's fine-tuned model, a little better and about four times slower.
- `--shifts 2`: two passes averaged, a little better, twice as slow.
- `--device cpu`: the processor even with a GPU.
- `--max-seconds`: longer samples are refused (64 by default, as on the unit).
- `--bind ADDRESS`: listen only on that address of the computer.

## Security

The token is a shared word, kept in plain text in the unit's settings file and on this computer. It keeps other
people on a shared network from using your computer's GPU, nothing more. A request with a wrong token, or a file
longer than `--max-seconds` allows, is refused before its sample is kept, and at most four samples are taken in at
once. Run the service on networks you trust, and with `--bind` on the address of the unit's network when the computer
has others.

## How it talks to the unit

One TCP connection per sample, on port 4790: the unit sends the WAV, the service answers with progress messages
(at least every 5 seconds, as the unit gives up after 20 seconds of silence, and with the percentage done each time it
changes, at most once a second), then each stem, then a done mark. The
exchange is described at the top of [stemd/protocol.py](stemd/protocol.py). The mods' tests use a stand-in that
speaks it too, and this repository's tests check that the two agree.

## Developing

```sh
python -m unittest discover -s tests -v
STEMD_TEST_DEMUCS=1 python -m unittest discover -s tests -v     # with Demucs installed: a real separation too
```

## Licences

stemd is under the MIT licence or the Apache 2.0 licence, at your choice ([LICENSE-MIT](LICENSE-MIT),
[LICENSE-APACHE](LICENSE-APACHE)). Demucs is Meta's, under the MIT licence: it is installed from PyPI and pinned to
4.0.1, as the project is archived. Its model's weights are downloaded from Meta's servers the first time.
