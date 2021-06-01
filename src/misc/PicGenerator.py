"""
Generate pictures of all digitised file in the snapshot directory
Put thumbnails in the web thumbnail directory

This is a separate process that will run until the main program exits

"""

import multiprocessing
import logging
import signal
import time
import os
import pathlib

from misc import SpectrumPicture
from misc import global_vars

# for logging
logger = logging.getLogger(__name__)


class PicGenerator(multiprocessing.Process):

    def __init__(self, snap_dir: pathlib.PurePath, web_thumb_dir: pathlib.PurePath, log_level: int):
        """
        Generate pictures, png, of each snapshot file

        :param snap_dir: Where the snapshots are
        :param web_thumb_dir: Where thumbnails for the web are to go
        :param log_level: logging
        """

        multiprocessing.Process.__init__(self)
        self._snap_dir = snap_dir
        self._thumb_dir = web_thumb_dir
        self._log_level = log_level
        self._shutdown = False

    def shutdown(self):
        logger.debug("PicGenerator Shutting down")
        self._shutdown = True

    def signal_handler(self, sig, __):
        self.shutdown()

    def run(self):
        global logger
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__+".log")
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
        # but it can send us a signal, then we can shutdown our self
        signal.signal(signal.SIGINT, self.signal_handler)

        logger.info("Pic generator started")
        logger.info(f"paths '{self._snap_dir}'")
        logger.info(f"thumbs '{self._thumb_dir}'")

        if SpectrumPicture.can_create_pictures():
            gen = SpectrumPicture.SpectrumPicture(str(self._thumb_dir))
            while not self._shutdown:
                try:
                    # get all the non hidden and non png files in snapshot dir
                    for path in pathlib.Path(self._snap_dir).iterdir():
                        filename = os.path.basename(path)
                        if not filename.startswith(".") and not filename.endswith("png"):
                            # if png does not exist then create one
                            png_filename = pathlib.PurePath(path.parent, path.name+".png")
                            if not os.path.isfile(png_filename):
                                try:
                                    _ = gen.create_picture(path)  # returns True if managed to create picture
                                except ValueError as msg:
                                    logger.error(f"PicGenerator {msg}")

                    time.sleep(1)  # check every second

                except Exception as msg:
                    logger.error(f"PicGenerator {msg}")
                    time.sleep(1)
        else:
            logger.error("Cant create spectral pictures, spectrumPicture failed")

        logger.error("Process exited")
        return
