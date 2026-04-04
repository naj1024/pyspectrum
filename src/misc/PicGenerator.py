"""
Generate pictures of all digitised file in the snapshot directory
Put thumbnails in the web thumbnail directory

This is a separate process that will run until the main program exits

"""

import logging
import multiprocessing
import os
import pathlib
import signal
import time

from misc import SpectrumPicture
from misc import global_vars

# for logging
logger = logging.getLogger(__name__)


class PicGenerator(multiprocessing.Process):

    def __init__(self, log_level: int):
        """
        Generate pictures, png, of each snapshot file

        :param log_level: logging
        """

        multiprocessing.Process.__init__(self)
        self._log_level = log_level
        self._shutdown = False

    def shutdown(self):
        logger.debug("PicGenerator Shutting down")
        self._shutdown = True

    def signal_handler(self, _sig, __):
        self.shutdown()

    def run(self):
        global logger
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")
        # define file handler and set formatter
        file_handler = logging.FileHandler(log_file, mode="w")
        formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                      datefmt="%Y-%m-%d %H:%M:%S UTC")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logger.setLevel(self._log_level)

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # but it can send us a signal, then we can shut down our selves
        signal.signal(signal.SIGINT, self.signal_handler)

        logger.info("Pic generator started")
        logger.info(f"paths '{global_vars.SNAPSHOT_DIRECTORY}'")
        logger.info(f"thumbs '{global_vars.THUMBNAILS_DIRECTORY}'")

        if SpectrumPicture.can_create_pictures():
            gen = SpectrumPicture.SpectrumPicture()

            while not self._shutdown:
                try:
                    # get all the non-hidden and non png and meta files in snapshot dir
                    for full_path in pathlib.Path(global_vars.SNAPSHOT_DIRECTORY).iterdir():
                        if not full_path.is_file():
                            continue

                        filename = os.path.basename(full_path)
                        if not filename.startswith("."):
                            ignore_extensions = ['png', 'sigmf-meta']
                            excluded = False
                            for ext in ignore_extensions:
                                if filename.endswith(ext):
                                    excluded = True

                            if not excluded:
                                # if png does not exist then create one
                                png_filename = pathlib.PurePath(global_vars.THUMBNAILS_DIRECTORY,
                                                                os.path.basename(full_path)
                                                                + ".png")
                                if not os.path.isfile(png_filename):
                                    try:
                                        _ = gen.create_picture(full_path, global_vars.THUMBNAILS_DIRECTORY)
                                    except ValueError as msg:
                                        logger.error(f"PicGenerator failed on {full_path}, {msg}")

                except Exception as msg:
                    logger.error(f"PicGenerator failed somewhere, {msg}")

                time.sleep(1)  # check every second
        else:
            logger.error("PicGenerator, failed")

        logger.error("Process exited")
        return
