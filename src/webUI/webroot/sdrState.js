/*
    The state of the SDR front end
    We will use this to update the front end state through the websocket
*/

'use strict';

function basename(path) {
   return path.split(/[\\/]/).pop();
}

sdrState.prototype.setName = function(name) {
    this.name = name;
}

// ALL set fucntions should only be called from UI side
sdrState.prototype.setCentreFrequencyHz = function(freqHz) {
    this.centreFrequencyHz = parseInt(freqHz);
    this.realCentreFrequencyHz = this.centreFrequencyHz + this.centreFrequencyOffsetHz;
    this.cfRealUpdated = true;
}
sdrState.prototype.setCentreFrequencyOffsetHz = function(freqHz) {
    this.centreFrequencyOffsetHz = parseInt(freqHz);
    // the sdr tuned frequency stays the same
    this.setCentreFrequencyHz(this.centreFrequencyHz);
    window.sessionStorage.setItem("centreFrequencyOffsetHz", this.centreFrequencyOffsetHz);
}
sdrState.prototype.setSps = function(sps) {
    this.sps = parseInt(sps);
}
sdrState.prototype.setFftSize = function(fftSize) {
    this.fftSize = parseInt(fftSize);
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
        console.log(params, this.sourceParams);
        this.centreFrequencyOffsetHz = 0.0;
    } else {
        this.sourceParams = params;
    }
}
sdrState.prototype.setDataFormat = function(format) {
    this.dataFormat = format;
}
sdrState.prototype.setFps = function(fps) {
    this.fps = fps;
}
sdrState.prototype.setGain = function(gain) {
    this.gain = gain;
}
sdrState.prototype.setGainMode = function(gainMode) {
    this.gainMode = gainMode;
}
sdrState.prototype.setGainModes = function(gainModes) {
    this.gainModes = gainModes;
}
sdrState.prototype.setSdrBwHz = function(sdrBwHz) {
    this.sdrBwHz = sdrBwHz;
}
sdrState.prototype.setPpmError = function(error) {
    this.ppmError = error;
}

