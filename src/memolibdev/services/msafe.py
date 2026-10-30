"""
services/msafe.py — Chaîne de contrôle MSAFE.

« L'IA propose, les contrôles vérifient, l'humain autorise. »

Cette interface définit le contrat. L'implémentation concrète
(FileSystemMSAFE) sera extraite de backend.py dans une session future.
Voir docs/adr/001-msafe.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol


class ProposalState(str, Enum):
    """États d'une proposition de modification."""
    PENDING = "pending"
    APPROVED = "approved"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Proposal:
    """
    Proposition de modification d'un fichier (immuable).

    Une fois créée, elle ne peut être que transitionnée vers un autre état,
    jamais modifiée in-place.
    """
    id: str
    file_path: Path
    old_sha256: str
    new_sha256: str
    diff: str
    state: ProposalState = ProposalState.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    approver: str | None = None
    snapshot_path: Path | None = None
    evidence_path: Path | None = None


class MSAFEProtocol(Protocol):
    """
    Contrat de la chaîne de contrôle MSAFE.

    Toute implémentation doit garantir :
      1. Aucune écriture sans snapshot préalable
      2. Aucune écriture sans validation humaine explicite
      3. Toute écriture génère une preuve cryptographique
      4. Toute écriture peut être annulée (rollback)
    """

    async def propose(self, file: Path, new_content: str) -> Proposal: ...
    async def approve(self, proposal_id: str, approver: str) -> Proposal: ...
    async def apply(self, proposal_id: str) -> Proposal: ...
    async def rollback(self, proposal_id: str) -> Proposal: ...
    async def verify(self, proposal_id: str) -> bool: ...
    async def list_pending(self) -> list[Proposal]: ...


__all__ = ["ProposalState", "Proposal", "MSAFEProtocol"]
