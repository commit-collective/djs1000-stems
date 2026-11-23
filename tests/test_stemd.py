# SPDX-License-Identifier: MIT OR Apache-2.0
"""The WAV files, the exchange with the unit and the service, with the fake separator (no model needed).

    python -m unittest discover -s tests -v

STEMD_TEST_DEMUCS=1 also runs a sample through Demucs (it needs it installed, and downloads its weights once).
"""
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stemd import protocol, server, wav  # noqa: E402
from stemd.separate import Fake  # noqa: E402


def tone(rate=44100, seconds=1.0, channels=2):
    t = np.arange(int(rate * seconds)) / rate
    left = 0.5 * np.sin(2 * np.pi * 110 * t) + 0.2 * np.sin(2 * np.pi * 3000 * t)
    return np.stack([left * (0.9 ** c) for c in range(channels)], axis=1).astype(np.float32)


class Wav(unittest.TestCase):
    def test_each_format_comes_back_as_it_went(self):
        samples = tone(seconds=0.1)
        for fmt, tol in ((wav.Format(44100, 2, 16), 1 / 32768), (wav.Format(44100, 2, 24), 1 / (1 << 23)),
                         (wav.Format(48000, 2, 32), 1e-6), (wav.Format(44100, 2, 32, float=True), 0)):
            with self.subTest(fmt=fmt):
                back, got = wav.read(wav.write(samples, fmt))
                self.assertEqual(got, fmt)
                self.assertEqual(back.shape, samples.shape)
                self.assertLessEqual(float(np.abs(back - samples).max()), tol + 1e-7)

    def test_full_scale_and_beyond_are_clipped_not_wrapped(self):
        samples = np.array([[1.5, -1.5], [1.0, -1.0]], dtype=np.float32)
        back, _ = wav.read(wav.write(samples, wav.Format(44100, 2, 24)))
        self.assertTrue((back[:, 0] > 0.99).all() and (back[:, 1] < -0.99).all())

    def test_extensible_files_and_other_chunks_are_read(self):
        plain = wav.write(tone(seconds=0.05, channels=1), wav.Format(44100, 1, 24))
        fmt_body = struct.pack("<HHIIHH", 0xFFFE, 1, 44100, 44100 * 3, 3, 24) + struct.pack("<HHI", 22, 24, 4)
        fmt_body += struct.pack("<H", 1) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
        data_at = plain.index(b"data")
        extra = b"LIST" + struct.pack("<I", 5) + b"INFO!" + b"\0"           # an odd length, padded
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_body)) + fmt_body + extra + plain[data_at:]
        samples, fmt = wav.read(b"RIFF" + struct.pack("<I", len(body)) + body)
        self.assertEqual((fmt.bits, fmt.channels, fmt.float), (24, 1, False))
        self.assertEqual(len(samples), int(44100 * 0.05))

    def test_what_is_not_a_wav_is_refused(self):
        for data in (b"", b"RIFF\0\0\0\0AVI ", wav.write(tone(seconds=0.01), wav.Format(44100, 2, 16)).replace(b"fmt ", b"xxxx")):
            with self.assertRaises(wav.WavError):
                wav.read(data)

    def test_fit_cuts_or_pads_to_the_frame(self):
        samples = tone(seconds=0.01)
        self.assertEqual(len(wav.fit(samples, 100)), 100)
        padded = wav.fit(samples, len(samples) + 7)
        self.assertEqual(len(padded), len(samples) + 7)
        self.assertFalse(padded[-7:].any())


class Slow:
    """A separator that takes its time, to see the progress records."""
    name = "slow"

    def __init__(self, seconds):
        self.seconds = seconds

    def load(self):
        pass

    def __call__(self, samples, rate, count):
        time.sleep(self.seconds)
        return Fake()(samples, rate, count)


class Broken(Slow):
    def __call__(self, samples, rate, count):
        raise RuntimeError("out of memory")


