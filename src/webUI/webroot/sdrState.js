/*
    The state of the SDR front end
    We will use this to update the front end state through the websocket
*/

'use strict';

sdrState.prototype.setName = function(name) {
    this.name = name;
}
sdrState.prototype.setCentreFrequencyHz = function(freqHz) {
    this.centreFrequencyHz = parseInt(freqHz);
}
sdrState.prototype.setSps = function(sps) {
    this.sps = parseInt(sps);
}
sdrState.prototype.setFftSize = function(fftSize) {
    this.fftSize = parseInt(fftSize);
}
sdrState.prototype.setInputSource = function(source) {
    this.source = source;
}
sdrState.prototype.setInputSourceParams = function(params) {
    this.sourceParams = params;
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
sdrState.prototype.setSdrBw = function(sdrBw) {
    this.sdrBw = sdrBw;
}
sdrState.prototype.setLastDataTime = function(last) {
    this.lastDataTime = last;
}
sdrState.prototype.setNextAckTime = function(next) {
    this.nextAckTime = next;
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
sdrState.prototype.getSps = function() {
    return this.sps;
}
sdrState.prototype.getFftSize = function() {
    return this.fftSize;
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
sdrState.prototype.getSdrBw = function() {
    return this.sdrBw;
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

sdrState.prototype.getResetSdrStateUpdated = function() {
    let state = this.sdrStateUpdated;
    if (state) {
        this.sdrStateUpdated = false;
    }
    return state;
}

sdrState.prototype.setFromJason = function(jsonConfig) {
    let updateCfgTable = false;
    if (jsonConfig.centre_frequency_hz != sdrState.getCentreFrequencyHz()) {
        sdrState.setCentreFrequencyHz(jsonConfig.centre_frequency_hz);
        spectrum.setCentreFreqHz(jsonConfig.centre_frequency_hz);
        updateCfgTable = true;
    }

    if (jsonConfig.sample_rate != sdrState.getSps()) {
        sdrState.setSps(jsonConfig.sample_rate);
        spectrum.setSps(jsonConfig.sample_rate);
        spectrum.setSpanHz(jsonConfig.sample_rate);
        updateCfgTable = true;
    }

    if (jsonConfig.fft_size != sdrState.getFftSize()) {
        sdrState.setFftSize(jsonConfig.fft_size);
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

    if (jsonConfig.input_sources != sdrState.getInputSources()) {
        sdrState.setInputSources(jsonConfig.input_sources);
        updateCfgTable = true;
    }

    if (jsonConfig.input_sources_web_helps != sdrState.getInputSourceHelps()) {
        sdrState.setInputSourceHelps(jsonConfig.input_sources_web_helps);
        updateCfgTable = true;
    }

    if (jsonConfig.sample_types != sdrState.getDataFormats()) {
        sdrState.setDataFormats(jsonConfig.sample_types);
        updateCfgTable = true;
    }

    if (jsonConfig.sample_type != sdrState.getDataFormat()) {
        sdrState.setDataFormat(jsonConfig.sample_type);
        updateCfgTable = true;
    }

    // TODO: race condition sometimes oscillating between two fps values
    // both UI and config can change this
//    if (jsonConfig.fps != sdrState.getFps()) {
//        sdrState.setFps(jsonConfig.fps);
//        handleFpsChange(jsonConfig.fps);
//        updateCfgTable = true;
//    }

    if (jsonConfig.measured_fps != sdrState.getMeasuredFps()) {
        sdrState.setMeasuredFps(jsonConfig.measured_fps);
        updateCfgTable = true;
    }

    if (jsonConfig.source_connected != sdrState.getSourceConnected()) {
        sdrState.setSourceConnected(jsonConfig.source_connected);
        updateCfgTable = true;
    }

    if (jsonConfig.gain != sdrState.getGain()) {
        sdrState.setGain(jsonConfig.gain);
        updateCfgTable = true;
    }

    if (jsonConfig.gain_mode != sdrState.getGainMode()) {
        sdrState.setGainMode(jsonConfig.gain_mode);
        updateCfgTable = true;
    }

    if (jsonConfig.gain_modes != sdrState.getGainMode()) {
        sdrState.setGainModes(jsonConfig.gain_modes);
        updateCfgTable = true;
    }

    return updateCfgTable;
}

function sdrState(name) {
    this.type = "sdrUpdate",
    this.sdrStateUpdated = false; // true if the UI has changed something
    this.centreFrequencyHz = 0.0;
    this.sps = 0;
    this.fftSize = 0;
    this.source = "";
    this.sourceParams = "";
    this.sources = [];
    this.sourceHelps = [];
    this.sourceConnected = false;
    this.gainMode = "auto"; // TODO
    this.gain = 0;
    this.gainMode = "";
    this.gainModes = []; // TODO
    this.sdrBw = 0; // TODO
    this.dataFormat = "";
    this.dataFormats = [];
    this.fps = 0;
    this.measuredFps = 0;
    this.nextAckTime = 0;
    this.lastDataTime = 0;
}