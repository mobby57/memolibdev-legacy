"""Local, side-effect-free contracts for external code proposals.

This module validates only a bounded data contract. It does not read files,
execute tests, parse or apply diffs, create snapshots, or grant authority.
Provider-declared test outcomes remain unverified declarations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
import unicodedata
from typing import Final, TypeAlias


SCHEMA_VERSION: Final = "external-proposal/v1"
MAX_ALLOWED_FILES: Final = 8
MAX_DECLARED_TESTS: Final = 20
MAX_PLAN_STEPS: Final = 10
MAX_PATH_CHARS: Final = 260
MAX_DIFF_BYTES: Final = 256 * 1024
MAX_METADATA_ITEMS: Final = 16
MAX_METADATA_VALUE_CHARS: Final = 512
MAX_DECLARED_TEST_DETAILS_CHARS: Final = 2_048
MAX_JSON_DEPTH: Final = 8
MAX_JSON_COLLECTION_ITEMS: Final = 64

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_METADATA_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ContractValidationError(ValueError):
    """Raised internally for an invalid external-proposal contract."""


class ProviderStatus(str, Enum):
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    BLOCKED = "BLOCKED"


class RejectionCode(str, Enum):
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNKNOWN_SCHEMA_VERSION = "UNKNOWN_SCHEMA_VERSION"
    IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_ENCODING = "INVALID_ENCODING"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    FORBIDDEN_FIELD = "FORBIDDEN_FIELD"
    FORBIDDEN_PATH = "FORBIDDEN_PATH"
    INVALID_CONTRACT = "INVALID_CONTRACT"


class DeclaredTestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNKNOWN = "unknown"


RawJsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | tuple["RawJsonValue", ...]
    | tuple[tuple[str, "RawJsonValue"], ...]
)


FORBIDDEN_FIELD_NAMES: Final = frozenset(
    {
        "approval",
        "human_approval",
        "authorization",
        "certificate",
        "apply",
        "apply_result",
        "d5_8",
        "d5_9",
        "commit",
        "push",
        "shell_command",
        "command",
        "execution_token",
    }
)

_RESPONSE_FIELDS: Final = frozenset(
    {
        "schema_version",
        "mission_id",
        "correlation_id",
        "provider_request_id",
        "plan",
        "changed_files",
        "unified_diff",
        "declared_tests",
        "provider_metadata",
    }
)


def _require_nfc(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{field}: string required")
    if "\x00" in value or unicodedata.normalize("NFC", value) != value:
        raise ContractValidationError(f"{field}: invalid encoding")
    return value


def _require_identifier(value: str, field: str) -> str:
    value = _require_nfc(value, field)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ContractValidationError(f"{field}: invalid identifier")
    return value


def _require_sha256(value: str, field: str) -> str:
    value = _require_nfc(value, field)
    if not _SHA256_RE.fullmatch(value):
        raise ContractValidationError(f"{field}: invalid sha256")
    return value


def _require_nonempty_text(value: str, field: str, maximum: int) -> str:
    value = _require_nfc(value, field)
    if not value.strip() or len(value) > maximum:
        raise ContractValidationError(f"{field}: invalid text")
    return value


def _require_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ContractValidationError(f"{field}: non-negative integer required")
    return value


def _require_relative_path(value: str, field: str) -> str:
    value = _require_nonempty_text(value, field, MAX_PATH_CHARS)
    if (
        "\\" in value
        or value.startswith("/")
        or value.startswith(".")
        or ":" in value
        or "//" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ContractValidationError(f"{field}: forbidden path")
    return value


@dataclass(frozen=True)
class AllowedFileReference:
    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _require_relative_path(self.path, "path"))
        object.__setattr__(self, "sha256", _require_sha256(self.sha256, "sha256"))
        object.__setattr__(
            self,
            "size_bytes",
            _require_nonnegative_int(self.size_bytes, "size_bytes"),
        )


@dataclass(frozen=True)
class ExternalProposalRequest:
    schema_version: str
    mission_id: str
    correlation_id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    allowed_files: tuple[AllowedFileReference, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("request: unsupported schema version")
        object.__setattr__(
            self,
            "mission_id",
            _require_identifier(self.mission_id, "mission_id"),
        )
        object.__setattr__(
            self,
            "correlation_id",
            _require_identifier(self.correlation_id, "correlation_id"),
        )
        object.__setattr__(
            self,
            "objective",
            _require_nonempty_text(self.objective, "objective", 2_048),
        )
        if not isinstance(self.acceptance_criteria, tuple):
            raise ContractValidationError("acceptance_criteria: tuple required")
        if not self.acceptance_criteria or len(self.acceptance_criteria) > MAX_PLAN_STEPS:
            raise ContractValidationError("acceptance_criteria: invalid count")
        object.__setattr__(
            self,
            "acceptance_criteria",
            tuple(
                _require_nonempty_text(item, "acceptance_criteria", 1_024)
                for item in self.acceptance_criteria
            ),
        )
        if not isinstance(self.allowed_files, tuple):
            raise ContractValidationError("allowed_files: tuple required")
        if not self.allowed_files or len(self.allowed_files) > MAX_ALLOWED_FILES:
            raise ContractValidationError("allowed_files: invalid count")
        if not all(isinstance(item, AllowedFileReference) for item in self.allowed_files):
            raise ContractValidationError("allowed_files: invalid item")
        paths = tuple(item.path for item in self.allowed_files)
        if len(set(paths)) != len(paths):
            raise ContractValidationError("allowed_files: duplicate path")


@dataclass(frozen=True)
class DeclaredTestResult:
    name: str
    claimed_status: DeclaredTestStatus
    details: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "test.name"))
        if not isinstance(self.claimed_status, DeclaredTestStatus):
            raise ContractValidationError("test.claimed_status: invalid status")
        if self.details is not None:
            object.__setattr__(
                self,
                "details",
                _require_nonempty_text(
                    self.details,
                    "test.details",
                    MAX_DECLARED_TEST_DETAILS_CHARS,
                ),
            )


@dataclass(frozen=True)
class ExternalProposal:
    schema_version: str
    mission_id: str
    correlation_id: str
    provider_request_id: str
    plan: tuple[str, ...]
    changed_files: tuple[str, ...]
    unified_diff: str
    declared_tests: tuple[DeclaredTestResult, ...]
    provider_metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("proposal: unsupported schema version")
        object.__setattr__(
            self,
            "mission_id",
            _require_identifier(self.mission_id, "proposal.mission_id"),
        )
        object.__setattr__(
            self,
            "correlation_id",
            _require_identifier(self.correlation_id, "proposal.correlation_id"),
        )
        object.__setattr__(
            self,
            "provider_request_id",
            _require_identifier(self.provider_request_id, "provider_request_id"),
        )
        if not isinstance(self.plan, tuple) or not self.plan:
            raise ContractValidationError("proposal.plan: invalid tuple")
        if not isinstance(self.changed_files, tuple) or not self.changed_files:
            raise ContractValidationError("proposal.changed_files: invalid tuple")
        if not isinstance(self.declared_tests, tuple):
            raise ContractValidationError("proposal.declared_tests: tuple required")
        if not isinstance(self.provider_metadata, tuple):
            raise ContractValidationError("proposal.provider_metadata: tuple required")
        if not all(isinstance(item, str) for item in self.plan):
            raise ContractValidationError("proposal.plan: invalid item")
        if not all(isinstance(item, str) for item in self.changed_files):
            raise ContractValidationError("proposal.changed_files: invalid item")
        if not all(isinstance(item, DeclaredTestResult) for item in self.declared_tests):
            raise ContractValidationError("proposal.declared_tests: invalid item")
        if not all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
            for item in self.provider_metadata
        ):
            raise ContractValidationError("proposal.provider_metadata: invalid item")


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderStatus
    raw_response: RawJsonValue | None
    error_code: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderStatus):
            raise ContractValidationError("provider_result: invalid status")
        if self.status is ProviderStatus.RESPONSE_RECEIVED:
            if self.raw_response is None or self.error_code is not None:
                raise ContractValidationError("provider_result: invalid response state")
            if isinstance(self.raw_response, (dict, list)):
                raise ContractValidationError("provider_result: mutable response")
            if freeze_json_value(self.raw_response) != self.raw_response:
                raise ContractValidationError("provider_result: non-canonical response")
        else:
            if self.raw_response is not None or not self.error_code:
                raise ContractValidationError("provider_result: invalid error state")
            object.__setattr__(
                self,
                "error_code",
                _require_identifier(self.error_code, "error_code"),
            )

    @classmethod
    def response_received(cls, response: object) -> "ProviderResult":
        return cls(
            status=ProviderStatus.RESPONSE_RECEIVED,
            raw_response=freeze_json_value(response),
            error_code=None,
        )

    @classmethod
    def timeout(cls) -> "ProviderResult":
        return cls(
            status=ProviderStatus.TIMEOUT,
            raw_response=None,
            error_code="TIMEOUT",
        )

    @classmethod
    def error(cls, error_code: str) -> "ProviderResult":
        return cls(
            status=ProviderStatus.ERROR,
            raw_response=None,
            error_code=error_code,
        )


@dataclass(frozen=True)
class ValidatedProposal:
    proposal: ExternalProposal
    request_sha256: str
    raw_response_sha256: str
    declared_diff_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, ExternalProposal):
            raise ContractValidationError("validated proposal: invalid proposal")
        for field, value in (
            ("request_sha256", self.request_sha256),
            ("raw_response_sha256", self.raw_response_sha256),
            ("declared_diff_sha256", self.declared_diff_sha256),
        ):
            _require_sha256(value, field)


@dataclass(frozen=True)
class ProposalValidationResult:
    status: ValidationStatus
    validated_proposal: ValidatedProposal | None
    rejection_codes: tuple[RejectionCode, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ValidationStatus):
            raise ContractValidationError("validation result: invalid status")
        if not isinstance(self.rejection_codes, tuple) or not all(
            isinstance(code, RejectionCode) for code in self.rejection_codes
        ):
            raise ContractValidationError("validation result: invalid rejection codes")
        if self.status is ValidationStatus.VALID:
            if self.validated_proposal is None or self.rejection_codes:
                raise ContractValidationError("validation result: invalid valid state")
        elif self.validated_proposal is not None or not self.rejection_codes:
            raise ContractValidationError("validation result: invalid blocked state")


def _freeze_mapping(value: object, depth: int) -> tuple[tuple[str, RawJsonValue], ...]:
    if not isinstance(value, dict):
        raise ContractValidationError("json object required")
    if len(value) > MAX_JSON_COLLECTION_ITEMS:
        raise ContractValidationError("json object too large")
    entries: list[tuple[str, RawJsonValue]] = []
    seen: set[str] = set()
    for key, child in value.items():
        if not isinstance(key, str) or not key.isascii() or key in seen:
            raise ContractValidationError("json object has invalid key")
        seen.add(key)
        entries.append((key, freeze_json_value(child, depth + 1)))
    return tuple(sorted(entries, key=lambda entry: entry[0]))


def freeze_json_value(value: object, depth: int = 0) -> RawJsonValue:
    """Convert admitted JSON-like data into immutable canonical containers."""
    if depth > MAX_JSON_DEPTH:
        raise ContractValidationError("json nesting too deep")
    if value is None or type(value) in {str, bool, int}:
        if isinstance(value, str):
            _require_nfc(value, "json string")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractValidationError("json float is not finite")
        return value
    if isinstance(value, dict):
        return _freeze_mapping(value, depth)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_JSON_COLLECTION_ITEMS:
            raise ContractValidationError("json array too large")
        return tuple(freeze_json_value(item, depth + 1) for item in value)
    raise ContractValidationError("json has unsupported type")


def parse_json_response(text: str) -> ProviderResult:
    """Parse JSON while rejecting duplicate keys before immutable conversion."""
    try:
        value = json.loads(
            _require_nonempty_text(text, "response", MAX_DIFF_BYTES * 2),
            object_pairs_hook=_pairs_without_duplicates,
        )
        return ProviderResult.response_received(value)
    except (ContractValidationError, TypeError, ValueError, UnicodeError, RecursionError):
        return ProviderResult.error("MALFORMED_RESPONSE")


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractValidationError("json duplicate key")
        result[key] = value
    return result


def _as_object(value: RawJsonValue, field: str) -> dict[str, RawJsonValue]:
    if not isinstance(value, tuple):
        raise ContractValidationError(f"{field}: object required")
    result: dict[str, RawJsonValue] = {}
    for entry in value:
        if (
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or entry[0] in result
        ):
            raise ContractValidationError(f"{field}: invalid object")
        result[entry[0]] = entry[1]
    return result


def _as_array(value: RawJsonValue, field: str) -> tuple[RawJsonValue, ...]:
    if not isinstance(value, tuple):
        raise ContractValidationError(f"{field}: array required")
    return value


def _as_string(value: RawJsonValue, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{field}: string required")
    return _require_nonempty_text(value, field, maximum)


def _scan_forbidden_fields(value: RawJsonValue) -> None:
    if isinstance(value, tuple):
        if value and all(
            isinstance(entry, tuple)
            and len(entry) == 2
            and isinstance(entry[0], str)
            for entry in value
        ):
            for key, child in value:
                if not key.isascii():
                    raise ContractValidationError("json key is not ascii")
                normalized_key = unicodedata.normalize("NFKC", key).casefold()
                if normalized_key in FORBIDDEN_FIELD_NAMES:
                    raise ContractValidationError("forbidden field")
                _scan_forbidden_fields(child)
        else:
            for child in value:
                _scan_forbidden_fields(child)


def _external_proposal_from_raw(
    request: ExternalProposalRequest,
    raw_response: RawJsonValue,
) -> ExternalProposal:
    _scan_forbidden_fields(raw_response)
    root = _as_object(raw_response, "response")
    if set(root) != _RESPONSE_FIELDS:
        raise ContractValidationError("response: unexpected field set")

    schema_version = _as_string(root["schema_version"], "schema_version", 64)
    if schema_version != SCHEMA_VERSION:
        raise ContractValidationError("response: unsupported schema version")

    mission_id = _require_identifier(
        _as_string(root["mission_id"], "mission_id", 128),
        "mission_id",
    )
    correlation_id = _require_identifier(
        _as_string(root["correlation_id"], "correlation_id", 128),
        "correlation_id",
    )
    if mission_id != request.mission_id or correlation_id != request.correlation_id:
        raise ContractValidationError("response: identifier mismatch")

    provider_request_id = _require_identifier(
        _as_string(root["provider_request_id"], "provider_request_id", 128),
        "provider_request_id",
    )

    raw_plan = _as_array(root["plan"], "plan")
    if not raw_plan or len(raw_plan) > MAX_PLAN_STEPS:
        raise ContractValidationError("plan: invalid count")
    plan = tuple(_as_string(item, "plan item", 1_024) for item in raw_plan)

    raw_changed_files = _as_array(root["changed_files"], "changed_files")
    if not raw_changed_files or len(raw_changed_files) > MAX_ALLOWED_FILES:
        raise ContractValidationError("changed_files: invalid count")
    changed_files = tuple(
        _require_relative_path(_as_string(item, "changed_file", MAX_PATH_CHARS), "changed_file")
        for item in raw_changed_files
    )
    if len(set(changed_files)) != len(changed_files):
        raise ContractValidationError("changed_files: duplicate path")
    allowed_paths = {file.path for file in request.allowed_files}
    if not set(changed_files).issubset(allowed_paths):
        raise ContractValidationError("changed_files: forbidden path")

    unified_diff = _as_string(root["unified_diff"], "unified_diff", MAX_DIFF_BYTES)
    if len(unified_diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise ContractValidationError("unified_diff: too large")

    raw_tests = _as_array(root["declared_tests"], "declared_tests")
    if len(raw_tests) > MAX_DECLARED_TESTS:
        raise ContractValidationError("declared_tests: too many entries")
    declared_tests: list[DeclaredTestResult] = []
    for item in raw_tests:
        test = _as_object(item, "declared_test")
        if set(test) not in ({"name", "claimed_status"}, {"name", "claimed_status", "details"}):
            raise ContractValidationError("declared_test: unexpected field set")
        status_value = _as_string(test["claimed_status"], "claimed_status", 32)
        try:
            status = DeclaredTestStatus(status_value)
        except ValueError as exc:
            raise ContractValidationError("declared_test: invalid status") from exc
        details_value = test.get("details")
        details = (
            _as_string(details_value, "details", MAX_DECLARED_TEST_DETAILS_CHARS)
            if details_value is not None
            else None
        )
        declared_tests.append(
            DeclaredTestResult(
                name=_as_string(test["name"], "test.name", 128),
                claimed_status=status,
                details=details,
            )
        )

    raw_metadata = _as_object(root["provider_metadata"], "provider_metadata")
    if not raw_metadata or len(raw_metadata) > MAX_METADATA_ITEMS:
        raise ContractValidationError("provider_metadata: invalid count")
    metadata: list[tuple[str, str]] = []
    for key, value in raw_metadata.items():
        if not _METADATA_KEY_RE.fullmatch(key):
            raise ContractValidationError("provider_metadata: invalid key")
        metadata.append(
            (
                key,
                _as_string(value, "provider_metadata value", MAX_METADATA_VALUE_CHARS),
            )
        )

    return ExternalProposal(
        schema_version=schema_version,
        mission_id=mission_id,
        correlation_id=correlation_id,
        provider_request_id=provider_request_id,
        plan=plan,
        changed_files=changed_files,
        unified_diff=unified_diff,
        declared_tests=tuple(declared_tests),
        provider_metadata=tuple(sorted(metadata, key=lambda entry: entry[0])),
    )


def _to_json_value(value: RawJsonValue) -> object:
    if isinstance(value, tuple):
        if value and all(
            isinstance(entry, tuple)
            and len(entry) == 2
            and isinstance(entry[0], str)
            for entry in value
        ):
            return {key: _to_json_value(child) for key, child in value}
        return [_to_json_value(child) for child in value]
    return value


def canonical_json_bytes(value: RawJsonValue) -> bytes:
    """Return UTF-8 bytes for the documented canonical JSON representation."""
    return json.dumps(
        _to_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_canonical(value: RawJsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def request_sha256(request: ExternalProposalRequest) -> str:
    return sha256_canonical(
        (
            ("schema_version", request.schema_version),
            ("mission_id", request.mission_id),
            ("correlation_id", request.correlation_id),
            ("objective", request.objective),
            ("acceptance_criteria", tuple(request.acceptance_criteria)),
            (
                "allowed_files",
                tuple(
                    (
                        ("path", item.path),
                        ("sha256", item.sha256),
                        ("size_bytes", item.size_bytes),
                    )
                    for item in request.allowed_files
                ),
            ),
        )
    )


def validate_provider_result(
    request: ExternalProposalRequest,
    provider_result: ProviderResult,
) -> ProposalValidationResult:
    """Validate only contract shape and bounds; never validate code safety."""
    if provider_result.status is ProviderStatus.TIMEOUT:
        return ProposalValidationResult(
            status=ValidationStatus.BLOCKED,
            validated_proposal=None,
            rejection_codes=(RejectionCode.PROVIDER_TIMEOUT,),
        )
    if provider_result.status is ProviderStatus.ERROR:
        return ProposalValidationResult(
            status=ValidationStatus.BLOCKED,
            validated_proposal=None,
            rejection_codes=(RejectionCode.PROVIDER_ERROR,),
        )

    try:
        if provider_result.raw_response is None:
            raise ContractValidationError("response missing")
        proposal = _external_proposal_from_raw(request, provider_result.raw_response)
        return ProposalValidationResult(
            status=ValidationStatus.VALID,
            validated_proposal=ValidatedProposal(
                proposal=proposal,
                request_sha256=request_sha256(request),
                raw_response_sha256=sha256_canonical(provider_result.raw_response),
                declared_diff_sha256=hashlib.sha256(
                    proposal.unified_diff.encode("utf-8")
                ).hexdigest(),
            ),
            rejection_codes=(),
        )
    except ContractValidationError as exc:
        message = str(exc)
        if "schema version" in message:
            code = RejectionCode.UNKNOWN_SCHEMA_VERSION
        elif "identifier mismatch" in message:
            code = RejectionCode.IDENTIFIER_MISMATCH
        elif "provider_request_id" in message:
            code = RejectionCode.MISSING_PROVENANCE
        elif "forbidden field" in message:
            code = RejectionCode.FORBIDDEN_FIELD
        elif "path" in message:
            code = RejectionCode.FORBIDDEN_PATH
        elif "too large" in message or "invalid count" in message:
            code = RejectionCode.LIMIT_EXCEEDED
        elif "encoding" in message:
            code = RejectionCode.INVALID_ENCODING
        elif "type" in message or "required" in message:
            code = RejectionCode.INVALID_TYPE
        else:
            code = RejectionCode.INVALID_CONTRACT
        return ProposalValidationResult(
            status=ValidationStatus.BLOCKED,
            validated_proposal=None,
            rejection_codes=(code,),
        )
