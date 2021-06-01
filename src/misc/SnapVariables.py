"""
Class to hold all the programmes variables that we need to pass around for snapshots

Passed to the UI as a jason string when required
"""

import json
import pathlib
import os

from misc import global_vars

# put snapshot directory in webroot so we can make web links to allow downloading of the snaps
# if the snapshots directory name is changed then you must edit main.js as well updateSnapFileList()
SNAPSHOT_DIRECTORY = pathlib.PurePath(f"{os.path.dirname(__file__)}", "..",
                                      "webUI", "webroot", global_vars.snapshot_dir)


class SnapVariables:
    def __init__(self):
        self.type = "snap"  # for use by javascript to distinguish control types

        self.baseFilename = "snap"
        self.snapState = "stop"  # start, stop
        self.preTriggerMilliSec = 1000  # milliseconds of capture before a trigger event
        self.postTriggerMilliSec = 1000  # milliseconds of capture after a trigger event
        self.triggerState = "wait"  # "wait", "triggered"
        self.triggered = False  # rather than the state we have a simple boolean
        self.triggers = ["manual", "off"]  # available trigger sources
        self.triggerType = "manual"  # current trigger source

        self.currentSizeMbytes = 0
        self.expectedSizeMbytes = 0

        self.cf = 0
        self.sps = 0

        self.max_file_size = 200000000  # 200MBytes, we have to have enough memory to hold this
        self.wav_flag = "Off"  # On/Off as getting True/False/true/false to work through json&web was impossible
        self.directory_list = []  # each entry will be name, date, sizeMbytes

    def make_json(self):
        return json.dumps(self, default=lambda o: o.__dict__)
