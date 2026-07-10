"""Searches settings row: unset default, round-trip, overwrite."""

from __future__ import annotations

from jobwatch.searches import SearchConfig, get_searches, set_searches


def test_unconfigured_returns_empty(session):
    assert get_searches(session) == []


def test_set_then_get_round_trips(session):
    searches = [
        SearchConfig(name="swe-dk", search_term="software engineer", location="Denmark"),
        SearchConfig(name="sre-dk", search_term="SRE", location="Denmark", results_wanted=20),
    ]
    set_searches(session, searches)
    assert get_searches(session) == searches


def test_set_overwrites_previous_value(session):
    set_searches(session, [SearchConfig(name="a", search_term="x", location="y")])
    replacement = [SearchConfig(name="b", search_term="x", location="y")]
    set_searches(session, replacement)
    assert get_searches(session) == replacement