////////////////////
// getters
///////
sdrState.prototype.getName = function() {
    return this.name;
}
sdrState.prototype.getCentreFrequencyHz = function() {
    return this.centreFrequencyHz;
}
sdrState.prototype.getRealCentreFrequencyHz = function() {
    return this.realCentreFrequencyHz;
}
sdrState.prototype.getCentreFrequencyOffsetHz = function() {
    return this.centreFrequencyOffsetHz;
}
sdrState.prototype.getSps = function() {
    return this.sps;
}
sdrState.prototype.getFftSize = function() {
    return this.fftSize;
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

sdrState.prototype.setUiStateUpdated = function() {
    this.uuid += 1;
    sessionStorage.setItem("uuid", this.uuid);
    this.uiStateUpdated = true;
}
sdrState.prototype.getUiStateUpdated = function() {
    return this.uiStateUpdated;
}
sdrState.prototype.getLastDataTime = function() {
    return this.lastDataTime;
}
sdrState.prototype.getNextAckTime = function() {
    return this.nextAckTime;
}
sdrState.prototype.getUiDelay = function() {
    return this.uiDelay;
}
sdrState.prototype.getPpmError = function() {
    return this.ppmError;
}

sdrState.prototype.getResetSdrStateUpdated = function() {
    let state = this.sdrStateUpdated;
    this.sdrStateUpdated = false;
    return state;
}
sdrState.prototype.getResetUiStateUpdated = function() {
    let state = this.uiStateUpdated;
    this.uiStateUpdated = false;
    return state;
}
sdrState.prototype.getResetRealCfUpdated = function() {
    let state = this.cfRealUpdated;
    this.cfRealUpdated = false;
    return state;
}
sdrState.prototype.getAlwaysChange = function() {
    let changed = this.alwaysChange;
    this.alwaysChange = false;
    return changed;
}
sdrState.prototype.setLastDataTime = function(last) {
    this.lastDataTime = last;
}
sdrState.prototype.setNextAckTime = function(next) {
    this.nextAckTime = next;
}

sdrState.prototype.setConfigFromJason = function(jsonConfig) {
    // this is only called when configuration data is sent from the server
    let updateUi = false;
    // ignore json that is out of step with our state
    if (jsonConfig.uuid >= this.uuid) {
        // if json uuid is in advance of ours then it means we have connected to a server
        // that has been runign a while and we are a new UI
        this.uuid = jsonConfig.uuid;
        //console.log(jsonConfig.uuid, this.uuid, jsonConfig)

        if (jsonConfig.centre_frequency_hz != this.centreFrequencyHz) {
            this.centreFrequencyHz = parseInt(jsonConfig.centre_frequency_hz);
            this.realCentreFrequencyHz = this.centreFrequencyHz + this.centreFrequencyOffsetHz;
            spectrum.setCentreFreqHz(this.realCentreFrequencyHz);
            updateUi = true;
            this.cfRealUpdated = true;
        }

        if (jsonConfig.sample_rate != this.sps) {
            this.sps = jsonConfig.sample_rate;
            spectrum.setSps(jsonConfig.sample_rate);
            spectrum.setSpanHz(jsonConfig.sample_rate);
            updateUi = true;
        }

        if (jsonConfig.input_bw_hz != this.sdrBwHz) {
            this.sdrBwHz = jsonConfig.input_bw_hz;
            updateUi = true;
        }

        if (jsonConfig.fft_size != this.fftSize) {
            this.fftSize = jsonConfig.fft_size;
            updateUi = true;
        }

        if (jsonConfig.window != this.window) {
            this.window = jsonConfig.window;
            updateUi = true;
        }

        if (JSON.stringify(jsonConfig.window_types) != JSON.stringify(this.windows)) {
            this.windows = jsonConfig.window_types;
            updateUi = true;
        }

        if (jsonConfig.input_source != this.source) {
            this.source = jsonConfig.input_source;
            updateUi = true;
        }

        if (jsonConfig.input_params != this.sourceParams) {
             if (this.source == "file") {
                this.sourceParams = basename(jsonConfig.input_params);
             } else {
                this.sourceParams = jsonConfig.input_params;
             }
            updateUi = true;
        }

        if (JSON.stringify(jsonConfig.input_sources) != JSON.stringify(this.sources)) {
            this.sources = jsonConfig.input_sources;
            updateUi = true;
        }

        if (JSON.stringify(jsonConfig.input_sources_web_helps) != JSON.stringify(this.sourceHelps)) {
            this.sourceHelps = jsonConfig.input_sources_web_helps;
            updateUi = true;
        }

        if (JSON.stringify(jsonConfig.sample_types) != JSON.stringify(this.dataFormats)) {
            this.dataFormats = jsonConfig.sample_types;
            updateUi = true;
        }

        if (jsonConfig.sample_type != this.dataFormat) {
            this.dataFormat = jsonConfig.sample_type;
            updateUi = true;
        }

        if (jsonConfig.source_connected != this.sourceConnected) {
            this.sourceConnected = jsonConfig.source_connected;
            updateUi = true;
        }

        if (jsonConfig.gain_mode != this.gainMode) {
            this.gainMode = jsonConfig.gain_mode;
            updateUi = true;
        }

        if (JSON.stringify(jsonConfig.gain_modes)!= JSON.stringify(this.gainModes)) {
            this.gainModes = jsonConfig.gain_modes;
            updateUi = true;
        }

        if (jsonConfig.ppm_error != this.ppmError) {
            this.ppmError = parseFloat(jsonConfig.ppm_error);
            updateUi = true;
        }
        this.sdrStateUpdated = updateUi;
    }

    // things that will always change, and we don't care about uuid
    if (jsonConfig.gain != this.gain) {
        this.gain = jsonConfig.gain;
        this.alwaysChange = true;
    }
    if (jsonConfig.ui_delay != this.uiDelay) {
        this.uiDelay = jsonConfig.ui_delay;
        this.alwaysChange = true;
    }
    if (jsonConfig.measured_fps != this.measuredFps) {
        this.measuredFps = jsonConfig.measured_fps;
        this.alwaysChange = true;
    }

    return updateUi;
}

function sdrState() {
    this.type = "sdrUpdate";
    this.uuid = 0; // for ignoring out of date, in flight, server replies

    this.uiStateUpdated = false; // true if the UI has changed something
    this.sdrStateUpdated = false; // true if the server has changed something
    this.cfRealUpdated = false;

    // special values that are expected to vary every time
    this.alwaysChange = false;  // things that will change all the time
    this.gain = 0;
    this.measuredFps = 0;
    this.uiDelay = 0;

    // non visible things
    this.nextAckTime = 0;
    this.lastDataTime = 0;

    // normal UI visible values
    this.centreFrequencyHz = 0.0; // what the sdr will be given
    this.realCentreFrequencyHz = 0.0; // takes account of offset
    this.centreFrequencyOffsetHz = 0.0; // subtracted from realCentreFrequencyHz

    this.sps = 0;
    this.sdrBwHz = 0;
    this.ppmError = 0.0;

    this.fftSize = 0;
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

    this.fps = 0;

    let uuid = sessionStorage.getItem("uuid");
    if (uuid != null) {
        sdrState.uuid = uuid;
    }
}
