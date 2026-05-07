# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Tests for per-agent content audit log (Units 1, 2, 3, 7)."""

from __future__ import annotations

import hashlib

from ccs.agent.runtime import CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION
from ccs.core.hashing import compute_content_hash


# ---------------------------------------------------------------------------
# Unit 1: Hash utility and schema version constant
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    def test_empty_string(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_content_hash("") == expected

    def test_hello(self):
        expected = hashlib.sha256(b"hello").hexdigest()
        assert compute_content_hash("hello") == expected

    def test_deterministic(self):
        assert compute_content_hash("same") == compute_content_hash("same")

    def test_different_content_different_hash(self):
        assert compute_content_hash("a") != compute_content_hash("b")

    def test_utf8_encoding(self):
        content = "éàü"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert compute_content_hash(content) == expected


class TestSchemaVersionConstant:
    def test_starts_with_ccs(self):
        assert CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION.startswith("ccs.")

    def test_value(self):
        assert CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION == "ccs.content_audit.v1"
