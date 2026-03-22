/*
    SDR State (modernised, reactive)
*/

"use strict";

function basename(path) {
    return path.split(/[\\/]/).pop();
}

class SdrState {

    constructor() {

        // dynamic / runtime
        this.gain = 0;
        this.measuredFps = 0;
        this.fps = 0;
        this.uiDelay = 0;
        this.loopCpuPc = 0;
        this.maxCpuCorePc = 0;
        this.overflows = 0;

        this.lastDataTime = 0;

        // RF / DSP
        this.sdrFrequencyHz = 0;
        this.frequencyRealHz = 0;
        this.frequencyOffsetHz = 0;
        this.firstTime = true;

        this.sps = 0;
        this.sdrBwHz = 0;
        this.ppmError = 0;
        this.dbmOffset = 0;
        this.dcRemoval = false;
        this.inputLevel = 0;
        this.streamLength = 0;
        this.streamCurrent = 0;

        this.fftSize = 0;
        this.psd = "";
        this.fftOverlap = 0;
        this.fftOverlaps = [];
        this.fftSizes = [];
        this.fftFrameTime = 0;
        this.window = "";
        this.windows = [];
        this.fftRbw = 0;
        this.fftBin = 0;

        this.readMagnitudes = false;

        this.source = "";
        this.sourceParams = "";
        this.sources = [];
        this.sourceHelps = {};
        this.sourceConnected = false;

        this.gainMode = "";
        this.gainModes = [];

        this.dataFormat = "";
        this.dataFormats = [];

        // internal
        this._silent = false;
        this._listeners = [];
    }

    onChange(fn) {
        this._listeners.push(fn);
    }

    _notify(prop, value) {
        this._listeners.forEach(fn => fn(prop, value));
    }

    setConfigFromJason(cfg) {

        this._silent = true;

        if (this.firstTime) {
            this.frequencyOffsetHz = Number(cfg.conversion_frequency_hz) || 0;
            this.firstTime = false;
        }

        if (cfg.digitiserFrequency)
            this.sdrFrequencyHz = Number(cfg.digitiserFrequency);

        if (cfg.frequency) {
            this.frequencyRealHz = Number(cfg.frequency.value);
            this.frequencyOffsetHz = Number(cfg.frequency.conversion);

            if (window.spectrum) {
                spectrum.setCentreFreqHz(this.frequencyRealHz);
            }
        }

        if (cfg.digitiserSampleRate) {
            this.sps = Number(cfg.digitiserSampleRate);

            if (window.spectrum) {
                spectrum.setSps(this.sps);
                spectrum.setSpanHz(this.sps);
            }
        }

        if (cfg.digitiserBandwidth)
            this.sdrBwHz = Number(cfg.digitiserBandwidth);

        if (cfg.fftSizes)
            this.fftSizes = cfg.fftSizes;

        if (cfg.fftFrameTime)
            this.fftFrameTime = cfg.fftFrameTime;

        if (cfg.fftSize)
            this.fftSize = cfg.fftSize;

        if (cfg.fftRbw) {
            this.fftRbw = cfg.fftRbw;
            this.fftBin = this.sps / this.fftSize;
        }

        if (cfg.fftOverlaps)
            this.fftOverlaps = cfg.fftOverlaps;

        if (cfg.fftOverlap)
            this.fftOverlap = cfg.fftOverlap;

        if (cfg.psd)
            this.psd = (cfg.psd === "On") ? "On" : "Off";

        if (cfg.fftWindow)
            this.window = cfg.fftWindow;

        if (cfg.fftWindows)
            this.windows = cfg.fftWindows;

        if (cfg.readMagnitudes)
            this.readMagnitudes = cfg.readMagnitudes;

        if (cfg.sources) {
            const entries = Object.entries(cfg.sources);
            this.sources = entries.map(e => e[0]);
            this.sourceHelps = Object.fromEntries(entries);
        }

        if (cfg.source) {
            this.source = cfg.source.source;
            this.sourceConnected = cfg.source.connected;

            this.sourceParams = (this.source === "file")
                ? basename(cfg.source.params)
                : cfg.source.params;
        }

        if (cfg.digitiserFormats)
            this.dataFormats = cfg.digitiserFormats;

        if (cfg.digitiserFormat)
            this.dataFormat = cfg.digitiserFormat;

        if (cfg.digitiserGain)
            this.gain = Number(cfg.digitiserGain);

        if (cfg.digitiserGainType)
            this.gainMode = cfg.digitiserGainType;

        if (cfg.digitiserGainTypes)
            this.gainModes = cfg.digitiserGainTypes;

        if (cfg.digitiserPartsPerMillion)
            this.ppmError = Number(cfg.digitiserPartsPerMillion);

        if (cfg.digitiserDcRemoval)
            this.dcRemoval = cfg.digitiserDcRemoval;

        if (cfg.digitiserDcRemovals)
            this.dcRemovals = cfg.digitiserDcRemovals;

        if (cfg.digitiserInputLevel)
            this.inputLevel = cfg.digitiserInputLevel;

        if (cfg.streamLength)
            this.streamLength = cfg.streamLength;

        if (cfg.streamCurrent)
            this.streamCurrent = cfg.streamCurrent;

        if (cfg.digitiserDbmOffset)
            this.dbmOffset = Number(cfg.digitiserDbmOffset);

        if (cfg.presetFps)
            this.fpsAllowed = cfg.presetFps;

        if (cfg.delay)
            this.uiDelay = Number(cfg.delay);

        if (cfg.loopCpuPc)
            this.loopCpuPc = Number(cfg.loopCpuPc);

        if (cfg.maxCpuCorePc)
            this.maxCpuCorePc = Number(cfg.maxCpuCorePc);

        if (cfg.overflows)
            this.overflows = Number(cfg.overflows);

        if (cfg.fps) {
            this.fps = Number(cfg.fps.set);
            this.measuredFps = Number(cfg.fps.measured);
        }

        this._silent = false;
    }
}


/*
    Optional API mapping (only include what you want writable from UI)
*/
const sdrApiMap = {
    gain: { endpoint: "digitiserGain", key: "digitiserGain" },
    gainMode: { endpoint: "digitiserGainType", key: "digitiserGainType" },
    dataFormat: { endpoint: "digitiserFormat", key: "digitiserFormat" },
    frequencyRealHz: { endpoint: "frequency", key: "frequency" }
};


/*
    Proxy wrapper
*/
const sdrState = new Proxy(new SdrState(), {
    set(target, prop, value) {
        // auto number conversion
        if (typeof target[prop] === "number")
            value = Number(value) || 0;

        target[prop] = value;

        if (!target._silent) {
            const api = sdrApiMap[prop];
            if (api) {
                fetch(`./sdr/${api.endpoint}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ [api.key]: value })
                });
            }
            target._notify(prop, value);
        }
        return true;
    }
});


/*
    Export
*/
window.sdrState = sdrState;
