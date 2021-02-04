"""
File open class

Handles binary and wav files
Returns the open file and the associated metadata

"""
import wave
import logging
from typing import Tuple
from io import TextIOWrapper

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


class FileInput:

    def __init__(self, file_name: str):
        """
        File input class

        :param file_name: File name including path if required
        """
        self._filename = file_name

    def open(self) -> Tuple[bool, TextIOWrapper, bool, str, float, float]:
        """
        Open the file
        :return: A boolean to say we are successful, file_handle, bool for wav file, data_type, sps, centre_frequency
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
            if sample_width == 2:
                data_type = "16tle"  # wav files are little endian
            elif sample_width == 4:
                data_type = "32fle"  # wav files are little endian

                msgs = "wav does not have 2 bytes per i,q sample, 4 bytes complex"
                logger.error(msgs)
                raise ValueError(msgs)

            data_type = "16tle"  # wav files are little endian
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
                        msgs = f"Error: Unsupported input of type real from {self._filename}"
                        logger.error(msgs)
                        raise ValueError(msgs)
                else:
                    cf = 0.0  # default
                    sps = 1.0  # default
                    data_type = "16tle"  # default

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
