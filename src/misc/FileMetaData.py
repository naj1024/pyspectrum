"""
File open class which hopefully alos gets the meta data:

    metadata            source
    sample type         wav, filename
    sample rate         wav, filename
    centre frequency    filename

Only sampel type and sample rate will be recovered from a wav file.

Handles binary and wav files
Returns the open file and the associated metadata

"""
import logging
from io import TextIOWrapper
from typing import Tuple

from misc import wave_b as wave

logger = logging.getLogger('spectrum_logger')


def parse_filename(filename: str) -> Tuple[bool, str, bool, float, float]:
    """
    Parse a filename to extract its information

    Filename should end in .cplx.sample_rate.sample_type
    sometimes there is a centre frequency part as well, cf in MHz
    e.g
    xyz.cf1234.45.cplx.10000.16tle - little endian
    xyz.cf1234.01.real.10000.16tbe - real and big endian - not supported due to being real
    xyz.cf1234.23.cplx.10000.8be
    xyz.cf1234.cplx.10000.8be     - no digits after decimal point

    :param filename:
    :return: A tuple with an ok flag, and the type [8t,16tbe,16tle...], complex flag and sample rate in Hz
    """
    data_type: str = "16tle"
    complex_flag: bool = True
    sample_rate_hz = 1.0
    centre_frequency = 0.0
    ok: bool = False

    if filename:
        parts = [x.strip() for x in filename.split('.')]
        # work from end
        if len(parts) >= 4:
            # test.cf1234.0.cplx.1000.16tle -> ['test', 'cf1234', '0', 'cplx', '1000', '16tle']
            # test.cf1234.cplx.1000.16tle -> ['test', 'cf1234', 'cplx', '1000', '16tle']
            # test.cplx.1000.16tle -> ['test', 'cplx', '1000', '16tle']
            data_type = parts[-1]
            sample_rate = parts[-2]
            cplx = parts[-3]

            # cf parse is quite complex, first off is '.cf' in the filename
            if ".cf" in filename:
                indices = [i for i, part in enumerate(parts) if 'cf' in part]
                # if we find more than one .cf index then all bets are off
                if len(indices) == 1:
                    index = indices[0]  # where the .cf is in the list of parts
                    try:
                        cf = parts[index]
                        # is the next index real/cplx
                        if parts[index + 1] in ["cplx", "real"]:
                            # short cf with no decimal point
                            # ['test', '?', '?', ..., 'cf1234', 'cplx', '1000', '16tle']
                            # drop the 'cf'
                            centre_frequency = float(cf[2:]) * 1e6
                        else:
                            # long cf with a decimal point
                            #  ['test', '?', '?', ..., 'cf1234', '0', 'cplx', '1000', '16tle']
                            cf_decimal_fraction = parts[-4]
                            # drop the 'cf' and add in the decimal fraction part
                            cf = cf[2:] + "." + cf_decimal_fraction
                            centre_frequency = float(cf) * 1e6
                    except ValueError:
                        pass

            # check the fields make as much sense as we can here
            if cplx in ["cplx", "real"]:
                if cplx != "cplx":
                    complex_flag = False
                else:
                    # now convert the sample rate
                    try:
                        sample_rate_hz = float(sample_rate)
                        ok = True
                    except ValueError:
                        # don't exception just mark it as bad
                        ok = False

    return ok, data_type, complex_flag, sample_rate_hz, centre_frequency


class FileMetaData:

    def __init__(self, file_name: str):
        """
        Open and get meta data from a file, in filename or inbuilt, say from .wav format

        :param file_name: File name including path if required
        """
        self._filename = file_name
        self._has_meta_data = True  # default that we managed to recover meta data for this file

    def has_meta_data(self) -> bool:
        return self._has_meta_data

    def open(self) -> Tuple[bool, TextIOWrapper, bool, str, float, float]:
        """
        Open the file
        :return: A
                    boolean for successful recovery of sps,cf and type
                    file_handle of an open file
                    bool indicating a wav file
                    data_type, sps, centre_frequency
        """
        cf = 0.0  # default
        wav_file = False
        try:
            # first off, is this a wav file ?
            file = wave.open(self._filename, "rb")

            if file.getnchannels() != 2:
                msgs = f"wav file does not have 2 channels"
                logger.error(msgs)
                raise ValueError(msgs)

            sample_width = file.getsampwidth()
            data_type = file.getwformat()
            if sample_width == 2 and data_type == wave.WAVE_FORMAT_PCM:
                data_type = "16tle"  # wav files are little endian
            elif sample_width == 4 and data_type == wave.WAVE_FORMAT_IEEE_FLOAT:
                # assume (!) we wrote the file so it will be 32fle
                # wav module has no support for determining the format
                data_type = "32fle"  # wav files are little endian
            else:
                msgs = f"wav not supported, width {sample_width}, type {data_type}"
                logger.error(msgs)
                raise ValueError(msgs)

            # extract the cf from the filename if present
            ok, _, _, _, cf = parse_filename(self._filename)
            sps = file.getframerate()
            ok = True
            wav_file = True

        except wave.Error:
            # try again as a binary file
            try:
                file = open(self._filename, "rb")

                # see if we can set the meta data from the filename
                ok, data_type, complex_flag, sps, cf = parse_filename(self._filename)
                if ok:
                    if not complex_flag:
                        msgs = f"Unsupported input of type real from {self._filename}"
                        logger.error(msgs)
                        raise ValueError(msgs)
                else:
                    # don't set ok as these values were not recovered
                    # by not setting ok they can be overridden
                    cf = 0.0  # default
                    sps = 10000.0  # default
                    data_type = "16tle"  # default
                    self._has_meta_data = False  # say we don't know what this file is
                    # don't log these as the picture generator will keep trying
                    # msgs = f"No meta data recovered for raw binary file {self._filename}"
                    # logger.warning(msgs)

            except OSError as e:
                msgs = f"Failed to open file {self._filename}, {e}"
                logger.error(msgs)
                raise ValueError(msgs)

        except OSError as e:
            # catches things like file not found
            msgs = f"Failed to open file {self._filename}, {e}"
            logger.error(msgs)
            raise ValueError(msgs)

        logger.info(f"File {self._filename} opened with: cplx, {data_type}, "
                    f"{sps:.0f}sps, "
                    f"{cf:.0f}Hz")

        return ok, file, wav_file, data_type, sps, cf
