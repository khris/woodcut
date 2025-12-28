"""Woodcut - 목재 재단 최적화

Guillotine Cut 알고리즘 기반 목재 재단 최적화 도구
"""

from .strategies import RegionBasedPacker
from .visualizer import visualize_solution

__all__ = ['RegionBasedPacker', 'visualize_solution']
