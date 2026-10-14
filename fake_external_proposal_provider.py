"""Deterministic, in-memory fake provider for J1 contract tests.

It performs no I/O, does not wait, and cannot apply a diff or run tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from external_proposal_contract import (
    ExternalProposalRequest,
    ProviderResult,
    request_sha256,
)


class FakeProviderScenario(str, Enum):
    VALID = "VALID"
    MALFORMED = "MALFORMED"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    FORBIDDEN_PATH = "FORBIDDEN_PATH"
    FORBIDDEN_AUTHORITY = "FORBIDDEN_AUTHORITY"


@dataclass(frozen=True)
class FakeExternalProposalProvider:
    """Return synthetic responses from an injected deterministic scenario."""

    scenario: FakeProviderScenario = FakeProviderScenario.VALID
    enabled: bool = False

    @property
    def available(self) -> bool:
        return self.enabled

    def propose(
        self,
        request: ExternalProposalRequest,
        *,
        timeout_s: float,
    ) -> ProviderResult:
        """Return a deterministic result without waiting or performing I/O."""
        if not self.enabled:
            return ProviderResult.error("PROVIDER_DISABLED")
        if type(timeout_s) not in {int, float} or isinstance(timeout_s, bool) or timeout_s <= 0:
            return ProviderResult.error("INVALID_TIMEOUT")
        if self.scenario is FakeProviderScenario.TIMEOUT:
            return ProviderResult.timeout()
        if self.scenario is FakeProviderScenario.ERROR:
            return ProviderResult.error("SIMULATED_PROVIDER_ERROR")

        response = self._response_for(request)
        return ProviderResult.response_received(response)

    def _response_for(self, request: ExternalProposalRequest) -> dict[str, object]:
        deterministic_id = f"fake-{self.scenario.value.lower()}-{request_sha256(request)[:16]}"
        changed_path = request.allowed_files[0].path
        response: dict[str, object] = {
            "schema_version": request.schema_version,
            "mission_id": request.mission_id,
            "correlation_id": request.correlation_id,
            "provider_request_id": deterministic_id,
            "plan": ["Proposer une modification synthétique minimale."],
            "changed_files": [changed_path],
            "unified_diff": (
                f"--- a/{changed_path}\n"
                f"+++ b/{changed_path}\n"
                "@@ -1 +1 @@\n"
                "-synthetic-old\n"
                "+synthetic-new\n"
            ),
            "declared_tests": [
                {
                    "name": "synthetic-unit-test",
                    "claimed_status": "not_run",
                    "details": "Provider declaration only.",
                }
            ],
            "provider_metadata": {
                "provider_kind": "deterministic_fake",
                "scenario": self.scenario.value,
            },
        }

        if self.scenario is FakeProviderScenario.MALFORMED:
            response.pop("plan")
        elif self.scenario is FakeProviderScenario.MISSING_PROVENANCE:
            response["provider_request_id"] = ""
        elif self.scenario is FakeProviderScenario.IDENTIFIER_MISMATCH:
            response["mission_id"] = "different-mission"
        elif self.scenario is FakeProviderScenario.FORBIDDEN_PATH:
            response["changed_files"] = ["../forbidden.txt"]
        elif self.scenario is FakeProviderScenario.FORBIDDEN_AUTHORITY:
            response["provider_metadata"] = {
                "provider_kind": "deterministic_fake",
                "approval": "not-authoritative",
            }

        return response
