"""Synthetic J1 tests for local external-proposal contracts.

These tests are not a sandbox or a runtime isolation proof. They exercise
only the pure contract and fake provider once separately authorized to run.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from external_proposal_contract import (
    AllowedFileReference,
    ExternalProposalRequest,
    ProviderResult,
    RejectionCode,
    ValidationStatus,
    parse_json_response,
    validate_provider_result,
)
from fake_external_proposal_provider import (
    FakeExternalProposalProvider,
    FakeProviderScenario,
)


def _request() -> ExternalProposalRequest:
    return ExternalProposalRequest(
        schema_version="external-proposal/v1",
        mission_id="mission-001",
        correlation_id="correlation-001",
        objective="Change synthetic behavior.",
        acceptance_criteria=("A synthetic contract is valid.",),
        allowed_files=(
            AllowedFileReference(
                path="src/example.py",
                sha256="a" * 64,
                size_bytes=42,
            ),
        ),
    )


class ExternalProposalContractTests(unittest.TestCase):
    def test_valid_fake_response_is_contract_valid(self) -> None:
        result = FakeExternalProposalProvider(enabled=True).propose(
            _request(),
            timeout_s=1,
        )
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.VALID)
        self.assertIsNotNone(validation.validated_proposal)

    def test_unknown_schema_is_blocked(self) -> None:
        response = FakeExternalProposalProvider(enabled=True)._response_for(_request())
        response["schema_version"] = "external-proposal/v2"
        validation = validate_provider_result(
            _request(),
            ProviderResult.response_received(response),
        )

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertEqual(
            validation.rejection_codes,
            (RejectionCode.UNKNOWN_SCHEMA_VERSION,),
        )

    def test_identifier_mismatch_is_blocked(self) -> None:
        result = FakeExternalProposalProvider(
            scenario=FakeProviderScenario.IDENTIFIER_MISMATCH,
            enabled=True,
        ).propose(_request(), timeout_s=1)
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertIn(RejectionCode.IDENTIFIER_MISMATCH, validation.rejection_codes)

    def test_missing_provenance_is_blocked(self) -> None:
        result = FakeExternalProposalProvider(
            scenario=FakeProviderScenario.MISSING_PROVENANCE,
            enabled=True,
        ).propose(_request(), timeout_s=1)
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertIn(RejectionCode.MISSING_PROVENANCE, validation.rejection_codes)

    def test_malformed_response_is_blocked_without_validated_proposal(self) -> None:
        result = FakeExternalProposalProvider(
            scenario=FakeProviderScenario.MALFORMED,
            enabled=True,
        ).propose(_request(), timeout_s=1)
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertIsNone(validation.validated_proposal)

    def test_forbidden_path_is_blocked(self) -> None:
        result = FakeExternalProposalProvider(
            scenario=FakeProviderScenario.FORBIDDEN_PATH,
            enabled=True,
        ).propose(_request(), timeout_s=1)
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertIn(RejectionCode.FORBIDDEN_PATH, validation.rejection_codes)

    def test_forbidden_authority_field_is_blocked_recursively(self) -> None:
        result = FakeExternalProposalProvider(
            scenario=FakeProviderScenario.FORBIDDEN_AUTHORITY,
            enabled=True,
        ).propose(_request(), timeout_s=1)
        validation = validate_provider_result(_request(), result)

        self.assertEqual(validation.status, ValidationStatus.BLOCKED)
        self.assertIn(RejectionCode.FORBIDDEN_FIELD, validation.rejection_codes)

    def test_timeout_and_error_never_produce_validated_proposal(self) -> None:
        for scenario in (FakeProviderScenario.TIMEOUT, FakeProviderScenario.ERROR):
            result = FakeExternalProposalProvider(
                scenario=scenario,
                enabled=True,
            ).propose(_request(), timeout_s=1)
            validation = validate_provider_result(_request(), result)

            self.assertEqual(validation.status, ValidationStatus.BLOCKED)
            self.assertIsNone(validation.validated_proposal)

    def test_fake_provider_is_deterministic(self) -> None:
        provider = FakeExternalProposalProvider(enabled=True)

        first = provider.propose(_request(), timeout_s=1)
        second = provider.propose(_request(), timeout_s=1)

        self.assertEqual(first, second)

    def test_duplicate_json_keys_are_rejected_at_parse_boundary(self) -> None:
        result = parse_json_response('{"schema_version":"x","schema_version":"y"}')

        self.assertEqual(result.error_code, "MALFORMED_RESPONSE")

    def test_provider_declared_tests_are_not_verified_results(self) -> None:
        result = FakeExternalProposalProvider(enabled=True).propose(
            _request(),
            timeout_s=1,
        )
        validation = validate_provider_result(_request(), result)
        proposal = validation.validated_proposal

        self.assertIsNotNone(proposal)
        self.assertEqual(
            proposal.proposal.declared_tests[0].claimed_status.value,
            "not_run",
        )
        self.assertFalse(hasattr(proposal.proposal, "verified_tests"))


class StaticDependencyTests(unittest.TestCase):
    def test_j1_modules_do_not_import_runtime_or_authority_modules(self) -> None:
        prohibited_modules = {
            "agent_loop",
            "api_facade",
            "coder_authorization",
            "controlled_coder",
            "d59_controlled_apply",
            "file_target",
            "os",
            "pathlib",
            "socket",
            "subprocess",
        }
        root = Path(__file__).resolve().parent

        for name in (
            "external_proposal_contract.py",
            "fake_external_proposal_provider.py",
        ):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imports = {
                alias.name.split(".", 1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module.split(".", 1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            )
            self.assertTrue(imports.isdisjoint(prohibited_modules), name)
