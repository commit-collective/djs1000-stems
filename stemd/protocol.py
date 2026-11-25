# SPDX-License-Identifier: MIT OR Apache-2.0
"""The exchange between the DJS-1000's stems mod and this service, over TCP. Numbers are big-endian.

The unit sends:

    "DJST"              4 bytes
    version             1 byte, 1
    stems               1 byte, 2 or 4
    token               text: 2 bytes of length, then UTF-8
    sample name         text, without its extension
    length              4 bytes
    the WAV file        that many bytes

The service answers with records, each a letter and what follows it:

    P text              progress. The unit gives up after 20 s with nothing, so one comes at least every few seconds.
                        A number just before a "%" ("separating, 42%, 12 s") is how far it is: the unit shows it
    S text length data  a stem: its name (at most 24 letters, digits, spaces or dashes), then its WAV file
    E text              refused or failed: the unit removes what it wrote and shows REFUSED BY COMPUTER
    D                   done

The unit takes at most 4 stems and names each file `<sample name> (<stem>).wav`.

A request for 0 stems with no file is a check: the STEMS page asks it when it opens, to say before SPLIT whether the
computer is there. The answer is D, or E "wrong token".
"""
import socket
import struct

MAGIC = b"DJST"
VERSION = 1
NAMES = {2: ("vocals", "instrumental"), 4: ("drums", "bass", "vocals", "other")}
MAX_TEXT = 1024                 # longer texts are not something the unit sends
MAX_FILE = 256 * 1024 * 1024    # the unit's whole sample pool: no sample is larger


class ProtocolError(ValueError):
    """The other side did not speak the exchange."""


def exact(sock, n):
    chunks, left = [], n
    while left:
        part = sock.recv(min(left, 1 << 16))
        if not part:
            raise ConnectionError("the other side hung up")
        chunks.append(part)
        left -= len(part)
    return b"".join(chunks)


def text_in(sock, limit=MAX_TEXT):
    (n,) = struct.unpack(">H", exact(sock, 2))
    if n > limit:
        raise ProtocolError("a text of %d bytes" % n)
    return exact(sock, n).decode("utf-8", "replace")


def text(value):
    data = value.encode("utf-8")[:0xFFFF]
    return struct.pack(">H", len(data)) + data


class Request:
    def __init__(self, version, count, token, name, data):
        self.version, self.count, self.token, self.name, self.data = version, count, token, name, data


def read_request(sock, max_file=MAX_FILE):
    """The unit's request. ProtocolError if it is not one."""
    head = exact(sock, 6)
    if head[:4] != MAGIC:
        raise ProtocolError("not a stems request")
    version, count = head[4], head[5]
    token = text_in(sock)
    name = text_in(sock)
    (size,) = struct.unpack(">I", exact(sock, 4))
    if size > max_file:
        raise ProtocolError("a file of %d bytes" % size)
    return Request(version, count, token, name, exact(sock, size))


def progress(message):
    return b"P" + text(message)


def error(message):
    return b"E" + text(message)


def stem(name, data):
    return b"S" + text(name) + struct.pack(">I", len(data)) + data


DONE = b"D"


def check(host, port, token, timeout=5.0):
    """Asks as the unit's STEMS page does whether the service is there and takes the token. Raises ProtocolError with
    the service's own words if it refuses, OSError if nothing answers."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(MAGIC + bytes((VERSION, 0)) + text(token) + text("") + struct.pack(">I", 0))
        kind = exact(sock, 1)
        if kind == b"E":
            raise ProtocolError(text_in(sock))
        if kind != DONE:
            raise ProtocolError("an answer that is not understood: %r" % kind)


def send_request(host, port, token, name, data, count=2, timeout=30.0, on_progress=None):
    """Sends a sample as the unit does and gives back the stems: [(name, wav bytes)]. Raises ProtocolError with the
    service's own words if it refuses, ConnectionError if it hangs up. `timeout` is the longest silence allowed, 20 s
    on the unit."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(MAGIC + bytes((VERSION, count)) + text(token) + text(name) + struct.pack(">I", len(data)) + data)
        stems = []
        while True:
            kind = exact(sock, 1)
            if kind == b"P":
                message = text_in(sock)
                if on_progress:
                    on_progress(message)
            elif kind == b"S":
                stem_name = text_in(sock)
                (size,) = struct.unpack(">I", exact(sock, 4))
                stems.append((stem_name, exact(sock, size)))
            elif kind == b"E":
                raise ProtocolError(text_in(sock))
            elif kind == b"D":
                return stems
            else:
                raise ProtocolError("an answer that is not understood: %r" % kind)
