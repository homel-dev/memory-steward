"""Serving GC regression tests: durable alias, pinned sessions and restarts."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException

from memory_steward.codegraph_builds import CodeGraphBuildStore
from memory_steward.codegraph_controller import CodeGraphController
from memory_steward.codegraph_publisher import CodeGraphPublisher, service_name


def test_retired_serving_query_guards_active_generation_and_pinned_readers():
    store = CodeGraphBuildStore("unused")
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [("old-one",), ("old-two",)]
    store._connect = lambda **_kw: conn

    assert store.retired_serving_build_ids(grace_seconds=120) == ["old-one", "old-two"]
    query, params = cursor.execute.call_args.args
    assert params == (120,)
    assert "(old.received_at, old.id) < (live.received_at, live.id)" in query
    assert "old.source_namespace = live.source_namespace" in query
    assert "a.updated_at < now()" in query
    assert "session.expires_at > now()" in query
    assert "session.revision <> 'latest'" in query
    assert "registry.worker_id" in query


def test_retired_serving_rejects_negative_grace():
    store = CodeGraphBuildStore("unused")
    with pytest.raises(ValueError):
        store.retired_serving_build_ids(grace_seconds=-1)


def test_serving_prune_idempotent_and_ignores_not_found():
    publisher = object.__new__(CodeGraphPublisher)
    publisher.namespace = "ms"
    publisher.core = MagicMock()
    publisher.apps = MagicMock()
    old = "ce44d4b1-da4e-4b9b-8a19-28ebf0cf70ac"
    publisher.core.delete_namespaced_service.side_effect = ApiException(status=404)
    publisher.prune_build_ids([old, old])
    publisher.prune_build_ids([old])
    publisher.core.delete_namespaced_service.assert_called_once_with(service_name(old), "ms")
    publisher.apps.delete_namespaced_deployment.assert_called_once_with(service_name(old), "ms")


def test_prune_retries_after_transient_kubernetes_error():
    publisher = object.__new__(CodeGraphPublisher)
    publisher.namespace = "ms"
    publisher.core = MagicMock()
    publisher.apps = MagicMock()
    old = "ce44d4b1-da4e-4b9b-8a19-28ebf0cf70ac"
    publisher.apps.delete_namespaced_deployment.side_effect = [ApiException(status=403), None]
    with pytest.raises(ApiException):
        publisher.prune_build_ids([old])
    publisher.prune_build_ids([old])
    assert publisher.apps.delete_namespaced_deployment.call_count == 2


def test_gc_runs_without_new_successful_builds():
    controller = object.__new__(CodeGraphController)
    controller._submit_pending = lambda: 0
    controller._observe_active = lambda: 0
    controller.store = MagicMock()
    controller.publisher = MagicMock()
    controller.store.successful_generations.return_value = []
    controller.store.retired_serving_build_ids.return_value = ["old-id"]
    assert controller.drain_once() == 0
    controller.publisher.prune_build_ids.assert_called_once_with(["old-id"])


def test_gc_runs_even_if_current_deployment_not_ready():
    controller = object.__new__(CodeGraphController)
    controller._submit_pending = lambda: 0
    controller._observe_active = lambda: 0
    controller.store = MagicMock()
    controller.publisher = MagicMock()
    build = {"build_id": "new-id"}
    controller.store.successful_generations.return_value = [build]
    controller.publisher.ensure.return_value = None
    controller.store.retired_serving_build_ids.return_value = ["retired-id"]
    assert controller.drain_once() == 0
    controller.store.activate_serving_alias.assert_not_called()
    controller.publisher.prune_build_ids.assert_called_once_with(["retired-id"])
