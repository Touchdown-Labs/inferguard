---
title: Install the CLI
description: Install the InferGuard command line via pip. Python 3.11+ required.
---

InferGuard is published on PyPI as `inferguard` and is Apache 2.0.

## Requirements

- Python 3.11 or newer
- A POSIX shell (Linux or macOS recommended for full feature coverage)
- For GPU telemetry features, an NVIDIA driver and DCGM if you want
  the engine-and-GPU fused timeline

## From PyPI

```bash
pip install inferguard
```

The latest release is on [PyPI](https://pypi.org/project/inferguard/).

Verify:

```bash
inferguard --version
inferguard --help
```

## From source

```bash
git clone https://github.com/Touchdown-Labs/inferguard.git
cd inferguard
pip install -e .
```

Or run without installing:

```bash
PYTHONPATH=src python3 -m inferguard.cli --help
```

## Optional dependencies

Some features require extras. Install them on demand:

```bash
pip install 'inferguard[harness]'    # harness orchestrator
pip install 'inferguard[mcp]'        # MCP server
pip install 'inferguard[plot]'       # plotting support
pip install 'inferguard[docs]'       # local documentation build
```

## Next

- [Run the evidence loop](/inferguard/getting-started/quick-start/)
- [Run the harness](/inferguard/guides/harness/)
- [Use the command map](/inferguard/reference/cli/)
