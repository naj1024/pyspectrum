# A Python RF spectrum analyser 

![Screenshot](screenShot_web.png)

* Takes digitised IQ samples from some source to give a live spectrum and spectrogram.
* Has a plugin architecture for sources and analysis of spectrums.
* Can snapshot IQ samples to file upon an event, currently a manual trigger.
* Has a web based UI that can be used to take measurements on the spectrum.

This was an exercise in writing some python which expanded into providing a web based UI. 
The fft computations are done by libraries in Python, so not the fastest.

Performance depends on your machine and how the supporting fft libraries were compiled. 
I have certainly kept up with streams of data at over 3Msps.

All the input sources are provided by python modules with the different SDR platforms are supported by
corresponding Python libraries gleaned from Pypi.

## Input modules:
* audio       - useful for testing
* file        - wav and raw binary supported, all files must be in snapshot directory
* pluto (IP)  - Analog devices pluto SDR on IP, 70Mhz to 6GHz but wide open
* rtlsdr      - Direct connection via USB
* rtltcp      - rtl over tcp
* socket      - any stream of IQ samples

There is soapy support for sdrplay, but i have failed to get this working again after an initial success.

## Input data IQ types:
* 8bit offset binary
* 8bit 2's complement
* 16bit 2's complement little endian (x86)
* 16bit 2's complement big endian
* 32bit ieee float little endian
* 32bit ieee float big endian

## Problems
* Converting input data to complex float32 numpy arrays. This takes a lot of time, which would be a lot 
  simpler in C/C++.
* Soapy support is not really tested anymore.
* sdrplay support relies on soapy.

## Tested with the following:
    Windows: audio, file, pluto (IP), rtlsdr, rtltcp, socket
    Linux  : audio, file, pluto (IP), rtlsdr, rtltcp, socket
             soapy(audio, rtlsdr, sdrplay)
    
    On windows make sure to use the correct rlibrtlsdr.dll for your python 32bit/64bit
    
    Since, once, getting soapy to work under Linux i have failed to replicate 
        this ever again - pity it was my only interface to an sdrplay device
        
## Examples
Some examples for running from command line

    python ./SpectrumAnalyser.py         - Then goto http://127.0.0.1:8080 and configure the source

    python ./SpectrumAnalyser.py -H      - help

    python ./SpectrumAnalyser.py -i?     - list input sources that are available

    python ./SpectrumAnalyser.py -ipluto:192.168.2.1 -c433.92e6 -s600e3   - pluto at 433MHz and 600ksps

    python ./SpectrumAnalyser.py -ipluto:192.168.2.1 -c433.92e6 -s1e6 
                            --plugin analysis:peak:threshold:12 
                            --plugin report:mqtt:broker:192.168.0.101     - detect and log signals

    python ./SpectrumAnalyser.py -ifile:test.wav -c433.92e6    - a test wav file

    python ./SpectrumAnalyser.py -iaudio:1 -s48e3 -iaudio:1    - audio input 

    python ./SpectrumAnalyser.py -irtlsdr:kk -c433.92e6 -s1e6   - rtlsdr

    python ./src/SpectrumAnalyser.py -isoapy:audio -s48000 -c0  - soapy input

    python ./src/SpectrumAnalyser.py -isoapy:sdrplay -s2e6 c433.92e6 


## Dependencies

The following python modules should be installed. Optional ones provide specific capabilities.

    Required:
        numpy
        websockets
        
    Testing:
        pytest
        
    Optional:
        scipy       - another FFT library
        pyfftw      - another FFT library, faster above 8k size
        pyadi-iio   - pluto device
        iio         - pluto device
        pyrtlsdr    - rtlsdr devices
        sounddevice - audio devices
        soapysdr    - soapy support
        paho-mqtt   - mqtt functionality (client)


```
pip3 install -r src/requirements.txt
```
