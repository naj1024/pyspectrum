/*
    The state of the SDR front end
*/

'use strict';

function basename(path) {
   return path.split(/[\\/]/).pop();
}

sdrState.prototype.setName = function(name) {
    this.name = name;
}

sdrState.prototype.setSdrFrequencyHz = function(freqHz) {
    this.sdrFrequencyHz = parseInt(freqHz);
}
sdrState.prototype.setFrequencyHz = function(freqHz) {
    this.frequencyRealHz = parseInt(freqHz);
}
sdrState.prototype.setFrequencyOffsetHz = function(freqHz) {
    this.frequencyOffsetHz = parseInt(freqHz);
    window.sessionStorage.setItem("frequencyOffsetHz", this.frequencyOffsetHz);
}
sdrState.prototype.setSps = function(sps) {
    this.sps = parseInt(sps);
}
sdrState.prototype.setFftSize = function(fftSize) {
    this.fftSize = parseInt(fftSize);
}
sdrState.prototype.setFftSizes = function(fftSizes) {
    this.fftSizes = fftSizes;
}
sdrState.prototype.setFftWindow = function(window) {
    this.window = window;
}
sdrState.prototype.setFftWindows = function(windows) {
    this.windows = windows;
}
sdrState.prototype.setInputSource = function(source) {
    this.source = source;
}
sdrState.prototype.setInputSourceParams = function(params) {
    if (this.source == "file") {
        this.sourceParams = basename(params);
        this.frequencyOffsetHz = 0.0;
    } else {
        this.sourceParams = params;
    }
}
sdrState.prototype.setDataFormat = function(format) {
    this.dataFormat = format;
}
sdrState.prototype.setAllowedFps = function(allowed) {
    this.fpsAllowed = allowed;
}
sdrState.prototype.setFps = function(fps) {
    this.fps = parseInt(fps.set);
    this.measuredFps = parseFloat(fps.measured);
}
sdrState.prototype.setGain = function(gain) {
    this.gain = parseInt(gain);
}
sdrState.prototype.setGainMode = function(gainMode) {
    this.gainMode = gainMode;
}
sdrState.prototype.setGainModes = function(gainModes) {
    this.gainModes = gainModes;
}
sdrState.prototype.setSdrBwHz = function(sdrBwHz) {
    this.sdrBwHz = parseInt(sdrBwHz);
}
sdrState.prototype.setPpmError = function(error) {
    this.ppmError = parseFloat(error);
}
sdrState.prototype.setDBmOffset = function(error) {
    this.dbmOffset = parseFloat(error);
}

