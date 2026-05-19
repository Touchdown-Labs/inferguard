#!/usr/bin/env python3
"""Print exact Modal commands for LMCache MP packet gates."""

from __future__ import annotations

PACKET_COMMANDS = {
    "A": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_a",
    "B": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b",
    "C": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_c",
    "D": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_d",
    "E": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_e",
    "F": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_f",
    "G": "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_g",
}


def packet_commands() -> dict[str, str]:
    return dict(PACKET_COMMANDS)


def main() -> None:
    for packet, command in PACKET_COMMANDS.items():
        print(f"Packet {packet}: {command}")


if __name__ == "__main__":
    main()
