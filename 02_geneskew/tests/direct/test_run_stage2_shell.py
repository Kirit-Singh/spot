"""B3 — the runbook shell, parsed and its argv CAPTURED. Not read and believed.

THE DEFECT: the invocation matrix built selection paths by name —

    --stage1-v3-selection $SEL_WITHIN_$COND
    --stage1-v3-selection $SEL_TEMPORAL_${PAIR// /_}

Bash does not compose a variable name that way. `$SEL_WITHIN_$COND` is the unset variable
`SEL_WITHIN_` followed by `$COND`, so the flag received the bare string `Rest` — a CONDITION
NAME where a FILE PATH belongs. `set -u` does not catch it: the concatenation is a perfectly
valid expansion of two things, one of which is empty. The run then dies reading a file
called `Rest`, or — worse — reads one that happens to exist.

These tests do the two things reading the snippet cannot: `bash -n` PARSES it, and a dry run
CAPTURES the exact argv of every invocation, one argument per line.
"""
from __future__ import annotations

import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "analysis", "run_stage2.sh"))

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
PAIRS = (("Rest", "Stim8hr"), ("Stim8hr", "Rest"), ("Rest", "Stim48hr"),
         ("Stim48hr", "Rest"), ("Stim8hr", "Stim48hr"), ("Stim48hr", "Stim8hr"))
SOURCES = ("reactome", "go_bp")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("stage2run")
    sel = d / "sel"
    sel.mkdir()
    for c in CONDITIONS:
        (sel / f"within_{c}.v3.json").write_text("{}")
    for a, b in PAIRS:
        (sel / f"temporal_{a}_to_{b}.v3.json").write_text("{}")
    for s in SOURCES:
        (sel / f"genesets_{s}.ensembl.json").write_text("{}")
    names = ("V3_SCHEMA", "REGISTRY", "STAGE1_RELEASE", "DE", "GUIDE", "DONOR", "SGRNA",
             "MANIFEST", "SRCREG", "PB", "ENV_LOCK")
    e = dict(os.environ, SEL_DIR=str(sel), OUT=str(d / "out"), SPOT_DRY_RUN="1")
    for n in names:
        p = d / f"{n.lower()}.bin"
        p.write_text("x")
        e[n] = str(p)
    return e