////////////////////
// getters
///////
sdrState.prototype.getName = function() {
    return this.name;
}
sdrState.prototype.getSdrFrequencyHz = function() {
    return this.sdrFrequencyHz;
}
sdrState.prototype.getFrequencyHz = function() {
    return this.frequencyRealHz;
}
sdrState.prototype.getFrequencyOffsetHz = function() {
    return this.frequencyOffsetHz;
}
sdrState.prototype.getSps = function() {
    return this.sps;
}
sdrState.prototype.getFftSize = function() {
    return this.fftSize;
}
sdrState.prototype.getFftSizes = function() {
    return this.fftSizes;
}
sdrState.prototype.getFftWindow = function() {
    return this.window;
}
sdrState.prototype.getFftWindows = function() {
    return this.windows;
}
sdrState.prototype.getInputSource = function() {
    return this.source;
}
sdrState.prototype.getInputSourceParams = function() {
    return this.sourceParams;
}
sdrState.prototype.getInputSources = function() {
    return this.sources;
}
sdrState.prototype.getInputSourceHelps = function() {
    return this.sourceHelps;
}
sdrState.prototype.getInputSourceParamHelp = function(source) {
    return this.sourceHelps[source];
}
sdrState.prototype.getDataFormats = function() {
    return this.dataFormats;
}
sdrState.prototype.getDataFormat = function() {
    return this.dataFormat;
}
sdrState.prototype.getAllowedFps = function() {
    return this.fpsAllowed;
}
sdrState.prototype.getFps = function() {
    return this.fps;
}
sdrState.prototype.getMeasuredFps = function() {
    return this.measuredFps;
}
sdrState.prototype.getSourceConnected = function() {
    return this.sourceConnected;
}
sdrState.prototype.getGain = function() {
    return this.gain;
}
sdrState.prototype.getGainMode = function() {
    return this.gainMode;
}
sdrState.prototype.getGainModes = function() {
    return this.gainModes;
}
sdrState.prototype.getSdrBwHz = function() {
    return this.sdrBwHz;
}
sdrState.prototype.getLastDataTime = function() {
    return this.lastDataTime;
}
sdrState.prototype.getUiDelay = function() {
    return this.uiDelay;
}
sdrState.prototype.getReadRatio = function() {
    return this.readRatio;
}
sdrState.prototype.getHeadroom = function() {
    return this.headroom;
}
sdrState.prototype.getOverflows = function() {
    return this.overflows;
}
sdrState.prototype.getPpmError = function() {
    return this.ppmError;
}
sdrState.prototype.getDBmOffset = function() {
    return this.dbmOffset;
}
sdrState.prototype.setLastDataTime = function(last) {
    this.lastDataTime = last;
}
sdrState.prototype.setNextAckTime = function(next) {
    this.nextAckTime = next;
}
sdrState.prototype.setUiDelay = function(delay) {
    this.uiDelay = delay;
}
sdrState.prototype.setReadRatio = function(ratio) {
    this.readRatio = ratio;
}
sdrState.prototype.setHeadroom = function(headroom) {
    this.headroom = headroom;
}
sdrState.prototype.setOverflows = function(overflows) {
    this.overflows = overflows;
}

