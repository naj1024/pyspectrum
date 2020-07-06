# A Python spectrum analyser 

Takes raw IQ samples from some sdr source to give a live spectrum with optional spectrogram.

This was an exercise in writing some python. There are speed penalties in keeping to python in this. 
Getting the different SDR platforms to work is through libraries, some were tested on windows, some 
were tested on Ubuntu Linux. Getting a driver to work can be challenging, gnu-radio even has support 
that makes use outside gnu-radio almost impossible (iio).

Overall it gave me an idea of what the various sdr platforms have to do. It would be nice to use
web sockets to implement a different spectrum/spectrogram output. There are various examples that use
web sockets around.

The display is fairly rudimentary, implemented in matplotlib. There are various mouse controlled
options. The display runs as a separate process (not thread) so that we don't have problems with
the display taking processing time from the input data.

Speed wise it will depend on your machine. I have certainly kept up with streams of data at over 2Msps.
The display gets updated between 10 and 20fps.

The idea is to run real time, i.e. we are going to compute an FFT for the sample rate given and 
just update the display when we can. We remember all FFT results and do peak holding so that no peak
is missed on the display. 

How long the underlying FFT takes to compute will depend on how the underlying libraries are built
and configured. Each time the fft size changes we test all the available fft options to see which is 
tha fastest. FFTW seems, on my Ubuntu VM, to be the slowest until you hit 8k - but then i have not 
installed any of the fft libraries from source.

The slowest parts are: converting bytes into floats, re-ordering the fft bins for display, and of
course computing the the fft. It would be good to have a faster way of converting raw integer samples
to complex 32 bit floats.

The support for various input devices is a plugin architecture. If the python support for an input 
device is not available it cannot be used.

There is a separate plugin architecture for dealing with FFT results. With this you can add processing
to look for spectral spikes etc on the FFT bin results.

##Tested with the following:

    Windows: audio, file, pluto (IP), rtltcp, socket
    Linux  : audio, file, pluto (IP), rtlsdr, rtltcp, soapy(audio, rtlsdr, sdrplay), socket
    
## Examples

Some examples for running from command line, drop the --ignore-gooey if you don't have it installed.

python ./SpectrumAnalyser.py --ignore-gooey -H

python ./SpectrumAnalyser.py --ignore-gooey  -i?

python ./SpectrumAnalyser.py --ignore-gooey -ipluto:192.168.2.1 -c433.92e6 -s600e3 -E -F1024

python ./SpectrumAnalyser.py --ignore-gooey  -ipluto:192.168.2.1 -c433.92e6 -s1e6 -E --plugin analysis:peak:threshold:12 
                          --plugin report:mqtt:broker:192.168.0.101 

python ./SpectrumAnalyser.py --ignore-gooey  -ifile:test.wav -LE -W7.5 -c433.92e6

python ./SpectrumAnalyser.py --ignore-gooey  -ifile:test.cf433.92.cplx.600000.16le -LE -W7

python ./SpectrumAnalyser.py --ignore-gooey  -iaudio:1 -s48e3 -F1024 -DE -c0 -iaudio:1

python ./SpectrumAnalyser.py -irtlsdr:kk -c433.92e6 -s1e6 -E

python ./src/SpectrumAnalyser.py -isoapy:audio -s48000 -c0 -E

python ./src/SpectrumAnalyser.py -isoapy:sdrplay -s2e6 c433.92e6 -F2048 -E


## Dependencies

The following python modules should be installed. Optional ones provide specific capabilities.

    Required:
        numpy
        matplotlib
        
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
        gooey       - simple UI over the comamnd line options


## Raspberry Pi

This will run a raspberry pi, but **very** slowly.

The following was done on a not very clean V4.2 image from https://github.com/luigifreitas/pisdr-image
  
    uname -a 
    Linux pisdr 4.19.75-v7+ #1270 SMP Tue Sep 24 18:45:11 BST 2019 armv7l GNU/Linux
    
    cat /etc/debian_version 
    10.2
    
    cat /proc/device-tree/model
    Raspberry Pi 3 Model B Rev 1.2

    sudo apt install pipenv python-dev libatlas-base-dev python3-tk 

    cd
    tar -zxvf SpectrumAnalyser.tgz
    cd SpectrumAnalyser
    pipenv shell
    pipenv install matplotlib scipy pyrtlsdr sounddevice paho-mqtt

    # Assuming libiio is installed find a copy of iio.py and copy to your environment 
    cp ./libiio/build/bindings/python/iio.py ~/.local/share/virtualenvs/SpectrumAnalyser-cRKFuvKh/lib/python3.7/    
    pipenv install pyadi-iio

    python3 ./src/SpectrumAnalyser.py -i?
    Available sources: ['file', 'pluto', 'rtlsdr', 'socket', 'audio']
    file:Filename 	- Filename, binary or wave, e.g. file:./xyz.cf123.4.cplx.200000.16tbe
    pluto:IP 	    - The Ip or resolvable name of the Pluto device, e.g. pluto:192.168.2.1
    rtlsdr:Name 	- Name is anything, e.g. rtlsdr:abc
    socket:IP@port 	- The Ip or resolvable name and port on a server, e.g. socket:192.168.2.1@12345
    audio:Number 	- number of the input device e.g. audio:1, '?' for list

    NOTE: pipenv failed to install:
          pyfftw   - Breaks during install, compile problems?
          soapysdr - No matching distribution
          gooey    - Attempts to compile wx and fails
          
    NOTE: 'apt' will install python-fftw but that is not pyfftw, but there is python-pyfftw-doc !?
          There appears to be no support for fftw through pyfftw for python3 on this Linux distro

## TODO
 
    * Convert inputs to a streaming interfaces.
    * Make a proper GUI, maybe web based.
    * Add control back from the display process.
    * Allow retune of CF, sample rate and FFT size.
    * Drop receiver outputs