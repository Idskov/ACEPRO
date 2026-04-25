"""
Tests for active-remap lifecycle (print-end clear, startup stale-remap).
"""
import pytest
from unittest.mock import Mock
from ace.runout_monitor import RunoutMonitor
from ace.config import SENSOR_TOOLHEAD


@pytest.fixture
def monitor():
    """A RunoutMonitor wired with mocks. Manager exposes a state dict."""
    printer = Mock()
    gcode = Mock()
    reactor = Mock()
    reactor.NOW = 0.0
    reactor.NEVER = float("inf")
    reactor.register_timer = Mock(return_value="timer-id")
    reactor.unregister_timer = Mock()

    manager = Mock()
    state = {}

    def state_get(key, default=None):
        return state.get(key, default)

    def state_set_and_save(key, value):
        state[key] = value

    manager.state.get = Mock(side_effect=state_get)
    manager.state.set_and_save = Mock(side_effect=state_set_and_save)
    manager._state_store = state
    manager.toolchange_in_progress = False
    manager.get_switch_state = Mock(return_value=True)
    manager.is_feed_assist_active = Mock(return_value=False)

    endless = Mock()
    rm = RunoutMonitor(printer, gcode, reactor, endless, manager)
    return rm


def _make_print_stats(state_str):
    """Return a mock print_stats object reporting the given state string."""
    print_stats = Mock()
    print_stats.get_status = Mock(return_value={"state": state_str})
    return print_stats


def _drive_monitor(monitor, state_str):
    """
    Set printer.lookup_object to return a print_stats mock with state_str,
    then call _monitor_runout once.
    """
    monitor.printer.lookup_object = Mock(return_value=_make_print_stats(state_str))
    monitor._monitor_runout(eventtime=1.0)


class TestPrintEndClearsRemap:
    def _prep_monitor(self, monitor):
        """Put monitor into the state it would have mid-print."""
        # runout_detection_active must be True to pass the early-exit guard
        monitor.runout_detection_active = True
        # ace_current_index must be >= 0 to avoid the current_tool < 0 early-exit
        monitor.manager._state_store["ace_current_index"] = 0
        # Simulate the prior tick saw a printing state
        monitor.last_printing_active = True
        monitor.last_print_state = "printing"

    def test_remap_cleared_on_print_complete(self, monitor):
        # Pre-populate state with an active remap
        monitor.manager._state_store["ace_active_remap"] = {0: 2}
        self._prep_monitor(monitor)

        # Now print_stats reports complete -> print_just_stopped fires
        _drive_monitor(monitor, "complete")

        # Verify the remap was cleared
        assert monitor.manager._state_store.get("ace_active_remap") == {}

    def test_remap_not_cleared_when_still_printing(self, monitor):
        monitor.manager._state_store["ace_active_remap"] = {0: 2}
        self._prep_monitor(monitor)

        _drive_monitor(monitor, "printing")

        # Still printing -> remap stays
        assert monitor.manager._state_store["ace_active_remap"] == {0: 2}

    def test_remap_cleared_on_cancel(self, monitor):
        monitor.manager._state_store["ace_active_remap"] = {0: 2}
        self._prep_monitor(monitor)

        _drive_monitor(monitor, "cancelled")

        assert monitor.manager._state_store.get("ace_active_remap") == {}
