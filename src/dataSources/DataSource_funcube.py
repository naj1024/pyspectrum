"""
FUNcube dongle input wrapper

Copy of the audio input module with a few changes for the FUNcube

Devices FUNcube Dongle V1.0 - funcube pro  0x04d8,0xfb56
Devices FUNcube Dongle V2.0 - funcube pro+ 0x04d8,0xfb31

Under Linux
=================
We need to add a udev rule to enable an ordinary user to control the funcube through the usb hid interface
    As root:
    # vi /etc/udev/rules.d/50-funcube.rules
        SUBSYSTEMS=="usb", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="fb56", GROUP="usergroup", MODE="0666"
        SUBSYSTEMS=="usb", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="fb31", GROUP="usergroup", MODE="0666"

    # udevadm control --reload

    The user belongs to group usergroup

    For library support we need libhidapi-libusb.so.0 ? may of been for pyhidapi and not hid

Under Windows
===============
Failed to get this to work for hid control yet, can't find hidapi.dll. Tried putting it everywhere.

Unable to load any of the following libraries:libhidapi-hidraw.so libhidapi-hidraw.so.0
 libhidapi-libusb.so libhidapi-libusb.so.0 libhidapi-iohidmanager.so libhidapi-iohidmanager.so.0
 libhidapi.dylib hidapi.dll libhidapi-0.dll


FUNcube pro ?
=====================
    Guaranteed frequency range: 150kHz to 240MHz and 420MHz to 1.9GHz
    TCXO specified at 0.5ppm (in practice about 1.5ppm)
    192kHz sampling rate
    Eleven discrete hardware front end filters including:
        6MHz 3dB bandwidth (10MHz at -40dB) SAW filter for the 2m band.
        20MHz 3dB bandwidth (42MHz at -40dB) SAW filter for the 70cm band
        Third- and fifth-order LC bandpass filters for other bands
    Front end LNA OIP3 30dB
    Integrated 5V bias T switchable from software

  CONFIGURATION 1: 150 mA ==================================
   bLength              :    0x9 (9 bytes)
   bDescriptorType      :    0x2 Configuration
   wTotalLength         :   0x84 (132 bytes)
   bNumInterfaces       :    0x3
   bConfigurationValue  :    0x1
   iConfiguration       :    0x0
   bmAttributes         :   0x80 Bus Powered
   bMaxPower            :   0x4b (150 mA)
    INTERFACE 0: Audio =====================================
     bLength            :    0x9 (9 bytes)
     bDescriptorType    :    0x4 Interface
     bInterfaceNumber   :    0x0
     bAlternateSetting  :    0x0
     bNumEndpoints      :    0x0
     bInterfaceClass    :    0x1 Audio
     bInterfaceSubClass :    0x1
     bInterfaceProtocol :    0x0
     iInterface         :    0x0
    INTERFACE 1: Audio =====================================
     bLength            :    0x9 (9 bytes)
     bDescriptorType    :    0x4 Interface
     bInterfaceNumber   :    0x1
     bAlternateSetting  :    0x0
     bNumEndpoints      :    0x0
     bInterfaceClass    :    0x1 Audio
     bInterfaceSubClass :    0x2
     bInterfaceProtocol :    0x0
     iInterface         :    0x0
    INTERFACE 1, 1: Audio ==================================
     bLength            :    0x9 (9 bytes)
     bDescriptorType    :    0x4 Interface
     bInterfaceNumber   :    0x1
     bAlternateSetting  :    0x1
     bNumEndpoints      :    0x1
     bInterfaceClass    :    0x1 Audio
     bInterfaceSubClass :    0x2
     bInterfaceProtocol :    0x0
     iInterface         :    0x0
      ENDPOINT 0x81: Isochronous IN ========================
       bLength          :    0x9 (7 bytes)
       bDescriptorType  :    0x5 Endpoint
       bEndpointAddress :   0x81 IN
       bmAttributes     :    0x1 Isochronous
       wMaxPacketSize   :  0x184 (388 bytes)
       bInterval        :    0x1
    INTERFACE 2: Human Interface Device ====================
     bLength            :    0x9 (9 bytes)
     bDescriptorType    :    0x4 Interface
     bInterfaceNumber   :    0x2
     bAlternateSetting  :    0x0
     bNumEndpoints      :    0x2
     bInterfaceClass    :    0x3 Human Interface Device
     bInterfaceSubClass :    0x0
     bInterfaceProtocol :    0x0
     iInterface         :    0x0
      ENDPOINT 0x82: Interrupt IN ==========================
       bLength          :    0x7 (7 bytes)
       bDescriptorType  :    0x5 Endpoint
       bEndpointAddress :   0x82 IN
       bmAttributes     :    0x3 Interrupt
       wMaxPacketSize   :   0x40 (64 bytes)
       bInterval        :    0x1
      ENDPOINT 0x2: Interrupt OUT ==========================
       bLength          :    0x7 (7 bytes)
       bDescriptorType  :    0x5 Endpoint
       bEndpointAddress :    0x2 OUT
       bmAttributes     :    0x3 Interrupt
       wMaxPacketSize   :   0x40 (64 bytes)
       bInterval        :    0x1
"""

