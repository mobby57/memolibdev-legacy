"""
Tests du contrat MSAFE (documentation exécutable).

Ces tests valident l'interface, pas l'implémentation.
"""
from datetime import datetime
from pathlib import Path

import pytest
from dataclasses import FrozenInstanceError

from memolibdev.services.msafe import Proposal, ProposalState, MSAFEProtocol


def test_proposal_is_frozen():
    """Une Proposal est immuable après création."""
    p = Proposal(
        id="P-abc",
        file_path=Path("/tmp/test.py"),
        old_sha256="a" * 64,
        new_sha256="b" * 64,
        diff="--- a\n+++ b\n",
    )
    with pytest.raises(FrozenInstanceError):
        p.state = ProposalState.APPLIED


def test_proposal_default_state_is_pending():
    """Une nouvelle Proposal est toujours PENDING."""
    p = Proposal(
        id="P-abc",
        file_path=Path("/tmp/test.py"),
        old_sha256="a" * 64,
        new_sha256="b" * 64,
        diff="",
    )
    assert p.state == ProposalState.PENDING
    assert p.approver is None
    assert p.applied_at is None


def test_proposal_states_are_exhaustive():
    """Les 5 états couvrent tout le cycle de vie."""
    states = {s.value for s in ProposalState}
    assert states == {"pending", "approved", "applied", "rolled_back", "rejected"}


def test_msafe_protocol_has_6_methods():
    """Le contrat MSAFEProtocol expose les 6 méthodes critiques."""
    expected = {"propose", "approve", "apply", "rollback", "verify", "list_pending"}
    actual = {m for m in dir(MSAFEProtocol) if not m.startswith("_")}
    assert expected.issubset(actual)
