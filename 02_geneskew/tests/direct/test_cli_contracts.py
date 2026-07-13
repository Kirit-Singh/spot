"""PARSER-TEST EVERY EMBEDDED INVOCATION, against the producer's own argparse.

The invocation contract had drifted comprehensively — it named `direct.cli` (the SCREEN, not
the arm bundles), `direct.run_pathway` (likewise), and required two flags,
`--stage1-v3-selection` and `--stage1-v3-schema`, that NO PRODUCER HAS EVER HAD. A scheduler
that ran it would have died on argv, on every lane. An invocation contract nobody parses is
a comment with a colon in it.

So the flags are re-extracted, HERE, from the producers' own bytes at the pinned commits, by
AST — no import, no producer code copied into this tree, nothing executed. If a producer
changes its argv, this fails, instead of a run failing.
"""
from __future__ import annotations

import ast
import subprocess

import pytest
from direct.arm_topology import LANES
from direct.cli_contracts import CLI_CONTRACTS, PRODUCER_SOURCE, RETIRED_COMMANDS


def _producer_flags(sha: str, path: str) -> tuple[set, set]:
    """(all flags, required flags) from the producer's REAL argparse. By AST; never run."""
    try:
        src = subprocess.run(["git", "show", f"{sha}:{path}"],
                             capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:            # pragma: no cover - producer not fetched
        pytest.skip(f"producer bytes {sha}:{path} are not in this object store")

    every, required = set(), set()
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        flags = {a.value for a in node.args
                 if isinstance(a, ast.Constant) and str(a.value).startswith("--")}
        every |= flags
        if any(k.arg == "required" and getattr(k.value, "value", False) is True
               for k in node.keywords):
            required |= flags
    return every, required


@pytest.mark.parametrize("lane", LANES)
class TestEveryEmbeddedInvocationPARSES:
    def test_every_flag_we_record_EXISTS_in_the_producers_parser(self, lane):
        """The exact failure that shipped: a required flag nobody had ever implemented."""
        every, _ = _producer_flags(*PRODUCER_SOURCE[lane])
        contract = CLI_CONTRACTS[lane]
        recorded = set(contract["required_arguments"]) | set(contract["invocation_flags"])

        unknown = sorted(recorded - every)
        assert not unknown, (
            f"[{lane}] {CLI_CONTRACTS[lane]['command']} has no such flag(s): {unknown}. "
            f"Its real flags are {sorted(every)}")

    def test_every_flag_the_producer_REQUIRES_is_in_our_contract(self, lane):
        """A scheduler missing a required flag dies at argv — after the queue is committed."""
        _, required = _producer_flags(*PRODUCER_SOURCE[lane])
        missing = sorted(required - set(CLI_CONTRACTS[lane]["required_arguments"]))
        assert not missing, (
            f"[{lane}] the producer REQUIRES {missing}, and the contract does not record it")

    def test_the_command_MODULE_actually_exists_at_the_pinned_commit(self, lane):
        sha, path = PRODUCER_SOURCE[lane]
        module = CLI_CONTRACTS[lane]["command"].removeprefix("python -m ")
        # `direct.run_arms` <-> .../direct/run_arms.py
        assert path.endswith(module.replace(".", "/") + ".py"), (
            f"[{lane}] the contract runs {module!r}, but its pinned source is {path!r}")
        assert subprocess.run(["git", "cat-file", "-e", f"{sha}:{path}"],
                              capture_output=True).returncode == 0

    def test_the_contract_does_NOT_name_a_RETIRED_entry_point(self, lane):
        command = CLI_CONTRACTS[lane]["command"]
        assert command not in RETIRED_COMMANDS, (
            f"[{lane}] {command} is retired: {RETIRED_COMMANDS.get(command)}. It still RUNS, "
            "and it produces a release the aggregate must then refuse — a scheduler that "
            "'worked' is the worst way to find that out")


class TestTheInvocationCOUNTSMatchTheLaneCounts:
    """3 + 6 + 6 bundles, but NOT 3 + 6 + 6 invocations. Two lanes emit their whole lane."""

    def test_direct_emits_all_three_conditions_in_ONE_invocation(self):
        c = CLI_CONTRACTS["direct"]
        assert c["n_invocations"] == 1
        assert "--all-conditions" in c["invocation_flags"]

    def test_temporal_emits_all_six_pairs_in_ONE_invocation(self):
        c = CLI_CONTRACTS["temporal"]
        assert c["n_invocations"] == 1
        assert "--all-pairs" in c["invocation_flags"]

    def test_pathway_has_NO_all_in_one_flag_and_is_invoked_per_bundle(self):
        """It takes one --condition and one --gene-sets, so it runs 3 x 2 = 6 times."""
        every, _ = _producer_flags(*PRODUCER_SOURCE["pathway"])
        # the OTHER lanes' all-in-one flags, by name. (Not a `--all` prefix match: pathway
        # does carry `--allow-dirty-tree`, which is not an all-in-one flag at all.)
        assert not ({"--all-conditions", "--all-pairs", "--all-sources"} & every)
        assert CLI_CONTRACTS["pathway"]["n_invocations"] == 6
        assert CLI_CONTRACTS["pathway"]["invocation_flags"] == []
