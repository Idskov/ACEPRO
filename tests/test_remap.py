"""
Tests for the in-print tool-remap guard in perform_tool_change and the
transitive remap update in execute_swap.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


@pytest.fixture
def manager_remap_state():
    """A minimal manager-like object with state and gcode mocks for guard tests.

    We do NOT instantiate the real AceManager because perform_tool_change has
    extensive side effects. Instead we test the guard's behavior in isolation
    by simulating its environment: a state dict, a gcode mock, and a sentinel
    that captures the post-guard target_tool.
    """
    class FakeManager:
        pass

    m = FakeManager()
    state = {}
    m.state = Mock()
    m.state.get = Mock(side_effect=lambda k, d=None: state.get(k, d))
    m.state.set_and_save = Mock(side_effect=lambda k, v: state.__setitem__(k, v))
    m._state_store = state
    m.gcode = Mock()
    return m


def apply_remap_guard(manager, target_tool, is_endless_spool=False):
    """Replicate the production guard logic for unit testing.

    This mirrors the code that lives at the top of AceManager.perform_tool_change.
    Tests verify the guard's contract; an integration test or smoke test
    verifies it's wired up correctly inside the real method.
    """
    if not is_endless_spool:
        remap = manager.state.get("ace_active_remap", {})
        remap_normalized = {int(k): int(v) for k, v in remap.items()}
        if target_tool in remap_normalized:
            remapped = remap_normalized[target_tool]
            manager.gcode.respond_info(
                f"ACE: Tool remap active: T{target_tool} -> T{remapped}"
            )
            target_tool = remapped
    return target_tool


class TestRemapGuard:
    def test_no_remap_passes_through(self, manager_remap_state):
        result = apply_remap_guard(manager_remap_state, target_tool=0)
        assert result == 0
        assert not manager_remap_state.gcode.respond_info.called

    def test_remap_rewrites_target(self, manager_remap_state):
        manager_remap_state._state_store["ace_active_remap"] = {0: 2}
        result = apply_remap_guard(manager_remap_state, target_tool=0)
        assert result == 2
        # Verify the user gets feedback about the remap
        calls = [str(c) for c in manager_remap_state.gcode.respond_info.call_args_list]
        assert any("remap active" in c.lower() for c in calls)

    def test_is_endless_spool_bypasses_remap(self, manager_remap_state):
        manager_remap_state._state_store["ace_active_remap"] = {0: 2}
        result = apply_remap_guard(manager_remap_state, target_tool=0, is_endless_spool=True)
        assert result == 0  # remap bypassed
        assert not manager_remap_state.gcode.respond_info.called

    def test_string_keys_in_remap(self, manager_remap_state):
        manager_remap_state._state_store["ace_active_remap"] = {"0": 2}
        result = apply_remap_guard(manager_remap_state, target_tool=0)
        assert result == 2

    def test_unmatched_target_passes_through(self, manager_remap_state):
        manager_remap_state._state_store["ace_active_remap"] = {0: 2}
        result = apply_remap_guard(manager_remap_state, target_tool=1)
        assert result == 1
        assert not manager_remap_state.gcode.respond_info.called


class TestRemapGuardWiredUp:
    """Smoke test: the production perform_tool_change actually contains the guard.

    Because perform_tool_change is wrapped by @toolchange_in_progress_guard (which
    does not use functools.wraps), inspect.getsource returns the wrapper body.
    We read the source file directly instead so the check is reliable.
    """

    def test_guard_present_in_source(self):
        import pathlib
        from ace import manager as ace_manager_module

        source_path = pathlib.Path(ace_manager_module.__file__)
        source = source_path.read_text(encoding="utf-8")

        # Locate the function body by finding its def line and extracting a window
        # large enough to cover the guard (first ~30 lines after the def).
        lines = source.splitlines()
        start = next(
            (i for i, ln in enumerate(lines) if "def perform_tool_change" in ln),
            None,
        )
        assert start is not None, "perform_tool_change not found in manager.py"
        snippet = "\n".join(lines[start : start + 40])

        assert "Tool remap active" in snippet, "guard log line missing"
        assert "is_endless_spool" in snippet, "is_endless_spool bypass missing"
        assert "ace_active_remap" in snippet, "remap state key missing"


class TestExecuteSwapRemap:
    """Verify execute_swap writes ace_active_remap with transitive updates."""

    def setup_method(self):
        from ace.endless_spool import EndlessSpool
        from ace.config import ACE_INSTANCES, SLOTS_PER_ACE

        self.printer = Mock()
        self.gcode = Mock()
        self.manager = Mock()
        self.state = {}

        def state_get(key, default=None):
            return self.state.get(key, default)

        def state_set_and_save(key, value):
            self.state[key] = value

        self.manager.state.get = Mock(side_effect=state_get)
        self.manager.state.set_and_save = Mock(side_effect=state_set_and_save)
        self.manager.perform_tool_change = Mock(return_value="ok")
        self.manager.gcode = self.gcode
        self.manager._sync_inventory_to_persistent = Mock()

        reactor = Mock()
        reactor.monotonic = Mock(return_value=0.0)
        self.printer.get_reactor = Mock(return_value=reactor)

        ACE_INSTANCES.clear()
        instance = Mock()
        instance.instance_num = 0
        instance.SLOT_COUNT = SLOTS_PER_ACE
        instance.inventory = [
            {"status": "ready", "material": "PETG", "color": [0, 0, 0]}
            for _ in range(SLOTS_PER_ACE)
        ]
        ACE_INSTANCES[0] = instance
        self.manager.instances = {0: instance}

        self.endless_spool = EndlessSpool(self.printer, self.gcode, self.manager)

    def teardown_method(self):
        from ace.config import ACE_INSTANCES
        ACE_INSTANCES.clear()

    def test_simple_swap_writes_remap(self):
        self.endless_spool.execute_swap(from_tool=0, to_tool=2)
        assert self.state.get("ace_active_remap") == {0: 2}

    def test_chain_swap_transitive_update(self):
        # Pre-existing remap from a prior swap: T0 was served by T2
        self.state["ace_active_remap"] = {0: 2}
        # Now T2 runs out and swaps to T4. The {0: 2} entry must update to {0: 4}.
        self.endless_spool.execute_swap(from_tool=2, to_tool=4)
        assert self.state.get("ace_active_remap") == {0: 4, 2: 4}

    def test_failed_swap_does_not_write_remap(self):
        self.manager.perform_tool_change = Mock(side_effect=Exception("nope"))
        try:
            self.endless_spool.execute_swap(from_tool=0, to_tool=2)
        except Exception:
            pass
        assert "ace_active_remap" not in self.state
