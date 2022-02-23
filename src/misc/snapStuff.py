import datetime
import logging
import os
import pathlib

from misc import SnapVariables

logger = logging.getLogger('spectrum_logger')


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
        try:
            os.remove(file)
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
