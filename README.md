# A Python/webUI RF spectrum analyser

Support for rtlsdr, pluto, funcube, sdrplay (soapy), audio, socket, file.

![Screenshot](screenShot_web.png)

* Python processing.
* Web javascript UI.
* Spectrums are done at the sample rate.
* Useful for detecting short bursting signals.
* Plugin architecture for sources and analysis of spectrums.
* Snapshot file upon an event, currently a manual trigger.
* Has a web based UI that can be used to take measurements on the spectrum.
* Processing runs with no web client attached.

This was an exercise in writing some python which expanded into providing a web based UI. The fft computations are done
by libraries in Python, so not the fastest.

If you have some sort of sdr working with other tools then after installing the required python dependencies it should
just work.

Performance depends on your machine and how the supporting fft libraries were compiled. I have certainly kept up with
streams of data at over 3Msps.

## Input modules:

* audio - Useful for testing, in linux requires 'sudo apt-get install libportaudio2'
* file - wav and raw binary supported, all files must be in the snapshot directory
* pluto (IP)  - Analog devices pluto SDR, 70MHz to 6GHz with wide open front end
* rtlsdr - USB source
* rtltcp - rtl over tcp
* socket - A stream of IQ samples
* funcube - Pro and pro+ as audio devices, hid control supported in Linux only
* soapy - Support for sdrplay under Linux

## Input data IQ types:

* 8bit offset binary
* 8bit 2's complement
* 16bit 2's complement little endian (x86)
* 16bit 2's complement big endian
* 32bit ieee float little endian
* 32bit ieee float big endian

## Problems

* If the programme exceptions immediately, check the dependencies.
* funcube will exception under windows when closed, which we do when changing the source

## Installation - windows

Should be similar to the linux install, but

* No support for hid control of funcube, we can stream samples but not control the device.
* No support for sdrplay, as we don't have SoapySDR support - don't know how to install on windows.

## Installation - linux

    cd ~
    git clone https://github.com/naj1024/pyspectrum.git

Edit requirements.txt for required input sources.

    vi ./pyspectrum/src/requirements.txt

I'm using pipenv for a virtual environment.

    pipenv shell
    pip install -r ./pyspectrum/src/requirements.txt

Run, then connect to localhost:8080 in a browser

    python3 ./pyspectrum/src/SpectrumAnalyser.py

## Complete raspberry pi install, RPI-5
     
    # From fresh install of bookworm on RP-5 (January 2024)
        $ sudo apt update
        $ sudo apt upgrade
    
    # python virtual environement     
        $ sudo apt install pipenv
        
    # rtlsdr hardware support
        $ sudo apt install librtlsdr0
        $ sudo apt install librtlsdr-dev
        $ sudo apt install rtl-sdr
        $ sudo usermod -a -G plugdev pi
    
    # pluto hardware support
        $ sudo apt install libiio0 libiio-utils
         
    # audio hardware support
        $ sudo apt install libportaudio2
    
    # hardware support for control support of funcube devices
        $ sudo apt install libhidapi-hidraw0 libhidapi-libusb0
        
    # sdrplay hardware support
        $ chmod +x SDRplay_RSP_API-Linux-3.12.1.run
        $ sudo ./SDRplay_RSP_API-Linux-3.12.1.run
        $ sudo systemctl status sdrplay
        $ sudo systemctl enable sdrplay
    
    # Soapy for sdrplay, because distro soapy does not include sdrplay
        # dependancies for soapy build
        $ sudo apt install cmake g++ libpython3-dev python3-numpy swig
        
        ## sdrplay base
        $ cd
        $ git clone https://github.com/pothosware/SoapySDR.git
        $ cd SoapySDR
        $ mkdir build
        $ cd build
        $ cmake ..
        $ make
        $ sudo make install
        $ sudo ldconfig
        $ SoapySDRUtil --info    # no modules found
        
        ## Soapy sdrplay module
        $ cd ../..
        $ git clone https://github.com/SDRplay/SoapySDRPlay.git
        $ cd SoapySDRPlay
        $ mkdir build
        $ cd build
        $ cmake ..
        $ make
        $ sudo make install
        $ sudo ldconfig
        $ SoapySDRUtil --info    # libsdrPlaySupport.so module found
        
        ## test how fast raw driver can go, change sample rate 
        $ SoapySDRUtil --rate=8e6 --direction=RX --args="driver=sdrplay"
    
        ## Soapy rtlsdr module
        $ git clone https://github.com/pothosware/SoapyRTLSDR.git
        $ cd SoapyRTLSDR/
        $ mkdir build
        $ cd build
        $ cmake ..
        $ make
        $ sudo make install
        $ SoapySDRUtil --info    # librtlsdrSupport.so module found
        
    # python environment search paths for soapy
        $ vi ~/.local/share/virtualenvs/pi-xxxxxx/pyvenv.cfg
            # allow search on system packages as Soapy has installed them there
            include-system-site-packages = true
        
    # let things sort themselves out, libraries, rules, groups etc
        $ sudo reboot
       
    # test for working rtlsdr devices, as normal user
        $ rtl_test
       
    # clone the pyspectrum repository
        $ cd
        $ git clone https://github.com/naj1024/pyspectrum.git
        $ cd pyspectrum
        $ git checkout flask
    
        # install python requirements
        $ cd
        $ pipenv shell
        $ cd pyspectrum/src
        
        # edit for the features you require 
        $ vi requirements.txt
        $ pip install -r ./requirements.txt
        
        ## Run the spectrum anlayser
        $ python3 ./SpectrumAnalyser.py -vvv
        web server port 8080
        web socket port 8081
         * Serving Flask app 'webUI.FlaskInterface'
         * Debug mode: off
        
        ctr-c
            
        # check logs for errors
        $ cat ./logs/SpectrumAnalyser.log
        
        
    #############
    # Alternative soapy drivers 
    #   - distrubution provided 
    #   - no sdrplay
    #######
    $ sudo apt install soapysdr-module-all
    $ sudo apt install python3-soapysdr	
    
    $ vi ~/.local/share/virtualenvs/pi-xxxxxx/pyvenv.cfg
        # allow search on system packages as Soapy has installed them there
        include-system-site-packages = true
        
    # check that path includes system path python3/dist-packages
    $ pi@pi5:~ $ pipenv shell
    Launching subshell in virtual environment...
    pi@pi5:~ $  . /home/pi/.local/share/virtualenvs/pi-xxxxxx/bin/activate
    (pi) pi@pi5:~ $ python3.11 -c "import sys; print('\n'.join(sys.path))"
    
    /usr/lib/python311.zip
    /usr/lib/python3.11
    /usr/lib/python3.11/lib-dynload
    /home/pi/.local/share/virtualenvs/pi-xxxxxx/lib/python3.11/site-packages
    /usr/local/lib/python3.11/dist-packages
    /usr/lib/python3/dist-packages
    /usr/lib/python3.11/dist-packages
    (pi) pi@pi5:~ $ exit

	   