import queue
import logging
import time
import platform  # for detecting windows, as my portaudio core dumps on close (stop() actually does it)
from typing import Tuple

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "funcube"
help_string = f"{module_type}:Number \t- number of the input device e.g. {module_type}:1, '?' for list"
web_help_string = "Number - number of the input device e.g. 1. Use '?' for list"

try:
    import_error_msg = ""
    import sounddevice as sd
except ImportError as msg:
    sd = None
    import_error_msg = f"Info: {module_type} source has an issue, {str(msg)}"
    logging.info(import_error_msg)

try:
    # NOTE that pypi has pyhidapi and hid
    # Originally used pyhidapi but that is at least 6 years old.
    import hid
except ImportError as msg:
    hid = None
    logging.warn(f"Warning: {module_type} source has no ability to control device, {str(msg)}")


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# A queue for the audio streamer callback to put samples in to, 4 deep for low latency
audio_q = queue.Queue(4)


def audio_callback(incoming_samples: np.ndarray, frames: int, time_1, status) -> None:
    if status:
        if status.input_overflow:
            logger.error("audio input overflow")
        else:
            err = f"Error: {module_type} had a problem, {status}"
            logger.error(err)
            raise ValueError(err)

    # make complex array with left/right as real/imaginary
    # you should be feeding the audio LR with a complex source
    # frames is the number of left/right sample pairs, i.e. the samples
    complex_data = np.empty(shape=(frames,), dtype=np.complex64)

    for n in range(frames):
        complex_data[n] = complex(incoming_samples[n][0], incoming_samples[n][1])

    audio_q.put(complex_data.copy())


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float
                 ):
        """
        The audio input source

        :param source: Number of the device to use, or 'L' for a list
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: Not used
        :param sample_rate: Not used
        :param centre_frequency: Not used
        :param input_bw: The filtering of the input, may not be configurable
        """
        self._constant_data_type = "16tle"

        super().__init__(source, number_complex_samples, self._constant_data_type, sample_rate,
                         centre_frequency, input_bw)

        self._connected = False
        self._channels = 2  # we are really expecting stereo
        self._device_number = 0  # will be set in open
        self._audio_stream = None
        self._hid_device = None
        self._funcube_type = None
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        # sounddevice seems to require a reboot quite often before it works on windows,
        # probably driver problems after an OS sleep
        # Count number of queue emtpy events, along with sleep to get an idea if
        # something is broken
        self._empty_count = 0

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"No {module_type} support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._source == "?":
            self._audio_stream = None
            fun_cubes = ""
            all_sound_devices = sd.query_devices()
            device_number = 0  # count the device index
            for dev in all_sound_devices:
                if 'FUN' in dev.get('name'):
                    fun_cubes += f'{device_number} {dev.get("default_samplerate")} {dev.get("name")}\n'
                device_number = device_number + 1
            if len(fun_cubes) == 0:
                fun_cubes = f"No {module_type} detected"
            self._error = fun_cubes
            return False

        try:
            self._device_number = int(self._source)
        except ValueError:
            self._error += f"Illegal audio source number {self._source}"
            logger.error(self._error)
            raise ValueError(self._error)

        try:
            capabilities = sd.query_devices(device=self._device_number)
            if capabilities['max_input_channels'] != 2:
                raise ValueError(f"Unsupported number of channels {capabilities['max_input_channels']}")
            self._sample_rate_sps = capabilities['default_samplerate']  # we must use this rate
            self._bandwidth_hz = self._sample_rate_sps
            # is this funcube pro or pro+
            name = capabilities['name']
            if 'V2' in name:
                self._funcube_type = "pro+"
            elif 'V1' in name:
                self._funcube_type = "pro"
        except Exception as err_msg:
            msgs = f"{module_type} query error: {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            self._audio_stream = sd.InputStream(samplerate=self._sample_rate_sps,
                                                device=self._device_number,
                                                channels=self._channels,
                                                callback=audio_callback,
                                                blocksize=self._number_complex_samples,  # NOTE the size, not zero
                                                dtype="int16")
            self._audio_stream.start()  # required as we are not using 'with'

        except sd.PortAudioError as err_msg:
            msgs = f"{module_type} inputStream error: {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None
        except ValueError as err_msg:
            msgs = f"device number {self._source}, {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None
        except Exception as err_msg:
            msgs = f"device number {self._source}, {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None

        self._sample_rate_sps = self._audio_stream.samplerate  # actual sample rate
        logger.debug(f"Connected to {module_type} {self._device_number}")
        logger.info(f"Audio stream started ")
        self._connected = True

        # do we have hid support loaded
        if hid:
            try:
                if self._funcube_type == "pro":
                    self._hid_device = hid.Device(0x04d8, 0xfb56)
                elif self._funcube_type == "pro+":
                    self._hid_device = hid.Device(0x04d8, 0xfb31)
                else:
                    self._hid_device = None
            except Exception as hid_err:
                logger.error(f"hid problem: {hid_err}")
                self._hid_device = None
        else:
            self._hid_device = None

        self.set_centre_frequency_hz(self._centre_frequency_hz)
        return self._connected

    def close(self) -> None:
        if hid and self._hid_device:
            self._hid_device.close()
            self._hid_device = None

        if self._audio_stream:
            try:
                # under windows portaudio exceptions with fatal results
                if platform.system() != 'Windows':
                    self._audio_stream.stop()
                    self._audio_stream.close(ignore_errors=True)
                else:
                    self._error = f"{module_type} on Windows can not be closed properly"
                    logger.error(self._error)
                    # attempts to stop & close will cause python to exit
                    # Assertion failed!
                    # Program: C:\.....\Local\Programs\Python\Python38-32\python.exe
                    # File: src/hostapi/wdmks/pa_win_wdmks.c, Line 6351
                    # Expression: !stream->streamActive
            except Exception as err:
                self._error = f"{module_type} close error, {err}"
        self._connected = False

    def set_sample_rate_sps(self, sr: float) -> None:
        self._error = f"{module_type} can't change sample rate from {self._sample_rate_sps}"

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def set_centre_frequency_hz(self, cf: float) -> None:
        self._centre_frequency_hz = cf
        if hid and self._hid_device:
            # same as https://github.com/csete/fcdctl/blob/master/fcdhidcmd.h
            # FCD_CMD_APP_SET_FREQ_KHZ = 100
            FCD_CMD_APP_SET_FREQ_HZ = 101
            # FCD_CMD_APP_GET_FREQ_HZ = 102

            command = bytearray(65)  # 65bytes always
            command[0] = 0
            command[1] = FCD_CMD_APP_SET_FREQ_HZ
            cfi = int(cf)
            # frequency in little endian byte order
            command[2] = (cfi & 0xff)
            command[3] = ((cfi >> 8) & 0xff)
            command[4] = ((cfi >> 16) & 0xff)
            command[5] = ((cfi >> 24) & 0xff)
            try:
                self._hid_device.write(bytes(command))  # write takes string/bytes ?!?
            except Exception as hid_err:
                self._error = f"{module_type} failed to set frequency via usb hid command, {hid_err}"
                logger.error(self._error)

    def set_bandwidth_hz(self, bw: float) -> None:
        self._error = f"{module_type} can't change bandwidth"

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected:
            global audio_q
            try:
                complex_data = audio_q.get(block=False)
                rx_time = self.get_time_ns()
                self._empty_count = 0
                complex_data /= 32767.0  # normalise the data, assumes 16bit
            except queue.Empty:
                time.sleep(0.001)
                self._empty_count += 1
                if self._empty_count > 10000:
                    msgs = f"{module_type} not producing samples, reboot required?"
                    self._error = str(msgs)
                    logger.error(msgs)
                    print(msgs)
                    self._empty_count = 0
                    raise ValueError(msgs)

        return complex_data, rx_time
