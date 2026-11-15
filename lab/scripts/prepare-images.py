#!/usr/bin/env python3
"""Prepare a source candidate without building/importing application images.

The implementation is shared with build-images.py through image_sources.py.
Use lab:images:build for the complete operator workflow.
"""
from image_sources import main


if __name__ == '__main__':
    main()