# Soapy support - linux

The easiest way to get SoapySDR support is to install it from your distributions repository.
Distributions may not include the soapy driver you need, see above for source build instead.

    $ apt install python3-soapysdr
    $ dpkg -L dpkg -L python3-soapysdr

then your virtual environment searches the system paths as well, say it is called sid-xxxx

    $ vi ~/.local/share/virtualenvs/pi-xxxx/pyvenv.cfg
		# allow search on system packages as Soapy has installed them there
		include-system-site-packages = true
    
## TODO

* hackrf input would be nice to try, don't have one :(
* Detect and record automatically

## Tested with the following:

    Windows: audio, file, pluto, rtlsdr, rtltcp, socket, funcube
    Linux  : audio, file, pluto, rtlsdr, rtltcp, socket, funcube
             soapy(audio, rtlsdr, sdrplay)
    
    On windows make sure you have the correct rlibrtlsdr.dll for your python 32bit/64bit

## Comand line Examples - generally just need the first one

Some examples for running from command line, from a pipenv shell prompt

    python ./SpectrumAnalyser.py         - Then goto http://127.0.0.1:8080 and configure the source

    python ./SpectrumAnalyser.py -h      - help

    python ./SpectrumAnalyser.py -i?     - list input sources that are available

    python ./SpectrumAnalyser.py -vvv     - max debug output in logs/SpectrumAnalyser.log

Some default input selections, you normally select through web interface:

      python ./SpectrumAnalyser.py -ipluto:192.168.2.1 -c433.92e6 -s600e3   - pluto at 433MHz and 600ksps
  
      python ./SpectrumAnalyser.py -ipluto:192.168.2.1 -c433.92e6 -s1e6 
                              --plugin analysis:peak:threshold:12 
                              --plugin report:mqtt:broker:192.168.0.101     - detect and log signals
  
      python ./SpectrumAnalyser.py -ifile:test.wav -c433.92e6    - a test wav file
  
      python ./SpectrumAnalyser.py -iaudio:1 -s48e3 -iaudio:1    - audio input 
  
      python ./SpectrumAnalyser.py -irtlsdr:kk -c433.92e6 -s1e6   - rtlsdr

    SOAPY:
      python ./src/SpectrumAnalyser.py -isoapy:audio -s48000 -c0  - soapy input
      python ./src/SpectrumAnalyser.py -isoapy:sdrplay -s2e6 c433.92e6 

## Dependencies

The following python modules should be installed. Optional ones provide specific capabilities.

    Required:
        numpy
        websockets
        matplotlib
        
    Testing:
        pytest
        
    Optional:
        scipy       - another FFT library
        pyfftw      - another FFT library, faster above 8k size (for me)
        pyadi-iio   - pluto device
        iio         - pluto device
        pyrtlsdr    - rtlsdr devices
        sounddevice - audio and funcube devices
        soapysdr    - soapy support
        paho-mqtt   - mqtt plugin (client)
        hid         - funcube control through usb hid, linux only?
        sigmf       - sigmf file support

## AD936x pluto XO support

We can add support for pluto frequency correction in ppm by adding the following to the file ad936x.py when pyadi-iio is
installed. You should find the ad936x.py file under the adi directory in the site packages traversed by your
environment. Insert the lines in the ad9364 class definitions.

    @property
    def xo_correction(self):
        return self._get_iio_dev_attr("xo_correction")

    @xo_correction.setter
    def xo_correction(self, value):
        self._set_iio_dev_attr_str("xo_correction", value)
