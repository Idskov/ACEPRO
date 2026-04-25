"""
Tests for the 'spare' endless-spool match mode whitelist and basic resolution.
"""
import pytest
from unittest.mock import Mock
from ace.endless_spool import EndlessSpool
from ace.config import ACE_INSTANCES, SLOTS_PER_ACE


class TestSpareModeWhitelist:
    """Verify 'spare' is accepted by get_match_mode."""

    def setup_method(self):
        self.printer = Mock()
        self.gcode = Mock()
        self.manager = Mock()
        reactor = Mock()
        reactor.monotonic = Mock(return_value=0.0)
        self.printer.get_reactor = Mock(return_value=reactor)
        self.endless_spool = EndlessSpool(self.printer, self.gcode, self.manager)

    def test_spare_mode_is_accepted(self):
        self.manager.state.get = Mock(return_value="spare")
        assert self.endless_spool.get_match_mode() == "spare"

    def test_invalid_mode_falls_back_to_exact(self):
        self.manager.state.get = Mock(return_value="bogus")
        assert self.endless_spool.get_match_mode() == "exact"


class TestSpareModeFind:
    """Verify find_exact_match in spare mode resolves through ace_spare_mapping."""

    def setup_method(self):
        self.printer = Mock()
        self.gcode = Mock()
        self.manager = Mock()
        reactor = Mock()
        reactor.monotonic = Mock(return_value=0.0)
        self.printer.get_reactor = Mock(return_value=reactor)

        self.endless_spool = EndlessSpool(self.printer, self.gcode, self.manager)
        self.endless_spool.get_match_mode = Mock(return_value="spare")

        ACE_INSTANCES.clear()
        instance = Mock()
        instance.instance_num = 0
        instance.tool_offset = 0
        instance.SLOT_COUNT = SLOTS_PER_ACE
        instance.inventory = [
            {'material': 'PETG', 'color': [0, 0, 0], 'status': 'ready'}
            for _ in range(SLOTS_PER_ACE)
        ]
        ACE_INSTANCES[0] = instance

    def teardown_method(self):
        ACE_INSTANCES.clear()

    def test_returns_designated_spare_when_ready(self):
        self.manager.state.get = Mock(return_value={0: 2})
        assert self.endless_spool.find_exact_match(0) == 2

    def test_returns_minus_one_when_no_mapping(self):
        self.manager.state.get = Mock(return_value={})
        assert self.endless_spool.find_exact_match(0) == -1

    def test_returns_minus_one_when_spare_not_ready(self):
        ACE_INSTANCES[0].inventory[2]["status"] = "empty"
        self.manager.state.get = Mock(return_value={0: 2})
        assert self.endless_spool.find_exact_match(0) == -1

    def test_string_keys_handled(self):
        # saved_variables sometimes stringifies dict keys
        self.manager.state.get = Mock(return_value={"0": 2})
        assert self.endless_spool.find_exact_match(0) == 2

    def test_self_target_rejected(self):
        # Defensive: even if persisted state is corrupted
        self.manager.state.get = Mock(return_value={0: 0})
        assert self.endless_spool.find_exact_match(0) == -1
