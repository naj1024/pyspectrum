"""
Class to hold all the programmes variables that we need to pass around for snapshots

Passed to the UI as a jason string when required
"""

from dataclasses import dataclass

@dataclass
class Snapper:
    baseFilename = "snap"
    preTriggerMilliSec = 1000  # milliseconds of capture before a trigger event
    postTriggerMilliSec = 1000  # milliseconds of capture after a trigger event
    triggerState = "wait"  # "wait", "triggered"
    triggered = False  # rather than the state we have a simple boolean
    triggers = ["manual", "off"]  # available trigger sources
    triggerType = "manual"  # current trigger source

    currentSizeMbytes = 0
    expectedSizeMbytes = 0

    cf = 0
    sps = 0

    max_file_size = 500000000  # This is held in memory until the end when it is written out
    file_formats = ['bin', 'sigmf', 'wav']
    file_format = file_formats[0]
    directory_list = []  # each entry will be: name, date, sizeMbytes
