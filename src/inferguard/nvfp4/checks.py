"""NVFP4 KV-cache qualification checks.

Three operator checks against a running vLLM (OpenAI-compatible) endpoint:

  run_sm120_compat   - is the serving GPU on the SM120 FA2 NVFP4-KV path?
  run_kv_capacity    - NVFP4 vs fp8 KV pool ratio (parsed from /metrics or passed in)
  run_nvfp4_quality  - PPL / divergence / retrieval / decode-speed battery vs an fp8 reference

The nvfp4-quality battery is ported from the Touchdown qualification suite
(nvfp4_qualify.py in OCWC22/vllm-nvfp4-kv-sm120). It uses the OpenAI
/v1/completions and /tokenize routes only; no telemetry, no calls outside the
endpoints passed in.
"""

from __future__ import annotations

import math
import re
import statistics
import time
from typing import Any

import httpx

from .types import (
    CLAIM_INFERRED,
    CLAIM_MEASURED,
    CLAIM_NOT_PROVEN,
    CheckResult,
    NVFp4Qualification,
    NVFp4Verdict,
    QualThresholds,
)

# SM120 = RTX PRO 6000 / RTX 5090 (GB202). Compute capability 12.0 / 12.1.
SM120_CAPABILITIES = {(12, 0), (12, 1)}
# SM100 = datacenter Blackwell (B200): native trtllm-gen cubins, not this FA2 path.
SM100_MAJOR = 10

_DEFAULT_TIMEOUT = 600.0


# ---------------------------------------------------------------------------
# HTTP helpers (sync httpx; client is injectable for tests via MockTransport)
# ---------------------------------------------------------------------------

def _client(client: httpx.Client | None, timeout: float) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=timeout), True


