/*
    Snapshot State + API Sync
*/

"use strict";

class SnapState {

    constructor() {
        this.baseFilename = "";
        this.preTriggerMs = 0;
        this.postTriggerMs = 0;
        this.triggerState = false;
        this.triggerType = "0";
        this.triggers = [];
        this.currentSize = 0;
        this.expectedSize = 0;
        this.directoryList = [];
        this.deleteFileName = "";
        this.fileFormats = [];
        this.fileFormat = "";

        this._silent = false;
    }

    setFromJson(cfg) {
        // One or more in json
        this._silent = true;
        this.deleteFileName = ""; // TODO: why here

        if (cfg.snapName)
            this.baseFilename = cfg.snapName.split('/').pop();

        if (cfg.snapTriggerSource)
            this.triggerType = cfg.snapTriggerSource;

        if (cfg.snapTriggerSources)
            this.triggers = cfg.snapTriggerSources;

        if (cfg.snapPreTrigger !== undefined)
            this.preTriggerMs = parseInt(cfg.snapPreTrigger, 10) || 0;

        if (cfg.snapPostTrigger !== undefined)
            this.postTriggerMs = parseInt(cfg.snapPostTrigger, 10) || 0;

        if (cfg.snapSize !== undefined) {
            this.currentSize = parseInt(cfg.snapSize.current, 10) || 0;
            this.expectedSize = parseInt(cfg.snapSize.limit, 10) || 0;
        }

        if (cfg.snapTriggerState !== undefined)
            this.triggerState = cfg.snapTriggerState;

        if (cfg.snapFormats)
            this.fileFormats = cfg.snapFormats;

        if (cfg.snapFormat)
            this.fileFormat = cfg.snapFormat;

        if (cfg.snaps)
            this.directoryList = cfg.snaps;

        this._silent = false;
    }

    getDirectoryListEntries() {
        return this.directoryList?.length ?? 0;
    }
}


/*
    API helper
*/
async function update(endpoint, key, value) {
    try {
        const response = await fetch(`./snapshot/${endpoint}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [key]: value })
        });
        return await response.json();
    } catch (err) {
        console.error("Snapshot API error:", err);
    }
}

/*
    Property → API mapping
*/
const snapApiMap = {
    baseFilename: { endpoint: "snapName", key: "snapName" },
    triggerType: { endpoint: "snapTriggerSource", key: "snapTriggerSource" },
    preTriggerMs: { endpoint: "snapPreTrigger", key: "snapPreTrigger" },
    postTriggerMs: { endpoint: "snapPostTrigger", key: "snapPostTrigger" },
    fileFormat: { endpoint: "snapFormat", key: "snapFormat" }
};

/*
    Create state with Proxy auto-sync
*/
const snapState = new Proxy(new SnapState(), {

    set(target, prop, value) {
        target[prop] = value;
        if (target._silent)
            return true;

        if (!target._silent) {
            const api = snapApiMap[prop];
            if (api) {
                update(api.endpoint, api.key, value);
            }

            if (target._listeners) {
                target._listeners.forEach(fn => fn(prop, value));
            }
        }
        return true;
    }
});

snapState.onChange = function(callback) {
    if (!this._listeners)
        this._listeners = [];
    this._listeners.push(callback);
};

/*
    Snapshot trigger
*/
function triggerSnapshot() {
    return update(
        "snapTrigger",
        "snapTrigger",
        true
    );
}

/*
    Export globally
*/
window.snapState = snapState;
window.triggerSnapshot = triggerSnapshot;
