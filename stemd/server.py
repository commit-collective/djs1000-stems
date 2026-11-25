# SPDX-License-Identifier: MIT OR Apache-2.0
"""The service: takes the unit's requests over TCP, separates one sample at a time, sends the stems back.

While a sample waits or is separated, a progress record goes out every few seconds: the unit gives up after 20 s
without one. While it is separated, the record says how far it is ("separating, 42%, 12 s") each time that changes,
at most once a second. One request at a time is separated (a GPU has room for one), the others wait their turn.
"""
import hmac
import inspect
import socketserver
import threading
import time

from . import protocol, wav

KEEPALIVE = 5.0             # seconds between progress records while working
STEP = 1.0                  # the least time between records that say a new percentage
READ_TIMEOUT = 30.0         # the longest the unit may pause while it sends its request


LOG_FILE = None             # also written there when set (--log), for a service that runs without a window


def log(message):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + message
    print(line, flush=True)
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


class Service:
    def __init__(self, separator, token, max_seconds=64.0):
        self.separator, self.token, self.max_seconds = separator, token, max_seconds
        self.busy = threading.Lock()

    def allowed(self, token):
        return self.token is None or hmac.compare_digest(token.encode("utf-8"), self.token.encode("utf-8"))

    def handle(self, sock, who):
        """One connection: a request and its answer. Never raises."""
        began = time.monotonic()
        try:
            sock.settimeout(READ_TIMEOUT)
            request = protocol.read_request(sock)
        except (protocol.ProtocolError, ConnectionError, OSError) as e:
            log("%s: not a request (%s)" % (who, e))
            return self.reply(sock, protocol.error("not understood"))
        if request.version == protocol.VERSION and request.count == 0 and not request.data:
            if not self.allowed(request.token):
                log("%s: a check, wrong token" % who)
                return self.reply(sock, protocol.error("wrong token"))
            return self.reply(sock, protocol.DONE)
        label = "%s: %r, %d stems" % (who, request.name[:80], request.count)
        if request.version != protocol.VERSION or request.count not in protocol.NAMES:
            log("%s: refused, version %d" % (label, request.version))
            return self.reply(sock, protocol.error("not understood (version %d)" % request.version))
        if not self.allowed(request.token):
            log("%s: refused, wrong token" % label)
            return self.reply(sock, protocol.error("wrong token"))
        try:
            samples, fmt = wav.read(request.data)
        except wav.WavError as e:
            log("%s: refused, %s" % (label, e))
            return self.reply(sock, protocol.error("not a WAV it can read: %s" % e))
        seconds = len(samples) / fmt.rate
        if seconds > self.max_seconds:
            log("%s: refused, %.1f s" % (label, seconds))
            return self.reply(sock, protocol.error("over %g seconds" % self.max_seconds))
        log("%s: %.1f s at %d Hz, %d bits, %d channels" % (label, seconds, fmt.rate, fmt.bits, fmt.channels))
        try:
            stems = self.separate(sock, samples, fmt, request.count)
        except (ConnectionError, OSError) as e:
            log("%s: the unit hung up (%s)" % (label, e))
            return
        except Exception as e:                              # a model that fails says so to the unit
            log("%s: failed, %s: %s" % (label, type(e).__name__, e))
            return self.reply(sock, protocol.error(("separation failed: %s" % e)[:120]))
        try:
            for name in protocol.NAMES[request.count]:
                sock.sendall(protocol.stem(name, wav.write(stems[name], fmt)))
            sock.sendall(protocol.DONE)
        except OSError as e:
            log("%s: the unit hung up while the stems were sent (%s)" % (label, e))
            return
        log("%s: done in %.1f s" % (label, time.monotonic() - began))

    def separate(self, sock, samples, fmt, count):
        """The stems, with progress records sent every few seconds while it waits its turn and while it works."""
        result, failure = {}, []
        state = {"step": "waiting for another sample to be done", "done": None}
        try:
            told = "on_progress" in inspect.signature(self.separator).parameters
        except (TypeError, ValueError):
            told = False

        def progressed(part):
            state["done"] = part

        def work():
            try:
                with self.busy:
                    state["step"] = "separating"
                    state["since"] = time.monotonic()
                    self.separator.load()
                    if told:
                        result.update(self.separator(samples, fmt.rate, count, on_progress=progressed))
                    else:
                        result.update(self.separator(samples, fmt.rate, count))
            except BaseException as e:
                failure.append(e)
        worker = threading.Thread(target=work, daemon=True)
        sock.sendall(protocol.progress("separating"))
        worker.start()
        sent_at, sent_percent = time.monotonic(), None
        while True:
            worker.join(min(STEP, KEEPALIVE))
            if not worker.is_alive():
                break
            now = time.monotonic()
            percent = None if state["done"] is None else int(100 * state["done"])
            if state["step"] == "separating" and percent is not None and percent != sent_percent and now - sent_at >= STEP:
                message = "separating, %d%%, %d s" % (percent, now - state["since"])
            elif now - sent_at >= KEEPALIVE:
                if state["step"] != "separating":
                    message = state["step"]
                elif percent is None:
                    message = "separating, %d s" % (now - state["since"])
                else:
                    message = "separating, %d%%, %d s" % (percent, now - state["since"])
            else:
                continue
            sock.sendall(protocol.progress(message))
            sent_at, sent_percent = now, percent
        if failure:
            raise failure[0]
        return result

    @staticmethod
    def reply(sock, data):
        try:
            sock.sendall(data)
        except OSError:
            pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service):
        self.service = service

        class Handler(socketserver.BaseRequestHandler):
            def handle(handler):
                service.handle(handler.request, "%s:%d" % handler.client_address[:2])
        super().__init__(address, Handler)
