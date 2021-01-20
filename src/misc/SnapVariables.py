"""
Class to hold all the programmes variables that we need to pass around for snapshots

Passed to the UI as a jason string when required
"""

import json


class SnapVariables:
    def __init__(self):
        self.type = "snap"  # for use by javascript to distinguish control types

        self.baseFilename = "snap"
        self.snapState = "stop"  # start, stop
        self.preTriggerMilliSec = 500  # milliseconds of capture before a trigger event
        self.postTriggerMilliSec = 1000  # milliseconds of capture after a trigger event
        self.triggerState = "wait"  # "wait", "triggered"
        self.triggered = False  # rather than the state we have a simple boolean
        self.triggers = ["manual", "off"]  # available trigger sources
        self.triggerType = "off"  # current trigger source

        self.cf = 0
        self.sps = 0

        self.baseDirectory = ".\\snapshots"  # constant, we don't expect to change this

    def make_json(self):
        return json.dumps(self, default=lambda o: o.__dict__)
