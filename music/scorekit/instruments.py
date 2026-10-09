"""Instrument definitions: which zones, how they behave, where they sit."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import library as lib
from .library import Zone

NOTE = r"(?P<note>[A-G]#?-?\d)"
STEMS = ("piano", "strings", "mallets", "bass", "percussion", "synth", "winds")


@dataclass
class Instrument:
    name: str
    stem: str
    zones: list[Zone]
    kind: str = "oneshot"           # piano | sustain | oneshot
    release: float = 0.3            # seconds of release after key-up
    attack: float = 0.002           # extra fade-in (seconds)
    pre_roll: float = 0.0           # start this much early (slow attacks)
    pan: float = 0.0                # -1 left .. +1 right
    width: float = 1.0              # stereo width of the sample itself
    gain_db: float = 0.0
    veltrack: float = 0.6           # 0 = velocity ignores gain, 1 = square law
    detune_cents: float = 2.0       # humanised tuning spread
    xfade_layers: bool = False      # blend two dynamic layers by velocity
    lowpass: float | None = None    # static tone shaping (Hz)
    highpass: float | None = None
    extra: dict = field(default_factory=dict)

    def pick(self, pitch: float, vel: int, rr: int) -> list[tuple[Zone, float]]:
        """Return [(zone, weight)] for a note: nearest pitch, matching layer."""
        best_pitch = min(self.zones, key=lambda z: abs(z.pitch - pitch)).pitch
        near = [z for z in self.zones if abs(z.pitch - best_pitch) < 0.5]
        layers = sorted({z.layer for z in near})
        if self.xfade_layers and len(layers) > 1:
            pos = (vel / 127.0) * (len(layers) - 1)
            lo = layers[min(int(pos), len(layers) - 2)]
            hi = layers[layers.index(lo) + 1]
            frac = min(1.0, max(0.0, pos - layers.index(lo)))
            return [(self._rr(near, lo, rr), (1 - frac) ** 0.5),
                    (self._rr(near, hi, rr), frac ** 0.5)]
        exact = [z for z in near if z.lovel <= vel <= z.hivel]
        if exact:
            layer = exact[0].layer
        else:
            target = vel / 127.0 * (max(layers) + 1)
            layer = min(layers, key=lambda l: abs(l + 0.5 - target))
        return [(self._rr(near, layer, rr), 1.0)]

    @staticmethod
    def _rr(near: list[Zone], layer: int, rr: int) -> Zone:
        cands = sorted((z for z in near if z.layer == layer), key=lambda z: z.rr)
        return cands[rr % len(cands)]


def _v(folder: str, pattern: str, layers: list[str]) -> list[Zone]:
    return lib.vsco(folder, pattern, layers)


def _strings() -> list[Instrument]:
    s = "Strings/"
    short = dict(release=0.35, veltrack=0.7, detune_cents=2.5)
    sus = dict(kind="sustain", release=0.45, attack=0.03, pre_roll=0.06, veltrack=0.5,
               detune_cents=3.0)
    return [
        Instrument("vln_spic", "strings",
                   _v(s + "Violin Section/Spic", rf"VlnEns_Spic_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v2"]),
                   pan=-0.4, width=0.6, **short),
        Instrument("vla_spic", "strings",
                   _v(s + "Viola Section/spic", rf"Violas_spic_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v2"]),
                   pan=0.15, width=0.5, **short),
        Instrument("vc_spic", "strings",
                   _v(s + "Cello Section/spic", rf"spic_{NOTE}_(?P<layer>v\d)_RR(?P<rr>\d)\.wav", ["v1", "v2"]),
                   pan=0.4, width=0.5, **short),
        Instrument("cb_spic", "bass",
                   _v(s + "Solo Contrabass/Spic", rf"BKCtbss_Spic_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v3"]),
                   pan=0.1, width=0.3, release=0.3, veltrack=0.6, lowpass=5000),
        Instrument("vln_pizz", "strings",
                   _v(s + "Violin Section/Pizz", rf"VlnEns_Pizz_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v2"]),
                   release=0.25, pan=-0.4, width=0.5, veltrack=0.7),
        Instrument("vla_pizz", "strings",
                   _v(s + "Viola Section/pizz", rf"ViolaEns_pizz_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v2"]),
                   release=0.25, pan=0.15, width=0.5, veltrack=0.7),
        Instrument("vc_pizz", "strings",
                   _v(s + "Cello Section/pizzT", rf"pizzT_{NOTE}_(?P<layer>v\d)_RR(?P<rr>\d)\.wav", ["v1", "v2"]),
                   release=0.3, pan=0.4, width=0.5, veltrack=0.7),
        Instrument("cb_pizz", "bass",
                   _v(s + "Solo Contrabass/Pizz", rf"BKCtbss_Pizz_{NOTE}_(?P<layer>v\d)_rr(?P<rr>\d)\.wav", ["v1", "v3"]),
                   release=0.35, pan=0.1, width=0.3, veltrack=0.6, lowpass=5000),
        Instrument("vln_sus", "strings",
                   _v(s + "Violin Section/susVib", rf"VlnEns_susVib_{NOTE}_(?P<layer>v\d)\.wav", ["v1", "v2"]),
                   pan=-0.4, width=0.6, **sus),
        Instrument("vla_sus", "strings",
                   _v(s + "Viola Section/susvib", rf"ViolaEns_susvib_{NOTE}_(?P<layer>v\d)_\d\.wav", ["v1", "v2"]),
                   pan=0.15, width=0.5, **sus),
        Instrument("vc_sus", "strings",
                   _v(s + "Cello Section/susvib", rf"susvib_{NOTE}_(?P<layer>v\d)_(?P<rr>\d)\.wav", ["v1", "v3"]),
                   pan=0.4, width=0.5, **sus),
    ]


def _mallets_and_winds() -> list[Instrument]:
    return [
        Instrument("marimba", "mallets",
                   _v("Percussion/Marimba", rf"Marimba_hit_Outrigger_{NOTE}_loud_01\.wav", ["v1"]),
                   release=0.6, pan=-0.2, width=0.5, veltrack=0.75, detune_cents=0.0, gain_db=7.0),
        Instrument("xylo", "mallets",
                   _v("Percussion/Xylo", rf"Xylo_Medium_{NOTE}_ff_01_far\.wav", ["v1"]),
                   release=0.5, pan=0.3, width=0.5, veltrack=0.8, detune_cents=0.0,
                   lowpass=6500, gain_db=-6.0),
        Instrument("glock", "mallets",
                   _v("Percussion/Glock", rf"glock_medium_{NOTE}\.wav", ["v1"]),
                   release=2.0, pan=0.35, width=0.6, veltrack=0.8, detune_cents=0.0,
                   lowpass=6500, gain_db=1.5),
        Instrument("harp", "mallets",
                   _v("Strings/Harp", rf"KSHarp_{NOTE}_\w+\.wav", ["v1"]),
                   release=1.5, pan=-0.5, width=0.6, veltrack=0.7, detune_cents=0.0, gain_db=4.0),
        Instrument("horn", "winds",
                   _v("Brass/F Horn/sus", rf"MOHorn_sus_{NOTE}_(?P<layer>v\d)_1\.wav", ["v1", "v2", "v3"]),
                   kind="sustain", release=0.4, attack=0.05, pre_roll=0.04, pan=0.2,
                   width=0.4, veltrack=0.5, lowpass=5000, gain_db=-3.0, extra={"arc": (4.0, 3.0)}),
    ]


@lru_cache(maxsize=None)
def registry() -> dict[str, Instrument]:
    insts = [Instrument("piano", "piano", lib.salamander(), kind="piano",
                        release=0.5, width=0.7, veltrack=0.72, detune_cents=0.0)]
    insts += _strings() + _mallets_and_winds()
    return {i.name: i for i in insts}
