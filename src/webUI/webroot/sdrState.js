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
sdrState.prototype.setBw = function(bw) {
    this.bw = parseInt(bw);
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
sdrState.prototype.getBw = function() {
    return this.bw;
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
sdrState.prototype.getMeasuredFps = function() {
    return this.measuredFps;
}

sdrState.prototype.setSdrStateUpdated = function() {
    this.sdrStateUpdated = true;
}
sdrState.prototype.getSdrStateUpdated = function() {
    return this.sdrStateUpdated;
}
sdrState.prototype.getResetSdrStateUpdated = function() {
    let state = this.sdrStateUpdated;
    if (state) {
        this.sdrStateUpdated = false;
    }
    return state;
}

function sdrState(name) {
    this.type = "sdrUpdate",
    this.sdrStateUpdated = false; // true if the UI has changed something
    this.centreFrequencyHz = 0.0;
    this.sps = 0;
    this.bw = 0;
    this.fftSize = 0;
    this.source = "";
    this.sourceParams = "";
    this.sources = [];
    this.sourceHelps = [];
    this.gainMode = ""; // TODO
    this.gain = 0; // TODO
    this.dataFormat = "";
    this.dataFormats = [];
    this.measuredFps = 0;
}
