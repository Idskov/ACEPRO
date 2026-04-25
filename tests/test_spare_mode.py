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
