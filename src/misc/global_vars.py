import os
import pathlib

log_dir = "logs"  # relative to src directory
snapshot_directory_name = "snapshots"  # relative to src directory

# if the snapshots directory name is changed then you must edit main.js as well updateSnapFileList()
SNAPSHOT_DIRECTORY = pathlib.PurePath(f"{os.path.dirname(__file__)}", "..",
                                      "..", snapshot_directory_name)

# if the thumbnails directory name is changed then you must edit main.js as well updateSnapFileList()
THUMBNAILS_DIRECTORY = pathlib.PurePath(f"{os.path.dirname(__file__)}", "..",
                                      "..", snapshot_directory_name, "thumbnails")
