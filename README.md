# djs1000-stems

`stemd` is the companion service for the [DJS-1000 Stems mod](https://commitcollective.cc/djs1000/mods/).
Tap **STEMS → SPLIT** on a sample track to send its audio to a computer running `stemd`.
[Demucs](https://github.com/facebookresearch/demucs) separates it into vocals and instrumental,
or drums, bass, vocals and other. The stems are saved beside the original sample. They match its
format and length so the same loops and patterns still fit.

## What you need

- [DJS-1000 Mods v0.6.0 or later](https://commitcollective.cc/djs1000/mods/), with **Stems** enabled.
  The mod is in beta and off by default.
- A computer that can reach the DJS-1000 over the local network. Connect the DJS by Ethernet.
  The computer can use Ethernet or Wi-Fi on the same network.
- [Python](https://www.python.org/downloads/) 3.11 or later for the setup below. Python 3.12 is a good
  choice for a new installation. A GPU is optional. CPU separation works too and takes longer.

The service has been tested on Windows with CPU and NVIDIA CUDA. The manual setup below also
covers Linux and macOS, where end-to-end testing is still pending.

## 1. Install and start the service

Download the Source code ZIP from the [latest release](https://github.com/commit-collective/djs1000-stems/releases/latest)
or clone the repository. Open a terminal in the extracted folder.

**Linux or macOS**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ".[demucs]"
.venv/bin/stemd check --download
.venv/bin/stemd serve --token YOURWORD
```

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[demucs]"
.\.venv\Scripts\stemd.exe check --download
.\.venv\Scripts\stemd.exe serve --token YOURWORD
```

Choose your own token and use it again in the DJS settings. The check downloads the model weights
on first run. For a specific CPU or GPU build, use the [PyTorch install selector](https://pytorch.org/get-started/locally/)
and install its recommended `torch` and matching `torchaudio` into the same environment before
installing `.[demucs]`.

Use the computer's IPv4 address on the DJS network. The service lists local addresses at startup.
If the computer has several network connections, use `--bind ADDRESS` to listen only on the DJS
network's address. If a firewall blocks the connection, allow inbound TCP 4790 from the DJS or
its subnet. Run the service on a network you trust. Press Ctrl+C to stop it.

<details>
<summary>Windows installer, firewall and startup</summary>

The optional installer creates `.venv`, selects a CPU or NVIDIA PyTorch build and downloads the model.
Run it from the repository folder. Add `-Torch cpu` to force the CPU build.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

If Windows Firewall blocks the DJS, run this once in an administrator PowerShell. The Public
profile covers direct Ethernet connections that Windows classifies as unidentified.

```powershell
New-NetFirewallRule -DisplayName stemd -Direction Inbound -Protocol TCP -LocalPort 4790 -Action Allow -Profile Private,Public -RemoteAddress LocalSubnet
```

To start the service at login, run the following from the repository folder. The shortcut starts
the service minimized and writes a log to `stemd.log`. Delete the shortcut from `shell:startup`
to remove it.

```powershell
setx STEMD_TOKEN YOURWORD
$link = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\stemd.lnk")
$link.TargetPath = "$PWD\scripts\serve.cmd"
$link.WindowStyle = 7
$link.Save()
```

</details>

## 2. Connect the DJS-1000

On the USB stick, edit `djs1000-mods/djs1000-mods.txt` and add or update these lines.

```ini
stems = on
stems-host = 192.168.1.20
stems-token = YOURWORD
stems-count = 4
```

Replace the example address and token. Use `stems-count = 2` for vocals and instrumental.
If you started the service with a custom `--port`, append it to the address in `stems-host`.
Restart the DJS if you just enabled the mod. Open a sample track's menu, then select **STEMS → SPLIT**.
The page shows progress and displays the stems when they arrive.

### With the emulator

Use `127.0.0.1` for `stems-host` when the service and emulator backend run in the same Linux
environment. If the backend runs in WSL or a Linux VM and the service runs on the host, use a
host address reachable from the guest. See the [DJS-1000 emulator setup guide](https://github.com/commit-collective/djs1000-emulator/blob/main/docs/running.md)
for platform and network details.

## Check the connection

From the same computer, send a WAV to the running service. In the examples below, use the same `stemd` executable as in the install step.

```sh
stemd send 127.0.0.1 "Loop.wav" --token YOURWORD --count 4
```

Use the service computer's address if testing from another machine or if the service is bound to
a specific address. The results go into `Loop (stems)` beside the file.
`stemd separate "Loop.wav" --count 4` splits the file locally without a server.

| On the DJS | What to check |
| --- | --- |
| NO COMPUTER ANSWERS | Check the service is running, the address is reachable and the firewall allows the connection. |
| REFUSED BY COMPUTER | Check the service log for the reason. A wrong token means the two settings differ. |
| CONNECTION LOST | Check the network connection and the service log for an interrupted split. |

Run `stemd check` to see which device is selected. If the GPU setup fails, try `stemd serve --device cpu --token YOURWORD`.
See `stemd serve --help` for model, network and sample-length options.

## Developing

Install with `python -m pip install .` to run the tests or use `stemd serve --fake --token YOURWORD` without PyTorch.
The fake separator supplies filtered copies for testing the connection. The [protocol](stemd/protocol.py)
describes the exchange with the mod.

```sh
python -m unittest discover -s tests -v
```

Set `STEMD_TEST_DEMUCS=1` to also run the separation tests when Demucs is installed.

## Licences

Choose the [MIT licence](LICENSE-MIT) or the [Apache 2.0 licence](LICENSE-APACHE).
Demucs is an MIT-licensed dependency pinned to 4.0.1. Its model weights are downloaded separately.
