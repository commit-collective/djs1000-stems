# SPDX-License-Identifier: MIT OR Apache-2.0
"""Separating a sample into stems. A separator takes samples (frames, channels) at a rate and gives back each stem's
samples with the same shape: {name: samples}, in protocol.NAMES order. A separator may be given on_progress, called
with the part done so far (0 to 1) while it works.

`Fake` uses no model: its stems are bands of the sample (one-pole filters) that add up to it, for trying the unit
and the network without a GPU. `Demucs` runs Meta's Demucs (pinned to 4.0.1 in pyproject.toml): 4 stems from the
model, or 2 as Demucs's own --two-stems does, vocals and the rest added together.
"""
import threading

import numpy as np

from .protocol import NAMES


def one_pole(samples, alpha):
    """A one-pole low-pass of each channel."""
    out = np.empty_like(samples)
    state = np.zeros(samples.shape[1], dtype=np.float64)
    for i, frame in enumerate(samples.astype(np.float64)):
        state += alpha * (frame - state)
        out[i] = state
    return out


class Fake:
    name = "fake (filters, no model)"

    def load(self):
        pass

    def __call__(self, samples, rate, count, on_progress=None):
        low = one_pole(samples, 0.02)
        if count == 2:
            return {"vocals": samples - low, "instrumental": low}
        lowest = one_pole(samples, 0.005)
        mid = one_pole(samples, 0.08)
        return {"drums": samples - mid, "bass": lowest, "vocals": mid - low, "other": low - lowest}


def pick_device(wanted="auto"):
    import torch
    if wanted != "auto":
        return wanted
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Demucs:
    def __init__(self, model="htdemucs", device="auto", shifts=1):
        self.model_name, self.wanted, self.shifts = model, device, shifts
        self.model, self.device = None, None
        self.lock = threading.Lock()

    @property
    def name(self):
        return "Demucs %s on %s" % (self.model_name, self.device or self.wanted)

    def load(self):
        """Loads the model (downloading its weights the first time, into PyTorch's hub cache)."""
        with self.lock:
            if self.model is not None:
                return
            import torch
            from demucs.pretrained import get_model
            self.device = pick_device(self.wanted)
            # Demucs 4.0.1's checkpoints are whole pickled objects, which PyTorch 2.6 and later refuse by default
            # (torch.load's weights_only). They come from Meta's URL with a checked hash, so they are loaded as before.
            original = torch.load

            def load_all(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return original(*args, **kwargs)
            torch.load = load_all
            try:
                model = get_model(self.model_name)
            finally:
                torch.load = original
            model.eval()
            self.model = model.to(self.device)

    def __call__(self, samples, rate, count, on_progress=None):
        import torch
        from demucs.apply import apply_model
        import julius
        self.load()
        model = self.model
        frames, channels = samples.shape
        wav = torch.from_numpy(np.ascontiguousarray(samples.T, dtype=np.float32))
        if channels == 1:
            wav = wav.expand(model.audio_channels, -1)
        elif channels != model.audio_channels:
            wav = wav[:model.audio_channels] if channels > model.audio_channels else wav.mean(0, keepdim=True).expand(model.audio_channels, -1)
        if rate != model.samplerate:
            wav = julius.resample_frac(wav, rate, model.samplerate)
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8            # as Demucs's own command does: a silent sample stays silent
        hooks = []
        if on_progress:
            # Demucs 4.0.1 has no progress callback: each piece of the sample is one call of a model, so the calls
            # are counted against the number apply_model will make (its pieces, for each shift and each model).
            parts = getattr(model, "models", None) or [model]
            length = wav.shape[-1] + (int(0.5 * model.samplerate) if self.shifts else 0)
            total = 0
            for part in parts:
                stride = int(0.75 * int(model.samplerate * float(part.segment)))
                total += max(1, self.shifts) * max(1, -(-length // max(1, stride)))
            calls = [0]

            def counted(module, args):
                calls[0] += 1
                on_progress(min(0.99, calls[0] / total))
            hooks = [part.register_forward_pre_hook(counted) for part in parts]
        try:
            with torch.no_grad():
                out = apply_model(model, ((wav - mean) / std)[None], device=self.device, shifts=self.shifts,
                                  split=True, overlap=0.25, progress=False)[0]
        finally:
            for hook in hooks:
                hook.remove()
        out = out * std + mean
        if rate != model.samplerate:
            out = julius.resample_frac(out, model.samplerate, rate)
        parts = {}
        for i, source in enumerate(model.sources):
            part = out[i].cpu().numpy().T                    # (frames, model channels)
            if channels == 1:
                part = part.mean(axis=1, keepdims=True)
            elif channels != part.shape[1]:
                part = np.repeat(part.mean(axis=1, keepdims=True), channels, axis=1)
            parts[source] = fit(part, frames)
        if count == 2:
            vocals = parts["vocals"]
            rest = sum(v for k, v in parts.items() if k != "vocals")
            return {"vocals": vocals, "instrumental": rest}
        missing = [n for n in NAMES[4] if n not in parts]
        if missing:
            raise ValueError("the model %s has no %s stem" % (self.model_name, ", ".join(missing)))
        return {n: parts[n] for n in NAMES[4]}


def fit(samples, frames):
    from .wav import fit as fit_frames
    return fit_frames(samples.astype(np.float32), frames)
