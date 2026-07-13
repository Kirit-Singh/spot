"""The arm reference: exactly one shape is answerable, and every other is refused BY NAME."""
from __future__ import annotations

import pytest
from fixtures_p2s import CONDITION, PROGRAM
from p2s_arms import armref

KEY = f"direct|{PROGRAM}|increase|{CONDITION}"


def test_a_direct_arm_key_parses_into_its_parts():
    ref = armref.parse(KEY)
    assert (ref.program_id, ref.desired_change, ref.condition) == (
        PROGRAM, "increase", CONDITION)
    assert ref.sign == 1
    assert armref.parse(f"direct|{PROGRAM}|decrease|{CONDITION}").sign == -1


def test_a_temporal_arm_key_is_refused_by_name():
    """This is the temporal firewall, and it is structural.

    A temporal arm is keyed on an ORDERED CONDITION PAIR. There is nothing in this lane that
    can accept one, so there is nothing that could difference the two endpoints into a DiD.
    """
    with pytest.raises(armref.ArmRefError) as e:
        armref.parse(f"temporal|{PROGRAM}|increase|Stim8hr|Stim48hr")
    assert e.value.reason == "p2s_refuses_temporal_arm"
    assert "difference-in-differences" in str(e.value)


def test_a_pathway_arm_key_is_refused():
    with pytest.raises(armref.ArmRefError) as e:
        armref.parse(f"pathway|{PROGRAM}|increase|{CONDITION}|reactome")
    assert e.value.reason == "p2s_refuses_pathway_arm"


@pytest.mark.parametrize("bad", ["high", "low"])
def test_a_POLE_may_not_key_an_arm(bad):
    """The same pole is an increase in one role and a decrease in the other."""
    with pytest.raises(armref.ArmRefError) as e:
        armref.parse(f"direct|{PROGRAM}|{bad}|{CONDITION}")
    assert e.value.reason == "desired_change_is_not_a_desired_change"
    assert "POLE" in str(e.value)


@pytest.mark.parametrize("bad", ["away_from_A", "toward_B"])
def test_a_ROLE_may_not_key_an_arm(bad):
    """A role is a position in somebody's pair, not a property of the arm."""
    with pytest.raises(armref.ArmRefError) as e:
        armref.parse(f"direct|{PROGRAM}|{bad}|{CONDITION}")
    assert "ROLE" in str(e.value)


def test_the_two_arms_of_a_program_are_siblings():
    inc, dec = armref.both_arms(PROGRAM, CONDITION)
    assert inc.desired_change == "increase" and dec.desired_change == "decrease"
    assert armref.sibling(inc).arm_key == dec.arm_key
    assert armref.sibling(dec).arm_key == inc.arm_key
    assert armref.base_change() == "increase"


def test_a_non_canonical_key_is_refused_even_though_it_parses():
    with pytest.raises(armref.ArmRefError) as e:
        armref.parse(f"direct|{PROGRAM}|increase|{CONDITION}|extra")
    assert e.value.reason == "not_a_direct_arm_key"
