import pytest
import pathlib
import os
import logging

from SpectrumAnalyser import logger
from SpectrumAnalyser import setup_logging
from SpectrumAnalyser import setup_snap_config
from SpectrumAnalyser import setup_thumbs_dir
from misc import global_vars


def test_logging_dir():
    global logger
    test_filename = "test_logger.log"
    setup_logging(test_filename)
    # check logging directory is created where we expect it - relative to src directory (we are in test dir)
    log_dir = pathlib.PurePath(os.path.dirname(__file__), "..", "src", global_vars.log_dir)
    assert os.path.isdir(log_dir)


def test_snapshot_dir():
    _ = setup_snap_config()
    snap_dir = pathlib.PurePath(os.path.dirname(__file__), "..", "src", "snapshots")
    assert os.path.isdir(snap_dir)


def test_thumbnail_dir():
    _ = setup_thumbs_dir()
    thumb_dir = pathlib.PurePath(os.path.dirname(__file__), "..", "src", "webUI", "webroot", "thumbnails")
    assert os.path.isdir(thumb_dir)

