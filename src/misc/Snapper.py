"""
Class to hold all the programmes variables that we need to pass around for snapshots

Passed to the UI as a jason string when required
"""

import json


class Snapper:
    def __init__(self):
        self.baseFilename = "snap"
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

        self.max_file_size = 500000000  # This is held in memory until the end when it is written out
        self.file_formats = ['bin', 'wav']
        self.file_format = "bin"
        self.directory_list = []  # each entry will be: name, date, sizeMbytes

