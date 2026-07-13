"""THE FOUR RECURSIVE FIREWALLS. Over the WHOLE artifact, at any depth, keys AND values.

1. INFERENCE   p / q / FDR / significance. This estimator has NO calibrated null, so a number
               that merely LOOKS like significance would be READ as significance.
2. OBJECTIVE   combined / balanced / weighted / composite / objective / score. There is no
               combined arm objective, and a target opposing one arm must never be able to
               buy rank with a large value on the other.
3. JOIN-TIME   pair / Pareto / concordance / joint / role / pole / batch — every one a
               COMPARISON-SCOPED property. A reusable arm carrying one would be a
               pair-shaped artifact wearing a reusable arm's key.
4. MACHINE     absolute paths, hostnames, private addresses. Not content: an artifact whose
               bytes contain the machine that made them cannot be content-addressed and leaks
               a filesystem into a published record.

TOKEN rules, not substring rules. A substring rule for "p" would refuse every key containing
the letter, and a firewall that refuses everything is one somebody turns off:
``n_panel_surviving`` is not a p-value, and it survives.

Hosts are detected STRUCTURALLY, not by name. This module names no machine — a verifier whose
source had to list the lab's hosts in order to reject them would be publishing the very thing
it exists to keep out of an artifact.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# The banned tokens. A key is banned if ANY of its snake_case tokens is one of these.
# --------------------------------------------------------------------------- #
INFERENCE_TOKENS = frozenset({
    "p", "q", "pval", "pvals", "pvalue", "qval", "qvals", "qvalue", "padj", "qadj",
    "fdr", "bonferroni", "significance", "signif", "pcorrected", "qcorrected",
})
OBJECTIVE_TOKENS = frozenset({
    "combined", "balanced", "weighted", "composite", "objective", "score", "scores",
    "scored", "aggregate", "overall",
})
JOIN_TIME_TOKENS = frozenset({
    "pair", "pairs", "paired", "pareto", "concordance", "concordant", "discordant",
    "joint", "jointly", "role", "roles", "pole", "poles",
    "batch", "batches", "confounded", "confound",
})
BANNED_TOKENS = INFERENCE_TOKENS | OBJECTIVE_TOKENS | JOIN_TIME_TOKENS

# ...and the join-time IDENTIFIERS, banned by EXACT NAME rather than by token.
#
# The token rule cannot be used here. ``selection_release`` is the Stage-1 RELEASE this
# bundle bound — a required, legitimate provenance field — while ``selection_id`` names a
# specific A/B selection and is exactly the pair-scoped identifier a reusable arm may not
# carry. Banning the token ``selection`` would refuse both, and a firewall that refuses the
# binding it is supposed to require is one somebody turns off.
BANNED_EXACT_NAMES = frozenset({
    "selection_id", "selection_key", "question_id", "question_key", "pair_id", "pair_key",
})

# THERE IS NO ``role`` EXEMPTION. ``run_binding`` is a FIXED EXACT-KEY object, so THE FIELD
# NAME IS THE ROLE: no generic ``role`` key, no list mini-language, and therefore no
# role-shaped hole for a selection role to walk through. A ``role`` key at any depth, with
# any value, is refused.
# A whole-key substring rule for the two role NAMES, which are not snake_case tokens.
BANNED_SUBSTRING_RE = re.compile(r"away_from_a|toward_b", re.IGNORECASE)

# Exempt by EXACT SPELLING.
#
#   qc_ontarget_significant     the UPSTREAM QC gate's own outcome flag, under its own name.
#                               A gate outcome, not a p-value.
#   ordered_pairs / n_ordered_pairs / expected_n_ordered_pairs
#                               the ORDERED CONDITION pairs — which ARE the temporal
#                               topology, not a pair-scoped selection. The thing the firewall
#                               exists to keep out is an A/B PROGRAM pair or a selection id
#                               (``pair_id``, ``selection_id``), and those are still refused
#                               by exact name. Refusing the release's own condition-pair
#                               enumeration would be refusing the lane's subject matter.
EXACT_SPELLING_EXEMPTIONS = frozenset({
    "qc_ontarget_significant",
    "from_qc_ontarget_significant",
    "to_qc_ontarget_significant",
    "ordered_pairs",
    "n_ordered_pairs",
    "expected_n_ordered_pairs",
})

# Exempt ONLY while the declaration still says what it is exempted for saying.
NEGATIVE_DECLARATIONS: dict[str, Any] = {
    "bundle_carries_role_or_pole": False,
    "bundle_is_pair_agnostic": True,
}

# --------------------------------------------------------------------------- #
# Firewall 4: the machine. Keys that name a machine, and values that ARE one.
# --------------------------------------------------------------------------- #
MACHINE_KEY_RE = re.compile(
    r"(^|_)(path_abs|abs_path|abspath|realpath|fullpath|out_dir|outdir|cwd|host|hostname|"
    r"machine|node_name|user|username|homedir|home_dir)(_|$)|_on_disk$",
    re.IGNORECASE)

# An absolute POSIX path (a leading '/' followed by at least one more segment) or a Windows
# drive path. Prose like "marker/control decomposition" has no leading slash and survives;
# an absolute path does not.
ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s'\"(=,;])/[^\s'\"]*/|^[A-Za-z]:[\\/]|[\s'\"(=,;][A-Za-z]:[\\/]")
# A '..' PATH SEGMENT. Slash-delimited, so "dense 1..n over the ranked population" is not
# a traversal and is not refused.
PATH_TRAVERSAL_RE = re.compile(r"(^|/)\.\.(/|$)")

# HOSTS ARE DETECTED STRUCTURALLY, NOT BY NAME. This module names no machine: a verifier
# whose source had to list the lab's hosts in order to reject them would be publishing the
# very thing it exists to keep out of an artifact. So the rules are shapes —
#   * a URI with an authority   (``file://…``, ``ssh://…``, ``https://…``)
#   * an ssh-style target       (``user@host:/path``)
#   * a private/loopback address
#   * ``localhost`` or any ``*.local`` name
# — and a deployment that wants its own hosts refused BY NAME passes them in as a denylist.
URI_AUTHORITY_RE = re.compile(r"\b[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
SSH_TARGET_RE = re.compile(r"\b[\w.\-]+@[\w.\-]+:")
LOCAL_HOST_RE = re.compile(r"\blocalhost\b|\b[a-z0-9][a-z0-9\-]*\.local\b", re.IGNORECASE)
PRIVATE_ADDRESS_RE = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")


def tokens(key: str) -> list[str]:
    """The snake_case / camelCase tokens of a key, lowercased."""
    return [t for t in re.split(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])", str(key)) if t]


def _key_is_banned(key: str, value: Any, path: str = "") -> bool:
    k = str(key)
    if k in EXACT_SPELLING_EXEMPTIONS:
        return False
    if k in NEGATIVE_DECLARATIONS:
        # `is` on the literal, so a truthy 1 or the string "false" cannot pose as the
        # prohibition and inherit its exemption.
        return value is not NEGATIVE_DECLARATIONS[k]
    if k in BANNED_EXACT_NAMES or BANNED_SUBSTRING_RE.search(k):
        return True
    return any(t.lower() in BANNED_TOKENS for t in tokens(k))


def banned_keys(obj: Any, path: str = "") -> list[str]:
    """Every p/q/FDR, combined-objective, pair/Pareto/concordance/joint, role/pole or
    batch KEY, at any depth. The dotted path is returned so a reader can find it."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if _key_is_banned(key, value, here):
                hits.append(here)
            hits.extend(banned_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(banned_keys(value, f"{path}[{i}]"))
    return hits


def _value_is_machine(value: Any, host_denylist: Iterable[str] = ()) -> bool:
    if not isinstance(value, str):
        return False
    if (ABSOLUTE_PATH_RE.search(value) or PATH_TRAVERSAL_RE.search(value)
            or URI_AUTHORITY_RE.search(value) or SSH_TARGET_RE.search(value)
            or LOCAL_HOST_RE.search(value) or PRIVATE_ADDRESS_RE.search(value)):
        return True
    low = value.lower()
    return any(re.search(rf"\b{re.escape(str(h).lower())}\b", low) for h in host_denylist)


def machine_path_hits(obj: Any, path: str = "",
                      host_denylist: Iterable[str] = ()) -> list[str]:
    """Every absolute path, traversal, host reference or private address — KEY or VALUE, at
    any depth. A published artifact carries no machine: not the one that made it, not the
    one that will read it."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if MACHINE_KEY_RE.search(str(key)):
                hits.append(here)
            hits.extend(machine_path_hits(value, here, host_denylist))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(machine_path_hits(value, f"{path}[{i}]", host_denylist))
    elif _value_is_machine(obj, host_denylist):
        hits.append(path or "<root>")
    return hits

