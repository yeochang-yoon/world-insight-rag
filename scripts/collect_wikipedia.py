#!/usr/bin/env python3
"""Collector CLI; real implementation is in world_insight.wiki."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from world_insight.cli import main

if __name__ == "__main__":
    main(["collect", *sys.argv[1:]])
