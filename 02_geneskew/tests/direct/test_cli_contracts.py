"""CLI_CONTRACTS advertises the ACTUAL producer modules — and ONLY flags those parsers accept.

A manifest that advertised ``direct.cli`` / ``direct.run_pathway`` / ``--stage1-v3-selection``
/ ``--batch-policy`` (none of which the current all-arm producers define) would state a
different execution than the one that produced its bundles. This parser-tests every embedded
invocation against the real module.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from direct.arm_topology import LANES
from direct.cli_contracts import CLI_CONTRACTS, LANE_MODULE, RETIRED_LANE_MODULES

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "analysis")


def _help(module: str) -> str:
    return subprocess.run([sys.executable, "-m", module, "--help"],
                          cwd=ANALYSIS, capture_output=True, text=True).stdout


class TestTheAdvertisedContractMatchesTheRealParsers:
    def test_each_command_names_the_REAL_production_module(self):
        for lane in LANES:
            assert CLI_CONTRACTS[lane]["command"] == f"python -m {LANE_MODULE[lane]}"

    def test_NO_contract_names_a_RETIRED_module(self):
        for lane in LANES:
            cmd = CLI_CONTRACTS[lane]["command"]
            for retired in RETIRED_LANE_MODULES:
                assert not cmd.endswith(retired), f"{lane} names retired {retired}"

    @pytest.mark.parametrize("lane", list(LANES))
    def test_every_required_flag_EXISTS_in_that_parser(self, lane):
        module = LANE_MODULE[lane]
        help_text = _help(module)
        assert help_text, f"{module} --help produced nothing"
        for flag in CLI_CONTRACTS[lane]["required_arguments"]:
            assert flag in help_text, f"{flag} is not a flag of {module}"

    @pytest.mark.parametrize("lane", list(LANES))
    def test_the_module_is_importable_and_has_a_main(self, lane):
        module = LANE_MODULE[lane]
        assert _help(module), f"{module} is not runnable as a module"
