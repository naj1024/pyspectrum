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
snapState.prototype.setCurrentSize = function(size) {
    this.snapCurrentSize = size;
}
snapState.prototype.setExpectedSize = function(size) {
    this.snapExpectedSize = size;
}
snapState.prototype.setDirectoryList = function(dirList) {
    this.directoryList = dirList;
}
snapState.prototype.setDeleteFilename = function(name) {
    this.deleteFileName = name;
}
snapState.prototype.setFileFormat = function(fileFormat) {
    this.fileFormat = fileFormat;
}
snapState.prototype.setFileFormats = function(fileFormats) {
    this.fileFormats = fileFormats;
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
snapState.prototype.getCurrentSize = function() {
    return this.snapCurrentSize;
}
snapState.prototype.getExpectedSize = function() {
    return this.snapExpectedSize;
}
snapState.prototype.getDirectoryList = function() {
    return this.directoryList;
}
snapState.prototype.getDeleteFilename = function() {
    return this.deleteFileName;
}
snapState.prototype.getFileFormat = function() {
    return this.fileFormat;
}
snapState.prototype.getFileFormats = function() {
    return this.fileFormats;
}
snapState.prototype.getDirectoryListEntries = function() {
    return this.directoryList.length;
}

snapState.prototype.setSnapFromJason = function(jsonConfig) {
    snapState.setDeleteFilename("");

    //console.log(jsonConfig)

    if (jsonConfig.snapName != undefined) {
        snapState.setBaseName(jsonConfig.snapName.split('/').reverse()[0]);
    }
    if (jsonConfig.snapTriggerSource != undefined) {
        snapState.setTriggerType(jsonConfig.snapTriggerSource);
    }
    if (jsonConfig.snapTriggerSources != undefined) {
        snapState.setTriggers(jsonConfig.snapTriggerSources);
    }
    if (jsonConfig.snapPreTrigger != undefined) {
        snapState.setPreTriggerMilliSec(jsonConfig.snapPreTrigger);
    }
    if (jsonConfig.snapPostTrigger != undefined) {
        snapState.setPostTriggerMilliSec(jsonConfig.snapPostTrigger);
    }
    if (jsonConfig.snapTrigger != undefined) {
        snapState.setTriggerState(jsonConfig.snapTrigger);
    }
    if (jsonConfig.snapFormats != undefined) {
        snapState.setFileFormats(jsonConfig.snapFormats);
    }
    if (jsonConfig.snapFormat != undefined) {
        snapState.setFileFormat(jsonConfig.snapFormat);
    }

    // just on size discrepancy for now
    if(jsonConfig.snaps != undefined) {
        snapState.setDirectoryList(jsonConfig.snaps);
    }
}

function handleSnapTrigger() {
    fetch("./snapshot/snapTrigger", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapTrigger":true})
    }).then(response => {
        return response.json();
    });
}
function handleSnapBaseNameChange(name) {
    fetch("./snapshot/snapName", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapName":(name)})
    }).then(response => {
        return response.json();
    });
    snapState.setBaseName(name);
}
function handleSnapTriggerModeChange(triggerType) {
    fetch("./snapshot/snapTriggerSource", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapTriggerSource":(triggerType)})
    }).then(response => {
        return response.json();
    });
    snapState.setTriggerType(triggerType);
}
function handleSnapPreTriggerChange(millisec) {
    fetch("./snapshot/snapPreTrigger", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapPreTrigger":(millisec)})
    }).then(response => {
        return response.json();
    });
    snapState.setPreTriggerMilliSec(millisec);
}
function handleSnapPostTriggerChange(millisec) {
    fetch("./snapshot/snapPostTrigger", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapPostTrigger":(millisec)})
    }).then(response => {
        return response.json();
    });
    snapState.setPostTriggerMilliSec(millisec);
}
function handleSnapFileFormatChange(fileFormat) {
    fetch("./snapshot/snapFormat", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"snapFormat":(fileFormat)})
    }).then(response => {
        return response.json();
    });
    snapState.setFileFormat(fileFormat);
}


function snapState() {
    this.baseFilename = "";
    this.preTriggerMilliSec = 0;
    this.postTriggerMilliSec = 0;
    this.triggerState = false;
    this.triggerType = "0";
    this.triggers = [];
    this.snapCurrentSize = 0;
    this.snapExpectedSize = 0;
    this.directoryList = [];
    this.deleteFileName = "";
    this.fileFormats = [];
    this.fileFormat = "";
}