sdrState.prototype.setConfigFromJason = function(jsonConfig) {
    //console.log(jsonConfig);

    // this should only set the offset frequency initially, i.e. set on command line
    if (this.firstTime) {
        this.frequencyOffsetHz = parseInt(jsonConfig.conversion_frequency_hz);
        this.firstTime = false;
    }

    if (jsonConfig.digitiserFrequency != undefined){
        this.sdrFrequencyHz = parseInt(jsonConfig.digitiserFrequency);
    }

    if (jsonConfig.frequency != undefined) {
        this.frequencyRealHz = parseInt(jsonConfig.frequency.value);
        this.frequencyOffsetHz = parseInt(jsonConfig.frequency.conversion);
        spectrum.setCentreFreqHz(this.frequencyRealHz);
    }

    if (jsonConfig.digitiserSampleRate != undefined) {
        this.sps = parseInt(jsonConfig.digitiserSampleRate);
        spectrum.setSps(jsonConfig.digitiserSampleRate);
        spectrum.setSpanHz(jsonConfig.digitiserSampleRate);
    }

    if (jsonConfig.digitiserBandwidth != undefined) {
        this.sdrBwHz = parseInt(jsonConfig.digitiserBandwidth);
    }

    if (jsonConfig.fftSizes != undefined) {
        this.fftSizes = jsonConfig.fftSizes;
    }

    if (jsonConfig.fftSize != undefined) {
        this.fftSize = parseInt(jsonConfig.fftSize);
    }

    if (jsonConfig.fftWindow != undefined) {
        this.window = jsonConfig.fftWindow;
    }

    if (jsonConfig.fftWindows != undefined) {
        this.windows = jsonConfig.fftWindows;
    }

    if (jsonConfig.sources != undefined) {
        // todo: keep the source and help paired up
        let sourceArray = Object.entries(jsonConfig.sources);
        let sources = [];
        let sourceHelps = [];
        for (var src = 0; src < sourceArray.length; src++) {
            sources.push(sourceArray[src][0]);
            sourceHelps.push(sourceArray[src][1]);
        }
        this.sources = sources;
        this.sourceHelps = sourceHelps;
    }

    if (jsonConfig.source != undefined) {
        //let src = Object.entries(jsonConfig.source);
        this.source = jsonConfig.source.source;
        this.sourceConnected = jsonConfig.source.connected;
        if (this.source == "file") {
            this.sourceParams = basename(jsonConfig.source.params);
        } else {
            this.sourceParams = jsonConfig.source.params;
        }
    }

    if (jsonConfig.digitiserFormats != undefined) {
        this.dataFormats = jsonConfig.digitiserFormats;
    }

    if (jsonConfig.digitiserFormat != undefined) {
        this.dataFormat = jsonConfig.digitiserFormat;
    }

    if (jsonConfig.digitiserGain != undefined) {
        this.gain = parseInt(jsonConfig.digitiserGain);
    }

    if (jsonConfig.digitiserGainType != undefined) {
        this.gainMode = jsonConfig.digitiserGainType;
    }

    if (jsonConfig.digitiserGainTypes != undefined) {
        this.gainModes = jsonConfig.digitiserGainTypes;
    }

    if (jsonConfig.digitiserPartsPerMillion != undefined) {
        this.ppmError = parseFloat(jsonConfig.digitiserPartsPerMillion);
    }

    if (jsonConfig.dbmOffset != undefined) {
        this.dbmOffset = parseFloat(jsonConfig.dbmOffset);
    }

    if (jsonConfig.presetFps != undefined) {
        this.fpsAllowed = jsonConfig.presetFps;
    }

    if (jsonConfig.delay != undefined) {
        this.uiDelay = parseFloat(jsonConfig.delay);
    }
    if (jsonConfig.readRatio != undefined) {
        this.readRatio = parseFloat(jsonConfig.readRatio);
    }
    if (jsonConfig.headroom != undefined) {
        this.headroom = parseFloat(jsonConfig.headroom);
    }
    if (jsonConfig.overflows != undefined) {
        this.overflows = parseInt(jsonConfig.overflows);
    }
    if (jsonConfig.ui_delay != this.uiDelay) {
        this.uiDelay = parseFloat(jsonConfig.ui_delay);
    }
    if (jsonConfig.read_ratio != this.readRatio) {
        this.readRatio = parseFloat(jsonConfig.read_ratio);
    }
    if (jsonConfig.headroom != this.headroom) {
        this.headroom = parseFloat(jsonConfig.headroom);
    }
    if (jsonConfig.overflows != this.overflows) {
        this.overflows = parseInt(jsonConfig.input_overflows);
    }
    
    if (jsonConfig.fps != undefined) {
        this.fps = parseInt(jsonConfig.fps.set);
        this.measuredFps = parseFloat(jsonConfig.fps.measired);
    }
}

function sdrState() {
    // special values that are expected to vary every time
    this.gain = 0;
    this.measuredFps = 0;
    this.fps = 0;
    this.uiDelay = 0;
    this.readRatio = 0;
    this.headroom = 0;
    this.overflows = 0;

    // non visible things
    this.lastDataTime = 0;

    // normal UI visible values
    this.sdrFrequencyHz = 0.0; // what the sdr will be given
    this.frequencyRealHz = 0.0; // takes account of offset
    this.frequencyOffsetHz = 0.0; // subtracted from realCentreFrequencyHz
    this.firstTime = true;

    this.sps = 0;
    this.sdrBwHz = 0;
    this.ppmError = 0.0;
    this.dbmOffset = 0.0;

    this.fftSize = 0;
    this.fftSizes = [];
    this.window = "";
    this.windows = [];

    this.source = "";
    this.sourceParams = "";
    this.sources = [];
    this.sourceHelps = [];
    this.sourceConnected = false;

    this.gainMode = "";
    this.gainModes = [];

    this.dataFormat = "";
    this.dataFormats = [];
}