def _post(http: httpx.Client, base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = http.post(base + path, json=payload)
    resp.raise_for_status()
    return resp.json()


def _ntok(http: httpx.Client, base: str, model: str, text: str) -> int:
    d = _post(http, base, "/tokenize", {"model": model, "prompt": text})
    return int(d["count"])


# ---------------------------------------------------------------------------
# Check 1: sm120-compat
# ---------------------------------------------------------------------------

def detect_local_capability() -> tuple[int, int] | None:
    """Best-effort local CUDA compute-capability probe. None if torch/GPU absent."""
    try:  # pragma: no cover - depends on host GPU
        import torch

        if not torch.cuda.is_available():
            return None
        return tuple(torch.cuda.get_device_capability())  # type: ignore[return-value]
    except Exception:
        return None


def run_sm120_compat(
    *,
    model: str = "",
    endpoint: str = "",
    capability: tuple[int, int] | None = None,
) -> NVFp4Qualification:
    """Decide whether the SM120 FA2 NVFP4-KV path applies to this GPU.

    `capability` may be passed explicitly (e.g. parsed from nvidia-smi or `--cc`);
    otherwise a local torch probe is attempted. Whether the FA2 backend and B2
    de-swizzle are actually active cannot be confirmed over HTTP, so that part is
    reported as not_proven.
    """
    cap = capability or detect_local_capability()
    results: list[CheckResult] = []

    if cap is None:
        results.append(
            CheckResult(
                name="GPU compute capability",
                passed=False,
                value="unknown",
                threshold="12.0 / 12.1",
                unit="cc",
                detail="No capability provided and no local CUDA device detected. Pass --cc.",
                claim_status=CLAIM_NOT_PROVEN,
            )
        )
        return NVFp4Qualification(
            check="sm120-compat",
            model=model,
            endpoint=endpoint,
            verdict=NVFp4Verdict.NEEDS_REVIEW,
            confidence=0.0,
            claim_status=CLAIM_NOT_PROVEN,
            results=results,
            reasoning="Compute capability could not be determined.",
            recommended_next="Re-run with --cc <major.minor> on the serving host.",
            raw={"capability": None},
        )

    major, minor = cap
    cc_str = f"{major}.{minor}"
    is_sm120 = (major, minor) in SM120_CAPABILITIES
    is_sm100 = major == SM100_MAJOR

    results.append(
        CheckResult(
            name="GPU compute capability",
            passed=is_sm120,
            value=cc_str,
            threshold="12.0 / 12.1",
            unit="cc",
            detail=f"Detected sm_{major}{minor} (cc {cc_str}).",
            claim_status=CLAIM_MEASURED,
        )
    )
    # FA2 backend + B2 de-swizzle activation is a server-config fact, not visible over HTTP.
    results.append(
        CheckResult(
            name="FA2 NVFP4-KV backend active",
            passed=is_sm120,
            value="not_confirmable_over_http",
            threshold="backend=fa2",
            unit="flag",
            detail="Confirm in server logs: backend forced to 'fa2', B2 V-SF de-swizzle on.",
            claim_status=CLAIM_NOT_PROVEN,
        )
    )

    if is_sm120:
        verdict = NVFp4Verdict.QUALIFIED
        reasoning = "SM120 GPU. The FlashInfer FA2 NVFP4-KV software path applies."
        nxt = "Run `inferguard nvfp4 kv-capacity` then `nvfp4-quality` before deploying."
        claim = CLAIM_MEASURED
        conf = 0.9
    elif is_sm100:
        verdict = NVFp4Verdict.NEEDS_REVIEW
        reasoning = "SM100 (B200). Use native trtllm-gen NVFP4-KV cubins, not this FA2 path."
        nxt = "Use the datacenter trtllm-gen path; this gate is SM120-only."
        claim = CLAIM_MEASURED
        conf = 0.8
    else:
        verdict = NVFp4Verdict.NOT_QUALIFIED
        reasoning = f"cc {cc_str} is neither SM120 nor SM100. NVFP4 KV path does not apply."
        nxt = "Use fp8 KV cache (Hopper) or the engine-native path for this arch."
        claim = CLAIM_MEASURED
        conf = 0.8

    return NVFp4Qualification(
        check="sm120-compat",
        model=model,
        endpoint=endpoint,
        verdict=verdict,
        confidence=conf,
        claim_status=claim,
        results=results,
        reasoning=reasoning,
        recommended_next=nxt,
        raw={"capability": [major, minor]},
    )


# ---------------------------------------------------------------------------
# Check 2: kv-capacity
# ---------------------------------------------------------------------------

_METRIC_NUM_BLOCKS = re.compile(r"^vllm:num_gpu_blocks(?:\{[^}]*\})?\s+([0-9.eE+]+)", re.MULTILINE)
_METRIC_BLOCK_SIZE = re.compile(r"block_size=\"?([0-9]+)\"?")


def parse_kv_tokens_from_metrics(metrics_text: str) -> int | None:
    """Parse KV pool token capacity from a vLLM Prometheus /metrics body.

    tokens = num_gpu_blocks * block_size. Returns None if the gauges are absent.
    """
    m = _METRIC_NUM_BLOCKS.search(metrics_text)
    if not m:
        return None
    blocks = int(float(m.group(1)))
    bs = _METRIC_BLOCK_SIZE.search(metrics_text)
    block_size = int(bs.group(1)) if bs else 16
    return blocks * block_size


def run_kv_capacity(
    *,
    model: str = "",
    endpoint: str = "",
    nvfp4_tokens: int | None = None,
    fp8_tokens: int | None = None,
    thresholds: QualThresholds | None = None,
    client: httpx.Client | None = None,
    metrics_path: str = "/metrics",
    timeout: float = 60.0,
) -> NVFp4Qualification:
    """Report NVFP4 KV pool size and the ratio vs an fp8 baseline.

    Token counts may be passed directly or parsed from the endpoint's /metrics.
    """
    thr = thresholds or QualThresholds()
    raw: dict[str, Any] = {}

    if nvfp4_tokens is None and endpoint:
        http, owns = _client(client, timeout)
        try:
            resp = http.get(endpoint + metrics_path)
            resp.raise_for_status()
            nvfp4_tokens = parse_kv_tokens_from_metrics(resp.text)
            raw["metrics_parsed"] = nvfp4_tokens is not None
        finally:
            if owns:
                http.close()

    results: list[CheckResult] = []
    raw["nvfp4_tokens"] = nvfp4_tokens
    raw["fp8_tokens"] = fp8_tokens

    if nvfp4_tokens is None:
        results.append(
            CheckResult(
                name="KV pool tokens (NVFP4)",
                passed=False,
                value="unknown",
                threshold="-",
                unit="tokens",
                detail="Could not parse num_gpu_blocks from /metrics. Pass --nvfp4-tokens.",
                claim_status=CLAIM_NOT_PROVEN,
            )
        )
        return NVFp4Qualification(
            check="kv-capacity",
            model=model,
            endpoint=endpoint,
            verdict=NVFp4Verdict.NEEDS_REVIEW,
            confidence=0.0,
            claim_status=CLAIM_NOT_PROVEN,
            results=results,
            reasoning="NVFP4 KV pool size unknown.",
            recommended_next="Provide --nvfp4-tokens or expose vllm:num_gpu_blocks on /metrics.",
            raw=raw,
        )

    results.append(
        CheckResult(
            name="KV pool tokens (NVFP4)",
            passed=True,
            value=nvfp4_tokens,
            threshold="-",
            unit="tokens",
            detail=f"NVFP4 KV pool: {nvfp4_tokens:,} tokens.",
            claim_status=CLAIM_MEASURED,
        )
    )

    if fp8_tokens:
        ratio = nvfp4_tokens / fp8_tokens
        passed = ratio >= thr.min_capacity_ratio
        results.append(
            CheckResult(
                name="Capacity gain vs fp8",
                passed=passed,
                value=round(ratio, 3),
                threshold=thr.min_capacity_ratio,
                unit="ratio",
                detail=f"NVFP4 {nvfp4_tokens:,} vs fp8 {fp8_tokens:,} tokens ({ratio:.2f}x).",
                claim_status=CLAIM_MEASURED,
            )
        )
        verdict = NVFp4Verdict.QUALIFIED if passed else NVFp4Verdict.NOT_QUALIFIED
        reasoning = (
            f"NVFP4 buys {ratio:.2f}x the KV pool. "
            + ("Above" if passed else "Below")
            + f" the {thr.min_capacity_ratio}x worth-it threshold."
        )
        nxt = (
            "Proceed to `nvfp4-quality` to confirm the model tolerates NVFP4."
            if passed
            else "Capacity gain too small to justify the quality risk; stay on fp8."
        )
        return NVFp4Qualification(
            check="kv-capacity",
            model=model,
            endpoint=endpoint,
            verdict=verdict,
            confidence=0.85,
            claim_status=CLAIM_MEASURED,
            results=results,
            reasoning=reasoning,
            recommended_next=nxt,
            raw=raw,
        )

    # No fp8 baseline: report the theoretical ceiling only.
    return NVFp4Qualification(
        check="kv-capacity",
        model=model,
        endpoint=endpoint,
        verdict=NVFp4Verdict.NEEDS_REVIEW,
        confidence=0.4,
        claim_status=CLAIM_INFERRED,
        results=results,
        reasoning="No fp8 baseline provided; NVFP4's byte ceiling vs fp8 is ~1.78x.",
        recommended_next="Pass --fp8-tokens (fp8 server's KV pool) to measure the real ratio.",
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Check 3: nvfp4-quality (PPL / divergence / retrieval / speed)
# ---------------------------------------------------------------------------

_PPL_PARAGRAPHS = [
    "The development of artificial intelligence has progressed through several distinct phases. "
    "Early systems relied on hand-coded rules and expert knowledge, which limited their flexibility.",
    "Modern neural networks process information through layers of interconnected nodes, each "
    "performing simple mathematical operations composed into hierarchical representations.",
    "The transformer architecture replaced recurrent connections with self-attention, enabling "
    "efficient parallel processing and better capture of long-range dependencies in text.",
    "Large language models show emergent capabilities that scale with model size and training data, "
    "including in-context learning, chain-of-thought reasoning, and instruction following.",
    "Inference optimization matters as models grow. The KV cache, storing key-value pairs from prior "
    "attention steps, is often the primary memory bottleneck during autoregressive generation.",
]

_DIVERGENCE_PROMPTS = [
    "Compute 27 * 34 + 19. Show your steps, then give the final number.",
    "Write a Python function is_palindrome(s) that ignores case and spaces.",
    "If all bloops are razzies and all razzies are lazzies, are all bloops lazzies? Why?",
    "What is the chemical symbol for gold, and what group is it in?",
    "A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?",
    "Differentiate f(x) = x^3 - 2x with respect to x.",
    "Explain what a hash table is and its average lookup complexity.",
    "What causes the seasons on Earth? Answer in two sentences.",
]


def _extract_token_nlls(resp: dict[str, Any]) -> list[float]:
    ch = resp["choices"][0]
    pl = ch.get("prompt_logprobs")
    nlls: list[float] = []
    if pl:
        for entry in pl:
            if not entry:
                continue
            v = list(entry.values())[0]
            lp = v["logprob"] if isinstance(v, dict) else float(v)
            if lp is not None and math.isfinite(lp):
                nlls.append(-lp)
        return nlls
    lg = ch.get("logprobs") or {}
    for lp in lg.get("token_logprobs") or []:
        if lp is not None and math.isfinite(lp):
            nlls.append(-lp)
    return nlls


def _build_ppl_prompt(http: httpx.Client, base: str, model: str, target_tokens: int) -> str:
    text = ""
    while True:
        for p in _PPL_PARAGRAPHS:
            text += p + "\n\n"
        try:
            if _ntok(http, base, model, text) >= target_tokens:
                break
        except Exception:
            if len(text) >= target_tokens * 4:
                break
    return text


def measure_ppl(
    http: httpx.Client, base: str, model: str, ctx_lengths: tuple[int, ...], warmup: int = 256
) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for ctx in ctx_lengths:
        try:
            prompt = _build_ppl_prompt(http, base, model, ctx)
            resp = _post(
                http,
                base,
                "/v1/completions",
                {
                    "model": model,
                    "prompt": prompt,
                    "max_tokens": 0,
                    "echo": True,
                    "prompt_logprobs": 0,
                    "temperature": 0,
                },
            )
            nlls = _extract_token_nlls(resp)
            if len(nlls) <= warmup + 4:
                out[ctx] = {"mean_nll": None, "error": "too few tokens"}
                continue
            body = nlls[warmup:]
            mean_nll = sum(body) / len(body)
            out[ctx] = {"mean_nll": round(mean_nll, 5), "ppl": round(math.exp(mean_nll), 4), "n_tokens": len(body)}
        except Exception as exc:  # noqa: BLE001 - record and continue
            out[ctx] = {"mean_nll": None, "error": str(exc)[:200]}
    return out


def measure_divergence_tokens(http: httpx.Client, base: str, model: str, max_tokens: int = 256) -> list[dict[str, Any]]:
    res: list[dict[str, Any]] = []
    for i, prompt in enumerate(_DIVERGENCE_PROMPTS):
        try:
            d = _post(
                http,
                base,
                "/v1/completions",
                {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0, "logprobs": 1, "stream": False},
            )
            tokens = (d["choices"][0].get("logprobs") or {}).get("tokens") or []
            res.append({"id": i, "tokens": tokens, "n": len(tokens)})
        except Exception as exc:  # noqa: BLE001
            res.append({"id": i, "tokens": [], "error": str(exc)[:200]})
    return res


def compute_divergence(fp8_results: list[dict[str, Any]], nvfp4_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    first_divs: list[int] = []
    agrees: list[float] = []
    n = 0
    for fp8, nvfp4 in zip(fp8_results, nvfp4_results, strict=False):
        a, b = fp8.get("tokens", []), nvfp4.get("tokens", [])
        length = min(len(a), len(b))
        if length == 0:
            continue
        n += 1
        fd = length
        for j in range(length):
            if a[j] != b[j]:
                fd = j
                break
        first_divs.append(fd)
        agrees.append(sum(1 for j in range(length) if a[j] == b[j]) / length)
    if not first_divs:
        return None
    return {
        "n": n,
        "median_first_div": int(statistics.median(first_divs)),
        "mean_agreement": round(sum(agrees) / len(agrees), 4),
    }


def measure_retrieval(http: httpx.Client, base: str, model: str, trials: int = 8) -> dict[str, Any]:
    import random

    rng = random.Random(42)
    results: list[dict[str, Any]] = []
    for trial in range(trials):
        code = str(rng.randint(10000, 99999))
        key = rng.choice(["harbor", "lantern", "meadow", "cobalt", "thistle"])
        filler = "The quick brown fox jumps over the lazy dog. " * 200
        needle = f"The secret passcode for {key} is {code}."
        sentences = filler.split(". ")
        sentences.insert(rng.randint(50, 150), needle)
        context = ". ".join(sentences)
        prompt = (
            f"Read the following text carefully, then answer the question.\n\n{context}\n\n"
            f"Question: What is the secret passcode for {key}? Reply with only the number."
        )
        try:
            d = _post(http, base, "/v1/completions", {"model": model, "prompt": prompt, "max_tokens": 32, "temperature": 0})
            answer = d["choices"][0].get("text", "")
            results.append({"trial": trial, "hit": code in answer, "code": code})
        except Exception as exc:  # noqa: BLE001
            results.append({"trial": trial, "hit": False, "error": str(exc)[:200]})
    acc = sum(1 for r in results if r.get("hit")) / len(results)
    return {"accuracy": round(acc, 4), "results": results}


def measure_decode_speed(http: httpx.Client, base: str, model: str, n_tokens: int = 256, n_runs: int = 3) -> dict[str, Any]:
    prompt = "Write a detailed essay about the history of computing from the earliest mechanical devices."
    speeds: list[float] = []
    for _ in range(n_runs):
        try:
            t0 = time.monotonic()
            d = _post(http, base, "/v1/completions", {"model": model, "prompt": prompt, "max_tokens": n_tokens, "temperature": 0.7})
            dt = time.monotonic() - t0
            ctok = d.get("usage", {}).get("completion_tokens", n_tokens)
            if dt > 0:
                speeds.append(ctok / dt)
        except Exception:  # noqa: BLE001
            continue
    if not speeds:
        return {"tok_per_sec": None, "error": "all runs failed"}
    return {"tok_per_sec": round(sum(speeds) / len(speeds), 1), "runs": len(speeds)}


def qualify_quality(
    *,
    nvfp4_ppl: dict[int, dict[str, Any]],
    fp8_ppl: dict[int, dict[str, Any]],
    divergence: dict[str, Any] | None,
    nvfp4_retrieval: dict[str, Any] | None,
    fp8_retrieval: dict[str, Any] | None,
    nvfp4_speed: dict[str, Any] | None,
    fp8_speed: dict[str, Any] | None,
    thresholds: QualThresholds,
) -> list[CheckResult]:
    """Apply the six thresholds to raw measurements (pure, fully unit-testable)."""
    results: list[CheckResult] = []

    worst_delta = 0.0
    have_ppl = False
    for ctx in thresholds.ppl_ctx_lengths:
        f = fp8_ppl.get(ctx, {}).get("mean_nll")
        n = nvfp4_ppl.get(ctx, {}).get("mean_nll")
        if f is not None and n is not None:
            have_ppl = True
            worst_delta = max(worst_delta, n - f)
    if have_ppl:
        results.append(
            CheckResult(
                name="PPL regression (worst delta nats)",
                passed=worst_delta < thresholds.max_ppl_delta_nats,
                value=round(worst_delta, 5),
                threshold=thresholds.max_ppl_delta_nats,
                unit="nats",
                detail=f"Worst PPL delta across context lengths: {worst_delta:+.5f} nats.",
            )
        )

    if divergence:
        med = divergence.get("median_first_div", 0)
        results.append(
            CheckResult(
                name="Greedy divergence",
                passed=med >= thresholds.min_first_div_tokens,
                value=med,
                threshold=thresholds.min_first_div_tokens,
                unit="tokens",
                detail=f"Median first divergence at token {med}.",
            )
        )

    if fp8_retrieval and nvfp4_retrieval:
        fa = fp8_retrieval.get("accuracy", 0.0)
        na = nvfp4_retrieval.get("accuracy", 0.0)
        ratio = na / fa if fa > 0 else 0.0
        results.append(
            CheckResult(
                name="Retrieval accuracy",
                passed=ratio >= thresholds.min_ruler_ratio,
                value=round(ratio, 4),
                threshold=thresholds.min_ruler_ratio,
                unit="ratio",
                detail=f"NVFP4 {na:.3f} vs fp8 {fa:.3f} ({ratio:.1%}).",
            )
        )

    ft = (fp8_speed or {}).get("tok_per_sec")
    nt = (nvfp4_speed or {}).get("tok_per_sec")
    if ft and nt:
        sr = nt / ft
        results.append(
            CheckResult(
                name="Decode speed",
                passed=sr >= thresholds.min_speed_ratio,
                value=round(sr, 4),
                threshold=thresholds.min_speed_ratio,
                unit="ratio",
                detail=f"NVFP4 {nt:.1f} vs fp8 {ft:.1f} tok/s ({sr:.1%}).",
            )
        )
    return results


def _verdict_from_results(results: list[CheckResult]) -> tuple[NVFp4Verdict, str, float, str]:
    if not results:
        return NVFp4Verdict.NEEDS_REVIEW, CLAIM_NOT_PROVEN, 0.0, "No checks produced a measurement."
    passed = all(r.passed for r in results)
    if passed:
        return (
            NVFp4Verdict.QUALIFIED,
            CLAIM_MEASURED,
            0.9,
            "All measured criteria within threshold. Deploy with --kv-cache-dtype nvfp4 and monitor.",
        )
    failed = [r.name for r in results if not r.passed]
    return (
        NVFp4Verdict.NOT_QUALIFIED,
        CLAIM_MEASURED,
        0.85,
        f"Failed: {', '.join(failed)}. Stay on fp8, or try mixed K=fp8 / V=nvfp4.",
    )


def run_nvfp4_quality(
    *,
    model: str,
    nvfp4_endpoint: str,
    fp8_endpoint: str | None = None,
    thresholds: QualThresholds | None = None,
    client: httpx.Client | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> NVFp4Qualification:
    """Run the quality battery against the NVFP4 endpoint, comparing to an fp8 reference."""
    thr = thresholds or QualThresholds()
    http, owns = _client(client, timeout)
    try:
        nvfp4_ppl = measure_ppl(http, nvfp4_endpoint, model, thr.ppl_ctx_lengths)
        nvfp4_div = measure_divergence_tokens(http, nvfp4_endpoint, model)
        nvfp4_ret = measure_retrieval(http, nvfp4_endpoint, model)
        nvfp4_spd = measure_decode_speed(http, nvfp4_endpoint, model)

        fp8_ppl: dict[int, dict[str, Any]] = {}
        fp8_div: list[dict[str, Any]] = []
        fp8_ret = None
        fp8_spd = None
        if fp8_endpoint:
            fp8_ppl = measure_ppl(http, fp8_endpoint, model, thr.ppl_ctx_lengths)
            fp8_div = measure_divergence_tokens(http, fp8_endpoint, model)
            fp8_ret = measure_retrieval(http, fp8_endpoint, model)
            fp8_spd = measure_decode_speed(http, fp8_endpoint, model)
    finally:
        if owns:
            http.close()

    divergence = compute_divergence(fp8_div, nvfp4_div) if fp8_div else None
    results = qualify_quality(
        nvfp4_ppl=nvfp4_ppl,
        fp8_ppl=fp8_ppl,
        divergence=divergence,
        nvfp4_retrieval=nvfp4_ret,
        fp8_retrieval=fp8_ret,
        nvfp4_speed=nvfp4_spd,
        fp8_speed=fp8_spd,
        thresholds=thr,
    )
    verdict, claim, conf, reasoning = _verdict_from_results(results)
    return NVFp4Qualification(
        check="nvfp4-quality",
        model=model,
        endpoint=nvfp4_endpoint,
        verdict=verdict,
        confidence=conf,
        claim_status=claim,
        results=results,
        reasoning=reasoning,
        recommended_next="Re-run under your production workload shape before committing.",
        raw={
            "nvfp4_ppl": {str(k): v for k, v in nvfp4_ppl.items()},
            "fp8_ppl": {str(k): v for k, v in fp8_ppl.items()},
            "divergence": divergence,
            "nvfp4_retrieval": nvfp4_ret,
            "fp8_retrieval": fp8_ret,
            "nvfp4_speed": nvfp4_spd,
            "fp8_speed": fp8_spd,
            "thresholds": thr.to_dict(),
        },
    )
