import datetime
import logging
import os
import pathlib

from misc import global_vars

logger = logging.getLogger('spectrum_logger')


def delete_file(filename: str, thumb_dir: pathlib.PurePath) -> None:
    """
    Delete a snapshot file

    :param filename: The filename we wish to delete, this will be the filename of the samples
    :param thumb_dir: Where the thumbnail is stored
    :return: None
    """
    filename = os.path.basename(filename)
    file = pathlib.PurePath(global_vars.SNAPSHOT_DIRECTORY, filename)
    file_png = pathlib.PurePath(global_vars.SNAPSHOT_DIRECTORY, filename + ".png")
    thumb_png = pathlib.PurePath(thumb_dir, filename + ".png")
    # sigmf files have an additional metadata file
    sigmf_meta = None
    if 'sigmf-data' in filename:
        sigmf_meta = str(filename)
        sigmf_meta = sigmf_meta.replace('sigmf-data', 'sigmf-meta')
        sigmf_meta = pathlib.PurePath(global_vars.SNAPSHOT_DIRECTORY, sigmf_meta)

    for delete in (file, file_png, thumb_png, sigmf_meta):
        try:
            if delete:
                os.remove(delete)
        except OSError as msg:
            err = f"Problem with delete of {filename}, {msg}"
            logger.error(err)


def list_snap_files(directory: pathlib.PurePath) -> []:
    """
    List the data sample files in the provided directory
    Exclude png, hidden and metadata files

    :param directory:
    :return: List of files
    """
    directory_list = []
    for path in pathlib.Path(directory).iterdir():
        if not path.name.startswith("."):
            ignore_extensions = ['png', 'sigmf-meta']
            excluded = False
            for ext in ignore_extensions:
                if path.name.endswith(ext):
                    excluded = True
            if not excluded:
                # We will not match the time in the filename as it is recording the trigger time
                # getctime() may also return the last modification time not creation time (dependent on OS)
                timestamp = int(os.path.getctime(path))
                date_time = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d_%H-%M-%S')
                directory_list.append((path.name, str(round(os.path.getsize(path) / (1024 * 1024), 3)), date_time))
    # sort so that most recent is first
    directory_list.sort(reverse=True, key=lambda a: a[2])
    return directory_list
