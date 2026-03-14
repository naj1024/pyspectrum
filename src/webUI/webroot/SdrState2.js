/*
    The state of the SDR front end
*/

'use strict';

class SnapState {

    constructor() {
        // special values that are expected to vary every time
        this.gain = 0;
        this.measuredFps = 0;
        this.fps = 0;
        this.uiDelay = 0;
        this.loopCpuPc = 0;
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
        this.dcRemoval = false;
        this.inputLevel = 0.0;
        this.streamLength = 0.0;
        this.streamCurrent = 0.0;

        this.fftSize = 0;
        this.psd = "";
        this.fftOverlap = 0;
        this.fftOverlaps = [];
        this.fftSizes = [];
        this.fftFrameTime = 0;
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

    setFromJson(jsonConfig) {
        // One or more in json
        this._silent = true;

        // this should only set the offset frequency initially, i.e. set on command line
        if (this.firstTime) {
            this.frequencyOffsetHz = parseInt(jsonConfig.conversion_frequency_hz, 10) || 0;
            this.firstTime = false;
        }

        if (jsonConfig.digitiserFrequency != undefined){
            this.sdrFrequencyHz = parseInt(jsonConfig.digitiserFrequency, 10) || 0;
        }

        if (jsonConfig.frequency) {
            this.frequencyRealHz = parseInt(jsonConfig.frequency.value, 10) || 0;
            this.frequencyOffsetHz = parseInt(jsonConfig.frequency.conversion, 10) || 0;
            spectrum.setCentreFreqHz(this.frequencyRealHz);  // TODO: why is this here
        }

        if (jsonConfig.digitiserSampleRate) {
            this.sps = parseInt(jsonConfig.digitiserSampleRate, 10) || 1;
            spectrum.setSps(this.sps);   // TODO: why is this here
            spectrum.setSpanHz(this.sps);   // TODO: why is this here
        }

        if (jsonConfig.digitiserBandwidth) {
            this.sdrBwHz = parseInt(jsonConfig.digitiserBandwidth, 10) || 0;
        }

        if (jsonConfig.fftSizes) {
            this.fftSizes = jsonConfig.fftSizes;
        }

        if (jsonConfig.fftFrameTime) {
            this.fftFrameTime = jsonConfig.fftFrameTime;
        }

        if (jsonConfig.fftSize) {
            this.fftSize = jsonConfig.fftSize;
        }

        if (jsonConfig.fftOverlaps) {
            this.fftOverlaps = jsonConfig.fftOverlaps;
        }

        if (jsonConfig.fftOverlap) {
            this.fftOverlap = jsonConfig.fftOverlap;
        }

        if (jsonConfig.psd) {
            if (jsonConfig.psd == false) {
                this.psd = "Off";
            }
            else{
                this.psd = "On";
            }
        }

        if (jsonConfig.fftWindow) {
            this.window = jsonConfig.fftWindow;
        }

        if (jsonConfig.fftWindows) {
            this.windows = jsonConfig.fftWindows;
        }

        if (jsonConfig.sources) {
            // TODO: keep the source and help paired up
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

        if (jsonConfig.source) {
            this.source = jsonConfig.source.source;
            this.sourceConnected = jsonConfig.source.connected;
            if (this.source == "file") {
                this.sourceParams = basename(jsonConfig.source.params);
            } else {
                this.sourceParams = jsonConfig.source.params;
            }
        }

        if (jsonConfig.digitiserFormats) {
            this.dataFormats = jsonConfig.digitiserFormats;
        }

        if (jsonConfig.digitiserFormat) {
            this.dataFormat = jsonConfig.digitiserFormat;
        }

        if (jsonConfig.digitiserGain) {
            this.gain = parseInt(jsonConfig.digitiserGain, 10) || 0;
        }

        if (jsonConfig.digitiserGainType) {
            this.gainMode = jsonConfig.digitiserGainType;
        }

        if (jsonConfig.digitiserGainTypes) {
            this.gainModes = jsonConfig.digitiserGainTypes;
        }

        if (jsonConfig.digitiserPartsPerMillion) {
            this.ppmError = parseFloat(jsonConfig.digitiserPartsPerMillion) || 0.0;
        }

        if (jsonConfig.digitiserDcRemoval) {
            this.dcRemoval = jsonConfig.digitiserDcRemoval;
        }

        if (jsonConfig.digitiserDcRemovals) {
            this.dcRemovals = jsonConfig.digitiserDcRemovals;
        }

        if (jsonConfig.digitiserInputLevel) {
            this.inputLevel = jsonConfig.digitiserInputLevel;
        }

        if (jsonConfig.streamLength) {
            this.streamLength = jsonConfig.streamLength;
        }

        if (jsonConfig.streamCurrent) {
            this.streamCurrent = jsonConfig.streamCurrent;
        }

        if (jsonConfig.digitiserDbmOffset) {
            this.dbmOffset = parseFloat(jsonConfig.digitiserDbmOffset || 0.0;
        }

        if (jsonConfig.presetFps) {
            this.fpsAllowed = jsonConfig.presetFps;
        }

        if (jsonConfig.delay) {
            this.uiDelay = parseFloat(jsonConfig.delay || 0.0;
        }
        if (jsonConfig.loopCpuPc) {
            this.loopCpuPc = parseFloat(jsonConfig.loopCpuPc) || 0.0;
        }
        if (jsonConfig.overflows) {
            this.overflows = parseInt(jsonConfig.overflows, 10) || 0;
        }
        if (jsonConfig.ui_delay) {
            this.uiDelay = parseFloat(jsonConfig.ui_delay);
        }
        if (jsonConfig.overflows) {
            this.overflows = parseInt(jsonConfig.input_overflows, 10) || 0;
        }

        if (jsonConfig.fps) {
            this.fps = parseInt(jsonConfig.fps.set, 10) || 0;
            this.measuredFps = parseFloat(jsonConfig.fps.measured || 0.0;
        }
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
const sdrApiMap = {
    baseFilename: { endpoint: "snapName", key: "snapName" },
    triggerType: { endpoint: "snapTriggerSource", key: "snapTriggerSource" },
    preTriggerMs: { endpoint: "snapPreTrigger", key: "snapPreTrigger" },
    postTriggerMs: { endpoint: "snapPostTrigger", key: "snapPostTrigger" },
    fileFormat: { endpoint: "snapFormat", key: "snapFormat" }
};

/*
    Create state with Proxy auto-sync
*/
const sdrState = new Proxy(new SdrState(), {
    set(target, prop, value) {
        target[prop] = value;
        if (target._silent)
            return true;

        const api = sdrApiMap[prop];
        if (api) {
            update(api.endpoint, api.key, value);
        }
        return true;
    }
});

/*
    Export globally
*/
window.sdrState = SdrState;


