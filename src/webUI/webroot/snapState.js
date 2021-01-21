/*
    The state of snapshots
*/

'use strict';


snapState.prototype.setBaseName = function(name) {
    this.baseFilename =  name;
}
snapState.prototype.setTriggerType = function(type) {
    this.triggerType = type;
}
snapState.prototype.setTriggerState = function(state) {
    this.triggerState = state;
}
snapState.prototype.setTriggers = function(trigs) {
    this.triggers = trigs;
}
snapState.prototype.setPreTriggerMilliSec = function(preMilliSec) {
    this.preTriggerMilliSec = parseInt(preMilliSec);
}
snapState.prototype.setPostTriggerMilliSec = function(postMilliSec) {
    this.postTriggerMilliSec = parseInt(postMilliSec);
}
snapState.prototype.setSnapState = function(state) {
    this.snapState = state;
}


snapState.prototype.getBaseName = function() {
    return this.baseFilename;
}
snapState.prototype.getTriggerType = function() {
    return this.triggerType;
}
snapState.prototype.getTriggerState = function() {
    return this.triggerState;
}
snapState.prototype.getTriggers = function() {
    return this.triggers;
}
snapState.prototype.getPreTriggerMilliSec = function() {
    return this.preTriggerMilliSec;
}
snapState.prototype.getPostTriggerMilliSec = function() {
    return this.postTriggerMilliSec;
}
snapState.prototype.getSnapState = function() {
    return this.snapState;
}

snapState.prototype.setSnapFromJason = function(jsonConfig) {
    let updateSnapTable = false;
    if (jsonConfig.baseFilename != snapState.getBaseName()) {
        snapState.setBaseName(jsonConfig.baseFilename);
        updateSnapTable = true;
    }
    if (jsonConfig.triggerType != snapState.getTriggerType()) {
        snapState.setTriggerType(jsonConfig.triggerType);
        updateSnapTable = true;
    }
    if (jsonConfig.triggers != snapState.getTriggers()) {
        snapState.setTriggers(jsonConfig.triggers);
        updateSnapTable = true;
    }
    if (jsonConfig.preTriggerMilliSec != snapState.getPreTriggerMilliSec()) {
        snapState.setPreTriggerMilliSec(jsonConfig.preTriggerMilliSec);
        updateSnapTable = true;
    }
    if (jsonConfig.postTriggerMilliSec != snapState.getPostTriggerMilliSec()) {
        snapState.setPostTriggerMilliSec(jsonConfig.postTriggerMilliSec);
        updateSnapTable = true;
    }
    if (jsonConfig.snapState != snapState.getSnapState()) {
        snapState.setSnapState(jsonConfig.snapState);
    }
    if (jsonConfig.triggerState != snapState.getTriggerState()) {
        snapState.setTriggerState(jsonConfig.triggerState);
        updateSnapTable = true;
    }
    return updateSnapTable;
}

snapState.prototype.getResetSnapStateUpdated = function() {
    let state = this.snapStateUpdated;
    if (state) {
        this.snapStateUpdated = false;
    }
    return state;
}
snapState.prototype.setSnapStateUpdated = function() {
    this.snapStateUpdated = true;
}
snapState.prototype.getSnapStateUpdated = function() {
    return this.snapStateUpdated;
}

function handleSnapTrigger() {
    snapState.setSnapState("start");
    snapState.setSnapStateUpdated();
}
function handleSnapBaseNameChange(name) {
    snapState.setBaseName(name);
    snapState.setSnapStateUpdated();
}
function handleSnapTriggerModeChange(triggerType) {
    snapState.setTriggerType(triggerType);
    snapState.setSnapStateUpdated();
}
function handleSnapPreTriggerChange(millisec) {
    snapState.setPreTriggerMilliSec(millisec);
    snapState.setSnapStateUpdated();
}
function handleSnapPostTriggerChange(millisec) {
    snapState.setPostTriggerMilliSec(millisec);
    snapState.setSnapStateUpdated();
}



function snapState() {
    this.type = "snapUpdate";
    this.baseFilename = "snapp";
    this.snapStateUpdated = false;
    this.snapState = "stop"; // start to trigger
    this.preTriggerMilliSec = 1000;
    this.postTriggerMilliSec = 2000;
    this.triggerState = "wait";
    this.triggerType = "manual";
    this.triggers = ["manual","test"];
}