class Service(unittest.TestCase):
    def start(self, separator=None, token="t1", max_seconds=64.0):
        srv = server.Server(("127.0.0.1", 0), server.Service(separator or Fake(), token, max_seconds))
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv.server_address[1]

    def send(self, port, data, token="t1", count=2, progress=None):
        return protocol.send_request("127.0.0.1", port, token, "Kick (1)", data, count, timeout=10,
                                     on_progress=progress)

    def test_stems_have_the_sources_format_and_length_and_add_up_to_it(self):
        port = self.start()
        source = tone(seconds=0.5)
        for count, fmt in ((2, wav.Format(44100, 2, 24)), (4, wav.Format(48000, 1, 16))):
            with self.subTest(count=count):
                samples = source[:, :fmt.channels]
                stems = self.send(port, wav.write(samples, fmt), count=count)
                self.assertEqual([name for name, _ in stems], list(protocol.NAMES[count]))
                total = 0
                for _, data in stems:
                    back, got = wav.read(data)
                    self.assertEqual((got, back.shape), (fmt, samples.shape))
                    total = total + back
                self.assertLess(float(np.abs(total - samples).max()), 4 / (1 << (fmt.bits - 1)))

    def test_a_wrong_token_an_unknown_version_and_a_long_sample_are_refused(self):
        port = self.start(max_seconds=1.0)
        short = wav.write(tone(seconds=0.2), wav.Format(44100, 2, 16))
        with self.assertRaisesRegex(protocol.ProtocolError, "wrong token"):
            self.send(port, short, token="nope")
        with self.assertRaisesRegex(protocol.ProtocolError, "over 1 seconds"):
            self.send(port, wav.write(tone(seconds=1.5), wav.Format(44100, 2, 16)))
        with self.assertRaisesRegex(protocol.ProtocolError, "not a WAV"):
            self.send(port, b"RIFF0000WAVEjunk")
        with self.assertRaisesRegex(protocol.ProtocolError, "not understood"):
            self.send(port, short, count=3)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(b"HTTP/1.1 GET /\r\n\r\n")
            self.assertEqual(sock.recv(1), b"E")

    def test_a_check_says_whether_the_token_is_taken(self):
        port = self.start()
        protocol.check("127.0.0.1", port, "t1")
        with self.assertRaisesRegex(protocol.ProtocolError, "wrong token"):
            protocol.check("127.0.0.1", port, "nope")
        protocol.check("127.0.0.1", self.start(token=None), "anything")

    def test_no_token_takes_any(self):
        port = self.start(token=None)
        self.assertEqual(len(self.send(port, wav.write(tone(seconds=0.1), wav.Format(44100, 2, 16)), token="")), 2)

    def test_progress_comes_while_it_works_and_while_it_waits_its_turn(self):
        self.addCleanup(setattr, server, "KEEPALIVE", server.KEEPALIVE)
        server.KEEPALIVE = 0.2
        port = self.start(Slow(1.0))
        data = wav.write(tone(seconds=0.1), wav.Format(44100, 2, 16))
        heard = {1: [], 2: []}
        results = {}

        def one(n):
            results[n] = self.send(port, data, progress=heard[n].append)
        first = threading.Thread(target=one, args=(1,))
        first.start()
        time.sleep(0.3)
        one(2)
        first.join()
        self.assertEqual(len(results[1]), 2)
        self.assertEqual(len(results[2]), 2)
        self.assertTrue(any(m.startswith("separating, ") for m in heard[1]), heard[1])
        self.assertIn("waiting for another sample to be done", heard[2])

    def test_a_separator_that_fails_says_so(self):
        port = self.start(Broken(0))
        with self.assertRaisesRegex(protocol.ProtocolError, "separation failed: out of memory"):
            self.send(port, wav.write(tone(seconds=0.1), wav.Format(44100, 2, 16)))

    def test_the_log_can_go_to_a_file_as_well(self):
        path = ROOT / "build" / "test.log"
        path.parent.mkdir(exist_ok=True)
        path.unlink(missing_ok=True)
        self.addCleanup(setattr, server, "LOG_FILE", None)
        server.LOG_FILE = str(path)
        port = self.start()
        with self.assertRaises(protocol.ProtocolError):
            self.send(port, b"junk", token="nope")
        self.assertIn("refused, wrong token", path.read_text(encoding="utf-8"))

    def test_a_unit_that_hangs_up_leaves_the_service_running(self):
        port = self.start(Slow(0.3))
        with socket.create_connection(("127.0.0.1", port)) as sock:
            sock.sendall(protocol.MAGIC + bytes((1, 2)) + protocol.text("t1"))     # and gone
        data = wav.write(tone(seconds=0.1), wav.Format(44100, 2, 16))
        with socket.create_connection(("127.0.0.1", port)) as sock:
            sock.sendall(protocol.MAGIC + bytes((1, 2)) + protocol.text("t1") + protocol.text("x")
                         + struct.pack(">I", len(data)) + data)
        self.assertEqual(len(self.send(port, data)), 2)


MODS_FAKE = ROOT.parent / "djs1000-mods" / "tests" / "stems_fake_pc.py"


@unittest.skipUnless(MODS_FAKE.exists(), "the mods' stand-in is not beside this repository")
class SameAsTheMods(unittest.TestCase):
    """The mods' tests use a stand-in for this service: this client (built as the unit's side) gets the same answers
    from it, so the two speak the same exchange."""

    def test_the_mods_stand_in_answers_this_client(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        log = ROOT / "build" / "fake-pc.log"
        log.parent.mkdir(exist_ok=True)
        process = subprocess.Popen([sys.executable, str(MODS_FAKE), "--port", str(port), "--token", "t1", "--log", str(log)])
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        data = wav.write(tone(seconds=0.1), wav.Format(44100, 2, 16))
        for _ in range(50):
            try:
                stems = protocol.send_request("127.0.0.1", port, "t1", "Kick", data, 4, timeout=5)
                break
            except ConnectionRefusedError:
                time.sleep(0.1)
        self.assertEqual([n for n, _ in stems], list(protocol.NAMES[4]))
        with self.assertRaisesRegex(protocol.ProtocolError, "wrong token"):
            protocol.send_request("127.0.0.1", port, "t2", "Kick", data, 2, timeout=5)
        protocol.check("127.0.0.1", port, "t1")
        with self.assertRaisesRegex(protocol.ProtocolError, "wrong token"):
            protocol.check("127.0.0.1", port, "t2")


@unittest.skipUnless(os.environ.get("STEMD_TEST_DEMUCS"), "STEMD_TEST_DEMUCS=1 runs Demucs")
class RealModel(unittest.TestCase):
    def test_demucs_gives_stems_that_fit_the_source(self):
        from stemd.separate import Demucs
        separator = Demucs()
        for fmt in (wav.Format(44100, 2, 24), wav.Format(48000, 1, 16)):
            samples = tone(fmt.rate, 3.0, fmt.channels)
            for count in (2, 4):
                with self.subTest(fmt=fmt, count=count):
                    stems = separator(samples, fmt.rate, count)
                    self.assertEqual(list(stems), list(protocol.NAMES[count]))
                    self.assertTrue(all(s.shape == samples.shape for s in stems.values()))
                    total = sum(stems.values())
                    self.assertLess(float(np.sqrt(((total - samples) ** 2).mean())), 0.05)


if __name__ == "__main__":
    unittest.main()
