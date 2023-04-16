import os
import pathlib

log_dir = "logs"  # relative to src directory
snapshot_directory_name = "snapshots"  # relative to src directory

# put snapshot directory in webroot so we can make web links to allow downloading of the snaps
# if the snapshots directory name is changed then you must edit main.js as well updateSnapFileList()
SNAPSHOT_DIRECTORY = pathlib.PurePath(f"{os.path.dirname(__file__)}", "..",
                                      "webUI", "webroot", snapshot_directory_name)
