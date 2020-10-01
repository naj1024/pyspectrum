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
sdrState.prototype.setSdrStateUpdated = function() {
    this.sdrStateUpdated = true;
}

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
sdrState.prototype.getResetSdrStateUpdated = function() {
    let state = this.sdrStateUpdated;
    if (state) {
        this.sdrStateUpdated = false;
    }
    return state;
}

function sdrState(name) {
    this.centreFrequencyHz = 0.0;
    this.sps = 0;
    this.bw = 0;
    this.fftSize = 0;
    this.name = name; // TODO
    this.gainMode = ""; // TODO
    this.gain = 0; // TODO

    this.sdrStateUpdated = false; // true if the UI has changed something
}
