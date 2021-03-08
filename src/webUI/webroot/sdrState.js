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
    if (this.source == "file")
    {
        this.sourceParams = basename(params);
        console.log(params, this.sourceParams);
        this.centreFrequencyOffsetHz = 0.0;
    }
    else
    {
        this.sourceParams = params;
    }
}
sdrState.prototype.setInputSources = function(sources) {
    this.sources = sources;
}
sdrState.prototype.setInputSourceHelps = function(helps) {
    this.sourceHelps = helps;
}
sdrState.prototype.setDataFormats = function(formats) {
   this.dataFormats = formats;
}
sdrState.prototype.setDataFormat = function(format) {
    this.dataFormat = format;
}
sdrState.prototype.setMeasuredFps = function(measured) {
    this.measuredFps = measured;
}
sdrState.prototype.setFps = function(fps) {
    this.fps = fps;
}
sdrState.prototype.setSourceConnected = function(connected) {
    this.sourceConnected = connected;
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
sdrState.prototype.setLastDataTime = function(last) {
    this.lastDataTime = last;
}
sdrState.prototype.setNextAckTime = function(next) {
    this.nextAckTime = next;
}
sdrState.prototype.setUiDelay = function(delay) {
    return this.uiDelay = delay;
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

sdrState.prototype.setSdrStateUpdated = function() {
    this.sdrStateUpdated = true;
}
sdrState.prototype.getSdrStateUpdated = function() {
    return this.sdrStateUpdated;
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

sdrState.prototype.setConfigFromJason = function(jsonConfig) {
    // console.log(jsonConfig)
    let updateCfgTable = false;

    // only update from the sdr frequency
    if (jsonConfig.centre_frequency_hz != sdrState.getCentreFrequencyHz()) {
        sdrState.setCentreFrequencyHz(jsonConfig.centre_frequency_hz);
        spectrum.setCentreFreqHz(sdrState.getRealCentreFrequencyHz());
        updateCfgTable = true;
    }

    if (jsonConfig.sample_rate != sdrState.getSps()) {
        sdrState.setSps(jsonConfig.sample_rate);
        spectrum.setSps(jsonConfig.sample_rate);
        spectrum.setSpanHz(jsonConfig.sample_rate);
        updateCfgTable = true;
    }

    if (jsonConfig.input_bw_hz != sdrState.getSdrBwHz()) {
        sdrState.setSdrBwHz(jsonConfig.input_bw_hz);
        updateCfgTable = true;
    }

    if (jsonConfig.fft_size != sdrState.getFftSize()) {
        sdrState.setFftSize(jsonConfig.fft_size);
        updateCfgTable = true;
    }

    if (jsonConfig.window != sdrState.getFftWindow()) {
        sdrState.setFftWindow(jsonConfig.window);
        updateCfgTable = true;
    }

    if (JSON.stringify(jsonConfig.window_types) != JSON.stringify(sdrState.getFftWindows())) {
        sdrState.setFftWindows(jsonConfig.window_types);
        updateCfgTable = true;
    }

    if (jsonConfig.input_source != sdrState.getInputSource()) {
        sdrState.setInputSource(jsonConfig.input_source);
        updateCfgTable = true;
    }

    if (jsonConfig.input_params != sdrState.getInputSourceParams()) {
        sdrState.setInputSourceParams(jsonConfig.input_params);
        updateCfgTable = true;
    }

    if (JSON.stringify(jsonConfig.input_sources) != JSON.stringify(sdrState.getInputSources())) {
        sdrState.setInputSources(jsonConfig.input_sources);
        updateCfgTable = true;
    }

    if (JSON.stringify(jsonConfig.input_sources_web_helps) != JSON.stringify(sdrState.getInputSourceHelps())) {
        sdrState.setInputSourceHelps(jsonConfig.input_sources_web_helps);
        updateCfgTable = true;
    }

    if (JSON.stringify(jsonConfig.sample_types) != JSON.stringify(sdrState.getDataFormats())) {
        sdrState.setDataFormats(jsonConfig.sample_types);
        updateCfgTable = true;
    }

    if (jsonConfig.sample_type != sdrState.getDataFormat()) {
        sdrState.setDataFormat(jsonConfig.sample_type);
        updateCfgTable = true;
    }

    if (jsonConfig.measured_fps != sdrState.getMeasuredFps()) {
        sdrState.setMeasuredFps(jsonConfig.measured_fps);
        this.alwaysChange = true;
    }

    if (jsonConfig.source_connected != sdrState.getSourceConnected()) {
        sdrState.setSourceConnected(jsonConfig.source_connected);
        updateCfgTable = true;
    }

    if (jsonConfig.gain != sdrState.getGain()) {
        sdrState.setGain(jsonConfig.gain);
        this.alwaysChange = true;
    }

    if (jsonConfig.gain_mode != sdrState.getGainMode()) {
        sdrState.setGainMode(jsonConfig.gain_mode);
        updateCfgTable = true;
    }

    if (JSON.stringify(jsonConfig.gain_modes)!= JSON.stringify(sdrState.getGainModes())) {
        sdrState.setGainModes(jsonConfig.gain_modes);
        updateCfgTable = true;
    }

    if (jsonConfig.ui_delay != sdrState.getUiDelay()) {
        sdrState.setUiDelay(jsonConfig.ui_delay);
        this.alwaysChange = true;
    }

    if (jsonConfig.ppm_error != sdrState.getPpmError()) {
        sdrState.setPpmError(jsonConfig.ppm_error);
        updateCfgTable = true;
    }
    this.sdrStateUpdated = updateCfgTable;
    return updateCfgTable;
}

function sdrState() {
    this.type = "sdrUpdate",
    this.sdrStateUpdated = false; // true if the UI has changed something
    this.centreFrequencyHz = 0.0; // what the sdr will be given
    this.realCentreFrequencyHz = 0.0; // takes account of offset
    this.cfRealUpdated = false;
    this.centreFrequencyOffsetHz = 0.0; // subtracted from realCentreFrequencyHz
    this.sps = 0;
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
    this.sdrBwHz = 0;
    this.ppmError = 0.0;
    this.dataFormat = "";
    this.dataFormats = [];
    this.fps = 0;
    this.nextAckTime = 0;
    this.lastDataTime = 0;

    // special values that are expected to vary every time
    this.alwaysChange = false;
    this.gain = 0;
    this.measuredFps = 0;
    this.uiDelay = 0;
}