def capture(env, what):
    """Run the script in dry-run mode and parse the invocations it WOULD have made."""
    proc = subprocess.run(["bash", SCRIPT, what], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    invocations, current, label = [], None, None
    for line in proc.stdout.splitlines():
        if line.startswith("=== BEGIN "):
            label, current = line[len("=== BEGIN "):], []
        elif line.startswith("=== END "):
            invocations.append((label, current))
            current = None
        elif current is not None:
            current.append(line)
    return invocations


class TestItParses:
    def test_bash_n_accepts_it(self):
        proc = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    def test_it_contains_NO_indirect_variable_name_construction(self):
        # The EXECUTABLE lines only. The header comment quotes the broken pattern in order
        # to explain it, and a check that cannot tell code from prose would force the file
        # to stop saying what it fixed.
        code = "\n".join(line for line in open(SCRIPT).read().splitlines()
                         if not line.lstrip().startswith("#"))
        assert "$SEL_WITHIN_$" not in code
        assert "$SEL_TEMPORAL_$" not in code
        assert "${!SEL" not in code         # indirect expansion, the same bug by another name


class TestTheArgvIsRight:
    def test_direct_is_three_invocations_one_per_condition(self, env):
        inv = capture(env, "direct")
        assert [label for label, _ in inv] == [f"direct:{c}" for c in CONDITIONS]

    def test_temporal_is_six_ORDERED_pairs(self, env):
        inv = capture(env, "temporal")
        assert [label for label, _ in inv] == \
            [f"temporal:{a}__{b}" for a, b in PAIRS]

    def test_pathway_is_three_conditions_times_two_sources(self, env):
        inv = capture(env, "pathway")
        assert [label for label, _ in inv] == \
            [f"pathway:{c}:{s}" for c in CONDITIONS for s in SOURCES]

    def test_all_is_fifteen_invocations(self, env):
        assert len(capture(env, "all")) == 15


class TestTheSelectionFlagGetsAPATHNotAConditionName:
    """The actual bug: `--stage1-v3-selection Rest`."""

    def _selection_arg(self, argv):
        return argv[argv.index("--stage1-v3-selection") + 1]

    @pytest.mark.parametrize("what", ["direct", "temporal", "pathway"])
    def test_every_selection_argument_is_an_EXISTING_FILE(self, env, what):
        for _label, argv in capture(env, what):
            path = self._selection_arg(argv)
            assert os.path.isfile(path), f"{path!r} is not a file"

    @pytest.mark.parametrize("what", ["direct", "temporal", "pathway"])
    def test_no_argument_is_a_BARE_CONDITION_NAME(self, env, what):
        for _label, argv in capture(env, what):
            for arg in argv:
                assert arg not in CONDITIONS, \
                    f"{arg!r} was passed as an argument — that is the $SEL_WITHIN_$COND bug"

    def test_each_condition_gets_its_OWN_contract(self, env):
        paths = {label: self._selection_arg(argv)
                 for label, argv in capture(env, "direct")}
        assert len(set(paths.values())) == 3
        for cond in CONDITIONS:
            assert os.path.basename(paths[f"direct:{cond}"]) == f"within_{cond}.v3.json"

    def test_each_ORDERED_pair_gets_its_own_contract_and_the_two_directions_differ(
            self, env):
        paths = {label: self._selection_arg(argv)
                 for label, argv in capture(env, "temporal")}
        assert len(set(paths.values())) == 6
        assert paths["temporal:Rest__Stim48hr"] != paths["temporal:Stim48hr__Rest"]

    def test_no_argument_is_EMPTY(self, env):
        for _label, argv in capture(env, "all"):
            assert all(a != "" for a in argv), "an empty argv slot is a silent wrong flag"


class TestItRefusesRatherThanGuessing:
    def test_an_unset_input_is_a_REFUSAL_not_a_default(self, env):
        broken = dict(env)
        del broken["DE"]
        proc = subprocess.run(["bash", SCRIPT, "direct"], env=broken,
                              capture_output=True, text=True)
        assert proc.returncode == 2
        assert "DE" in proc.stderr

    def test_a_missing_contract_is_a_REFUSAL_in_a_real_run(self, env):
        real = dict(env)
        real.pop("SPOT_DRY_RUN")
        real["SEL_DIR"] = os.path.join(env["OUT"], "nonexistent")
        proc = subprocess.run(["bash", SCRIPT, "direct"], env=real,
                              capture_output=True, text=True)
        assert proc.returncode == 2
        assert "does not exist" in proc.stderr

    def test_an_unknown_lane_is_usage_not_a_silent_no_op(self, env):
        proc = subprocess.run(["bash", SCRIPT, "sideways"], env=env,
                              capture_output=True, text=True)
        assert proc.returncode == 2


class TestTheFlagsItPassesActuallyEXIST:
    """A runbook whose flags argparse rejects is a runbook that has never been run."""

    @pytest.mark.parametrize("what,module", [
        ("direct", "direct.cli"),
        ("temporal", "direct.temporal.cli"),
        ("pathway", "direct.run_pathway"),
    ])
    def test_every_flag_the_SCRIPT_passes_exists_in_that_entry_points_argparse(
            self, env, what, module):
        # Driven through the REAL argparse, via --help. An assertion that the flags line up
        # is not a check; asking the parser is.
        help_text = subprocess.run(
            ["python", "-m", module, "--help"],
            cwd=os.path.normpath(os.path.join(HERE, "..", "..", "analysis")),
            capture_output=True, text=True).stdout

        for _label, argv in capture(env, what):
            for arg in argv:
                if arg.startswith("--"):
                    assert arg in help_text, f"{arg} is not a flag of {module}"
