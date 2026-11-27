# SPDX-License-Identifier: MIT OR Apache-2.0
"""stemd: separates the DJS-1000's samples into stems for its stems mod.

    stemd serve --token WORD                 the service the unit sends its samples to (TCP 4790)
    stemd serve --token WORD --fake          the same with filters instead of a model, to try the unit and the network
    stemd check [--download]                 what it would run on (PyTorch, the GPU), and the model's weights
    stemd separate FILE.wav [--count 4]      stems of a file on this computer, written next to it
    stemd send HOST FILE.wav --token WORD    sends a file as the unit does, to check a service from another computer
"""
import argparse
import os
import socket
import sys
import time

from . import __version__, protocol, wav

PORT = 4790


def separator_of(args):
    from .separate import Demucs, Fake
    return Fake() if args.fake else Demucs(args.model, args.device, args.shifts)


def addresses():
    """This computer's IPv4 addresses, as far as it can tell without changing anything."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith("127."))


def serve(args):
    from . import server as server_module
    from .server import Server, Service, log
    server_module.LOG_FILE = args.log
    token = args.token if args.token is not None else os.environ.get("STEMD_TOKEN")
    if not token and not args.no_token:
        sys.exit("stemd: give a --token (the same word as stems-token on the unit), or --no-token on a network "
                 "where only your own devices are")
    separator = separator_of(args)
    if not args.fake:
        log("loading %s (the first time, its weights are downloaded)" % separator.model_name)
        try:
            separator.load()
        except Exception as e:
            sys.exit("stemd: the model did not load: %s: %s. `stemd check` says more, --fake runs without it"
                     % (type(e).__name__, e))
    service = Service(separator, token or None, args.max_seconds)
    try:
        server = Server((args.bind, args.port), service)
    except OSError as e:
        sys.exit("stemd: cannot listen on %s:%d: %s" % (args.bind, args.port, e))
    log("stemd %s: %s, listening on %s:%d" % (__version__, separator.name, args.bind, args.port))
    if args.bind in ("0.0.0.0", ""):
        here = addresses()
        if here:
            log("on the unit: stems-host = %s (or the address of the network the unit is on)" % here[0]
                + (", this computer also has " + ", ".join(here[1:]) if len(here) > 1 else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("stopped")
    finally:
        server.server_close()


def check(args):
    print("stemd %s, Python %s" % (__version__, sys.version.split()[0]))
    try:
        import torch
        import demucs
    except ImportError as e:
        print("Demucs is not installed (%s): only --fake works. See the README's install steps." % e)
        return 1
    print("PyTorch %s, Demucs %s" % (torch.__version__, demucs.__version__))
    from .separate import Demucs, pick_device
    device = pick_device(args.device)
    if torch.cuda.is_available():
        print("GPU: %s (CUDA %s)" % (torch.cuda.get_device_name(0), torch.version.cuda))
        try:
            (torch.ones(8, device="cuda") * 2).sum().item()
        except Exception as e:
            print("  but it cannot run on it: %s. Install the PyTorch build for this GPU (see the README)" % e)
            return 1
    else:
        print("No CUDA GPU%s: it runs on the processor, a minute or two for a 60 s sample"
              % (" that this PyTorch can use" if torch.version.cuda is None else ""))
    print("It will run on: %s" % device)
    if args.download:
        separator = Demucs(args.model, args.device)
        began = time.monotonic()
        separator.load()
        print("Model %s ready (%.0f s)" % (args.model, time.monotonic() - began))
    return 0


def separate(args):
    separator = separator_of(args)
    with open(args.file, "rb") as f:
        samples, fmt = wav.read(f.read())
    began = time.monotonic()
    stems = separator(samples, fmt.rate, args.count)
    base, _ = os.path.splitext(args.file)
    folder = args.out or base + " (stems)"
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(base)
    for stem in protocol.NAMES[args.count]:
        path = os.path.join(folder, "%s (%s).wav" % (name, stem))
        with open(path, "wb") as f:
            f.write(wav.write(stems[stem], fmt))
        print(path)
    print("%s: %.1f s of audio in %.1f s" % (separator.name, len(samples) / fmt.rate, time.monotonic() - began))
    return 0


def send(args):
    with open(args.file, "rb") as f:
        data = f.read()
    name = os.path.splitext(os.path.basename(args.file))[0]
    host, _, port = args.host.partition(":")
    try:
        stems = protocol.send_request(host, int(port or PORT), args.token or "", name, data, args.count, timeout=20.0,
                                      on_progress=lambda m: print("the computer says:", m))
    except protocol.ProtocolError as e:
        sys.exit("refused: %s" % e)
    except (OSError, ConnectionError) as e:
        sys.exit("failed: %s" % e)
    asked = protocol.NAMES[args.count]
    if sorted(stem for stem, _ in stems) != sorted(asked):
        sys.exit("refused: the computer sent %s, not %s" % (", ".join(repr(s) for s, _ in stems), ", ".join(asked)))
    folder = args.out or os.path.splitext(args.file)[0] + " (stems)"
    os.makedirs(folder, exist_ok=True)
    for stem, data in stems:
        path = os.path.join(folder, "%s (%s).wav" % (name, stem))
        with open(path, "wb") as f:
            f.write(data)
        print(path)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stemd", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def model_options(p):
        p.add_argument("--fake", action="store_true", help="filters instead of a model: no PyTorch needed")
        p.add_argument("--model", default="htdemucs",
                       help="the Demucs model (default htdemucs. htdemucs_ft is a little better and four times slower)")
        p.add_argument("--device", default="auto", help="auto (a CUDA GPU if there is one), cuda, cpu or mps")
        p.add_argument("--shifts", type=int, default=1, help="passes with the sample shifted, averaged (slower, a little better)")

    p = sub.add_parser("serve", help="the service the unit sends its samples to")
    p.add_argument("--token", help="the word the unit must send (stems-token). Also read from STEMD_TOKEN")
    p.add_argument("--no-token", action="store_true", help="take requests with any token")
    p.add_argument("--bind", default="0.0.0.0", help="the address to listen on (default all of this computer's)")
    p.add_argument("--port", type=int, default=PORT, help="default %d, the mod's default" % PORT)
    p.add_argument("--max-seconds", type=float, default=64.0, help="longer samples are refused (default 64, as on the unit)")
    p.add_argument("--log", help="also write the log to this file (for a service started without a window)")
    model_options(p)
    p.set_defaults(run=serve)

    p = sub.add_parser("check", help="what it would run on, and whether the model loads")
    p.add_argument("--download", action="store_true", help="load the model, downloading its weights if needed")
    p.add_argument("--model", default="htdemucs")
    p.add_argument("--device", default="auto")
    p.set_defaults(run=check)

    p = sub.add_parser("separate", help="stems of a WAV on this computer")
    p.add_argument("file")
    p.add_argument("--count", type=int, choices=(2, 4), default=2)
    p.add_argument("--out", help="the folder (default: '<name> (stems)' next to the file)")
    model_options(p)
    p.set_defaults(run=separate)

    p = sub.add_parser("send", help="send a WAV as the unit does, to check a service")
    p.add_argument("host", help="the service's address, with :port if it is not %d" % PORT)
    p.add_argument("file")
    p.add_argument("--token", default="")
    p.add_argument("--count", type=int, choices=(2, 4), default=2)
    p.add_argument("--out", help="the folder (default: '<name> (stems)' next to the file)")
    p.set_defaults(run=send)

    args = parser.parse_args(argv)
    return args.run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
