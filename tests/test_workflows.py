"""Tests for the workflow registry."""

from src.agent.workflows import WORKFLOWS, get_by_label, workflow_labels


def test_registry_has_both_workflows():
    keys = {w.key for w in WORKFLOWS}
    assert {"single_hire", "ma_integration"} <= keys


def test_labels_match_registry_order():
    assert workflow_labels() == [w.label for w in WORKFLOWS]


def test_lookup_by_label_round_trips():
    for w in WORKFLOWS:
        assert get_by_label(w.label).key == w.key


def test_unknown_label_falls_back_to_first():
    assert get_by_label("does-not-exist").key == WORKFLOWS[0].key


def test_each_workflow_has_phases_and_copy():
    for w in WORKFLOWS:
        assert w.phases and isinstance(w.phases, list)
        assert w.hero_title and w.intake_placeholder and w.intake_hint
