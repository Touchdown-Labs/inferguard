#!/usr/bin/env python3
"""Print exact Modal commands for LMCache embedded/advanced packet gates."""

from __future__ import annotations

PACKET_COMMANDS = {
    "H1": "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm",
    "H2": "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h2_sglang_embedded",
    "H3-cacheblend": "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend",
    "H3-p2p": "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_p2p",
    "H3-pd": "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_pd",
}


def packet_commands() -> dict[str, str]:
    return dict(PACKET_COMMANDS)


def main() -> None:
    for packet, command in PACKET_COMMANDS.items():
        print(f"Packet {packet}: {command}")


if __name__ == "__main__":
    main()

