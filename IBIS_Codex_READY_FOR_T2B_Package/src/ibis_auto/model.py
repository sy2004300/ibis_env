from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Corner:
    name: str
    process: str
    temperature: str
    spf_key: str
    voltages: dict[str, str] = field(default_factory=dict)
    calibration: dict[str, str] = field(default_factory=dict)
    spf: Path | None = None


@dataclass
class Signal:
    name: str
    width: int
    direction: str
    pad: bool
    attribute_type: str
    power_domain: str
    ground_domain: str
    default: str
    description: str
    databook_description: str
    row_order: int


@dataclass
class ModulePlan:
    name: str
    generate_type: str
    impedances: list[int]


@dataclass
class Config:
    roots: dict[str, Path]
    modules: list[ModulePlan]
    corners: dict[str, Corner]
    voltage_order: list[str]
    simulation_options: list[str]
    aliases: dict[tuple[str, str, str], str]
    appends: list[tuple[str, str, str]]
    templates: dict[tuple[str, str], str]
    overrides: list[dict[str, str]]
    attribute_overrides: list[dict[str, str]]
    msi_mappings: dict[str, tuple[str, str, str]]

