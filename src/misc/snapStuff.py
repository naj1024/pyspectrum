import datetime
import os
import pathlib
import logging
from typing import Dict

from dataSink import DataSink_file
from misc import SnapVariables
from misc import SdrVariables

logger = logging.getLogger('spectrum_logger')


def handle_snap_message(data_sink: DataSink_file, snap_config: SnapVariables,
                        new_config: Dict, sdr_config: SdrVariables,
                        thumb_dir: pathlib.PurePath) -> DataSink_file:
    """
    messages from UI
    We may change the snap object here, data_sink, due to changes in cf, sps or configuration

    :param data_sink: where snap data will go, may change
    :param snap_config: current snap state etc
    :param new_config: dictionary from a json string with new configuration for snap
    :param sdr_config: sdr config so we can get cf, sps etc
    :param thumb_dir: where thumbnails ended up for the web UI
    :return: None
    """
    # print(new_config)
    changed = False
    if new_config['baseFilename'] != snap_config.baseFilename:
        snap_config.baseFilename = new_config['baseFilename']
        changed = True

    if new_config['wavFlag'] != snap_config.wav_flag:
        snap_config.wav_flag = new_config['wavFlag']
        changed = True

    if new_config['snapState'] != snap_config.snapState:
        # only 'manual' type can change state here
        # don't set changed
        if snap_config.triggerType == "manual":
            snap_config.snapState = new_config['snapState']
            if snap_config.snapState == "start":
                snap_config.triggered = True
                snap_config.triggerState = "triggered"
            else:
                snap_config.triggered = False
                snap_config.triggerState = "wait"
                snap_config.snapState = "stop"

    if new_config['preTriggerMilliSec'] != snap_config.preTriggerMilliSec:
        snap_config.preTriggerMilliSec = new_config['preTriggerMilliSec']
        changed = True

    if new_config['postTriggerMilliSec'] != snap_config.postTriggerMilliSec:
        snap_config.postTriggerMilliSec = new_config['postTriggerMilliSec']
        changed = True

    if new_config['triggerType'] != snap_config.triggerType:
        snap_config.triggerType = new_config['triggerType']  # don't set changed

    # has any non-snap setting changed
    if sdr_config.real_centre_frequency_hz != snap_config.cf or sdr_config.sample_rate != snap_config.sps:
        snap_config.cf = sdr_config.real_centre_frequency_hz
        snap_config.sps = sdr_config.sample_rate
        changed = True

    if new_config['deleteFileName'] != "":
        delete_file(new_config['deleteFileName'], thumb_dir)
        snap_config.directory_list = list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)

    if changed:
        data_sink = DataSink_file.FileOutput(snap_config, SnapVariables.SNAPSHOT_DIRECTORY)
        # following may of been changed by the sink
        if data_sink.get_post_trigger_milli_seconds() != snap_config.postTriggerMilliSec or \
                data_sink.get_pre_trigger_milli_seconds() != snap_config.preTriggerMilliSec:
            snap_config.postTriggerMilliSec = data_sink.get_post_trigger_milli_seconds()
            snap_config.preTriggerMilliSec = data_sink.get_pre_trigger_milli_seconds()
            sdr_config.error += f"Snap modified to maximum file size of {snap_config.max_file_size / 1e6}MBytes"

    return data_sink


def delete_file(filename: str, thumb_dir: pathlib.PurePath) -> None:
    """
    Delete a snapshot file

    :param filename: The filename we wish to delete, this will be the filename of the samples
    :param thumb_dir: Where the thumbnail is stored
    :return: None
    """
    filename = os.path.basename(filename)
    file = pathlib.PurePath(SnapVariables.SNAPSHOT_DIRECTORY, filename)
    file_png = pathlib.PurePath(SnapVariables.SNAPSHOT_DIRECTORY, filename + ".png")
    thumb_png = pathlib.PurePath(thumb_dir, filename + ".png")
    try:
        os.remove(file)
        try:
            os.remove(file_png)
            os.remove(thumb_png)
        except OSError:
            pass  # Don't care if we fail to delete the png files
    except OSError as msg:
        err = f"Problem with delete of {filename}, {msg}"
        logger.error(err)


def list_snap_files(directory: pathlib.PurePath) -> []:
    """
    List the files in the provided directory, exclude png and hidden files

    :param directory:
    :return: List of files
    """
    directory_list = []
    for path in pathlib.Path(directory).iterdir():
        if not path.name.startswith(".") and not path.name.endswith("png"):
            # We will not match the time in the filename as it is recording the trigger time
            # getctime() may also return the last modification time not creation time (dependent on OS)
            timestamp = int(os.path.getctime(path))
            date_time = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d_%H-%M-%S')
            directory_list.append((path.name, str(round(os.path.getsize(path) / (1024 * 1024), 3)), date_time))
    # sort so that most recent is first
    directory_list.sort(reverse=True, key=lambda a: a[2])
    return directory_list
