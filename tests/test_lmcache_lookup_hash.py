from __future__ import annotations

import json
from pathlib import Path

from inferguard.lmcache_lookup_hash import parse_lmcache_lookup_hash_jsonl


def test_lmcache_lookup_hash_jsonl_redacts_hashes_and_preserves_shape(tmp_path: Path) -> None:
    lookup_hashes = tmp_path / "lookup_hashes_0001.jsonl"
    lookup_hashes.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-07T00:00:00Z",
                        "request_id": "req-a",
                        "model_name": "meta-llama/Llama-3.1-8B",
                        "chunk_size": 256,
                        "seq_len": 512,
                        "dtypes": ["float16"],
                        "shapes": [[2, 16, 128]],
                        "chunk_hashes": ["raw-secret-hash-a", "raw-secret-hash-b"],
                        "config": {
                            "--lookup-hash-log-dir": "/var/log/lmcache",
                            "lookup_hash_rotation_interval": "60s",
                            "lookup_hash_max_size": 1048576,
                            "lookup_hash_max_files": 5,
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-07T00:00:01Z",
                        "request_id": "req-b",
                        "model_name": "meta-llama/Llama-3.1-8B",
                        "chunk_size": 256,
                        "seq_len": 768,
                        "dtypes": ["float16"],
                        "shapes": [[3, 16, 128]],
                        "chunk_hashes": ["raw-secret-hash-c"],
                    }
                ),
                "not-json",
            ]
        ),
        encoding="utf-8",
    )

    evidence = parse_lmcache_lookup_hash_jsonl(lookup_hashes)

    assert evidence["claim_status"] == "measured"
    assert evidence["row_count"] == 2
    assert evidence["malformed_rows"] == 1
    assert evidence["models"] == ["meta-llama/Llama-3.1-8B"]
    assert evidence["chunk_sizes"] == [256]
    assert evidence["seq_len"]["min"] == 512
    assert evidence["seq_len"]["max"] == 768
    assert evidence["chunk_hash_count"]["total"] == 3
    assert evidence["rows"][0]["chunk_hashes"] == {"redacted": True, "count": 2}
    assert "raw-secret-hash-a" not in json.dumps(evidence)
    assert evidence["rows"][0]["shapes"] == [[2, 16, 128]]
    assert evidence["config_evidence"]["lookup_hash_log_dir"] == "/var/log/lmcache"
    assert evidence["config_evidence"]["lookup_hash_max_files"] == 5
