"""Deterministic randomized invariant tests for coordinator protocol."""

from __future__ import annotations

import random
from uuid import UUID

from ccs.coordinator.registry import ArtifactRegistry
from ccs.coordinator.service import CoordinatorService
from ccs.core.exceptions import CoherenceError, InvariantViolationError
from ccs.core.invariants import check_monotonic_version, check_single_writer
from ccs.core.types import FetchRequest


def test_randomized_sequences_preserve_swmr_and_monotonic_versions() -> None:
    for seed in range(25):
        rng = random.Random(seed)
        svc = CoordinatorService(ArtifactRegistry())
        artifact = svc.register_artifact(name=f"plan-{seed}.md", content="v1")
        agents = [UUID(int=seed * 100 + i + 1) for i in range(4)]

        previous_version = artifact.version
        for step in range(180):
            agent = rng.choice(agents)
            operation = rng.choice(("fetch", "write", "commit", "upgrade", "invalidate"))

            try:
                if operation == "fetch":
                    svc.fetch(
                        FetchRequest(
                            artifact_id=artifact.id,
                            requesting_agent_id=agent,
                            requested_at_tick=step,
                        )
                    )
                elif operation == "write":
                    svc.write(agent_id=agent, artifact_id=artifact.id, issued_at_tick=step)
                elif operation == "commit":
                    svc.commit(
                        agent_id=agent,
                        artifact_id=artifact.id,
                        content=f"v{step}",
                        issued_at_tick=step,
                    )
                elif operation == "upgrade":
                    svc.upgrade(agent_id=agent, artifact_id=artifact.id, issued_at_tick=step)
                else:
                    svc.invalidate(
                        agent_id=agent,
                        artifact_id=artifact.id,
                        new_version=svc.registry.get_artifact(artifact.id).version,
                        issuer_agent_id=agent,
                        issued_at_tick=step,
                    )
            except CoherenceError:
                # Random operation sequences intentionally include invalid actions.
                pass

            state_map = svc.registry.get_state_map(artifact.id)
            try:
                check_single_writer(state_map)
            except InvariantViolationError as exc:
                raise AssertionError(f"SWMR violation at seed={seed} step={step}: {state_map}") from exc

            current_version = svc.registry.get_artifact(artifact.id).version
            try:
                check_monotonic_version(previous_version, current_version)
            except InvariantViolationError as exc:
                raise AssertionError(
                    f"Monotonic version violation at seed={seed} step={step}: "
                    f"prev={previous_version} current={current_version}"
                ) from exc
            previous_version = current_version
