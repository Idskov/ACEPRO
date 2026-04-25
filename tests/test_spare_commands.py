"""
Tests for ACE_SET_SPARE / ACE_CLEAR_SPARE / ACE_LIST_SPARES commands.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from ace import commands as ace_commands
from ace.config import ACE_INSTANCES, SLOTS_PER_ACE


@pytest.fixture(autouse=True)
def populate_ace_instances():
    """Populate ACE_INSTANCES with 1 instance (4 tools) so range checks pass."""
    ACE_INSTANCES.clear()
    instance = Mock()
    instance.instance_num = 0
    instance.tool_offset = 0
    instance.SLOT_COUNT = SLOTS_PER_ACE
    instance.inventory = [
        {"material": "", "color": [0, 0, 0], "status": "ready"}
        for _ in range(SLOTS_PER_ACE)
    ]
    ACE_INSTANCES[0] = instance
    yield
    ACE_INSTANCES.clear()


@pytest.fixture
def manager_with_state():
    """Manager with an in-memory state dict."""
    manager = Mock()
    state_store = {}

    def state_get(key, default=None):
        return state_store.get(key, default)

    def state_set_and_save(key, value):
        state_store[key] = value

    manager.state.get = Mock(side_effect=state_get)
    manager.state.set_and_save = Mock(side_effect=state_set_and_save)
    manager._state_store = state_store
    return manager


@pytest.fixture
def gcmd():
    """A gcmd Mock with default int/string getters."""
    gc = Mock()
    gc.error = Mock(side_effect=lambda msg: ValueError(msg))
    return gc


class TestSetSpare:
    def test_valid_pair_persists(self, manager_with_state, gcmd):
        gcmd.get_int = Mock(side_effect=lambda k, d=None: {"PRIMARY": 0, "SPARE": 2}[k])
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_SET_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {0: 2}

    def test_self_target_rejected(self, manager_with_state, gcmd):
        gcmd.get_int = Mock(side_effect=lambda k, d=None: {"PRIMARY": 0, "SPARE": 0}[k])
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            with pytest.raises(ValueError, match="cannot be its own spare"):
                ace_commands.cmd_ACE_SET_SPARE(gcmd)
        assert "ace_spare_mapping" not in manager_with_state._state_store

    def test_overwrite_existing_pair(self, manager_with_state, gcmd):
        manager_with_state._state_store["ace_spare_mapping"] = {0: 1}
        gcmd.get_int = Mock(side_effect=lambda k, d=None: {"PRIMARY": 0, "SPARE": 2}[k])
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_SET_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {0: 2}

    def test_fan_in_emits_info(self, manager_with_state, gcmd):
        manager_with_state._state_store["ace_spare_mapping"] = {0: 2}
        gcmd.get_int = Mock(side_effect=lambda k, d=None: {"PRIMARY": 1, "SPARE": 2}[k])
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_SET_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {0: 2, 1: 2}
        # Check that an info-level message mentions fan-in
        calls = [str(c) for c in gcmd.respond_info.call_args_list]
        assert any("fan-in" in c.lower() or "already" in c.lower() for c in calls)


class TestClearSpare:
    def test_clear_specific_primary(self, manager_with_state, gcmd):
        manager_with_state._state_store["ace_spare_mapping"] = {0: 2, 1: 3}
        gcmd.get_int = Mock(return_value=0)
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_CLEAR_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {1: 3}

    def test_clear_all_when_primary_omitted(self, manager_with_state, gcmd):
        manager_with_state._state_store["ace_spare_mapping"] = {0: 2, 1: 3}
        gcmd.get_int = Mock(return_value=-1)  # sentinel for "not provided"
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_CLEAR_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {}

    def test_clear_unknown_primary_is_noop(self, manager_with_state, gcmd):
        manager_with_state._state_store["ace_spare_mapping"] = {0: 2}
        gcmd.get_int = Mock(return_value=5)
        with patch.object(ace_commands, "ace_get_manager", return_value=manager_with_state):
            ace_commands.cmd_ACE_CLEAR_SPARE(gcmd)
        assert manager_with_state._state_store["ace_spare_mapping"] == {0: 2}
        calls = [str(c) for c in gcmd.respond_info.call_args_list]
        assert any("nothing changed" in c.lower() for c in calls)
