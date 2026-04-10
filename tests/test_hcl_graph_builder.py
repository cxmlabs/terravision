"""
Unit tests for hcl_graph_builder module.

Tests the HCL-only graph construction pipeline, particularly
reference detection and count.index handling.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock heavy dependencies before importing the module under test
sys.modules.setdefault("modules.provider_detector", MagicMock())
sys.modules.setdefault("modules.config_loader", MagicMock())

from modules.hcl_graph_builder import _find_references_in_string


class TestCountIndexRecursion:
    """Regression tests for count.index infinite recursion bug.
    
    Bug: _find_references_in_string recursed infinitely when count.index
    appeared without brackets (bare), e.g. element(var.subnets, count.index).
    The old code only stripped "[count.index]" but checked for "count.index",
    so bare occurrences produced an unchanged string -> infinite recursion.
    """

    def test_bare_count_index_no_recursion(self):
        """Bare count.index (no brackets) must not cause infinite recursion."""
        result = _find_references_in_string(
            "element(var.subnets, count.index)", [], "src"
        )
        assert isinstance(result, set)

    def test_bracketed_count_index_still_works(self):
        """Bracketed [count.index] should still resolve references."""
        nodes = ["aws_subnet.public"]
        result = _find_references_in_string(
            "${aws_subnet.public[count.index].id}", nodes, "src"
        )
        assert "aws_subnet.public" in result

    def test_mixed_bracketed_and_bare_count_index(self):
        """String with both bracketed and bare count.index."""
        nodes = ["aws_subnet.public"]
        result = _find_references_in_string(
            "${aws_subnet.public[count.index].id}-${count.index}", nodes, "src"
        )
        assert isinstance(result, set)

    def test_count_index_alone(self):
        """Just 'count.index' as entire string."""
        result = _find_references_in_string("count.index", [], "src")
        assert isinstance(result, set)

    def test_count_index_in_cidrsubnet(self):
        """count.index inside cidrsubnet() - common Terraform pattern."""
        result = _find_references_in_string(
            "${cidrsubnet(var.cidr, 8, count.index)}", [], "src"
        )
        assert isinstance(result, set)

    def test_no_count_index_unaffected(self):
        """Strings without count.index should work normally."""
        nodes = ["aws_vpc.main"]
        result = _find_references_in_string(
            "${aws_vpc.main.id}", nodes, "src"
        )
        assert "aws_vpc.main" in result
