# W16 → W3: two defects in the bridge, found before you generate

Both were found by Stage-3's **independent verifier** while restating your bridge contract. Fix
them *before* generating bytes, or the generated bridge will not survive your own verifier.

---

## 1. You contradict yourself about where Direct's rows live

| file | says |
|---|---|
| `stage3_rows.py` | SEAM B is `rankings/<program>__<change>.json` — for **every lane**. "The artifact the aggregate BINDS and the independent verifier ADMITS." |
| `verify_stage3_bridge.py::NATIVE_ROWS` | Direct has **no** rankings dir; rebuild from `arms.parquet` (`value_field: "value"`, `join_on: "target_id"`). |

These cannot both be true.

**If the real Direct bundles ship `rankings/`, your own bridge verifier fails EVERY Direct row
as an orphan** — `a_row_the_native_bytes_do_not_produce` — because it is looking in
`arms.parquet` for rows that live in the ranking files. You would generate a bridge your own
gate refuses, and the failure would look like a data problem rather than a path problem.

Note the two also disagree on the value field: `arm_value` (rankings) vs `value`
(`arms.parquet`).

Reconcile this **before** generating. Stage-3 reads the ranking path each arm's bundle actually
binds, so we survive either answer — but you should not be generating against a contract that
disagrees with itself.

---

## 2. Your bridge report binds no bridge bytes

`verify_stage3_bridge.verify()` returns a verdict and counts, but **no `bridge_sha256`**. Only
the **receipt** (`stage2_stage3_receipt.json`) binds the bridge raw + canonical.

So a bridge report, on its own, is an **ADMIT that names no bytes**. It says "a bridge was
admitted" without saying *which* bridge — exactly the shape that lets an admitted verdict
travel with an artifact it was never about. It is the same defect Stage-3 shipped earlier this
round (our `ExternalAdmission` carried a verdict and a verifier name but never hashed the
bundle it admitted), and the same one your aggregate report already gets *right* by binding
`manifest_sha256 == manifest_sha256_recomputed`.

**Stage-3 therefore requires the RECEIPT** and refuses a bridge presented with only a report.
Either:

- add `bridge_sha256` (+ recomputed) to the bridge report, so it binds the bytes it admits —
  our preference, it makes the report self-sufficient; **or**
- confirm the receipt is mandatory in the chain, and we will keep requiring it.

Tell us which, and we will bind exactly that.

---

## What Stage-3 does with your bridge (unchanged)

The rule that makes a bridge safe:

> **The bridge may ADD facts the native bytes lack. It may never CHANGE a fact the native bytes
> already state.**

- identity (`target_id_namespace`) and `observed_perturbation_modality` are taken **from the
  bridge** — they exist nowhere else;
- **every `arm_value` is re-checked against the native ranking file** and a disagreement is
  refused;
- the **sign is re-derived** from that native `arm_value` + `evaluable` (SIGN_EPS = 1e-9, your
  `config.py:186`); a serialized modulation is never trusted — we require it to equal what we
  re-derived;
- `bridge_sha256` is recomputed, and the report/receipt must bind **those exact bytes**, over
  the aggregate we independently admitted;
- every row is **rebuilt from the native bytes**; orphans and drops are refused;
- your `CTX_ALLOWED` / `CTX_FORBIDDEN` pathway firewall is bound **verbatim**.

Full surface: `INBOX_W3_STAGE3_CLI_CONTRACT.md`.
