'use strict';

/* =========================
   APP STATE
========================= */
const App = {
    state: {
        spectrum: null,
        sdr: null,
        snap: null,
        websocket: null,
        dataActive: false,
        configFocus: false,
        snapFocus: false
    }
};

/* =========================
   API LAYER
========================= */
const api = {
    async get(url) {
        const res = await fetch(url);
        return res.json();
    },

    async put(url, data) {
        const res = await fetch(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        return res.json();
    },

    async del(url, data) {
        const res = await fetch(url, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        return res.json();
    }
};

/* =========================
   GENERIC UPDATE HANDLER
========================= */
async function updateSetting({ url, key, value, apply }) {
    try {
        await api.put(url, { [key]: value });
        if (apply) apply(value);
    } catch (e) {
        console.error("Update failed:", e);
    }
}

/* =========================
   UI HELPERS
========================= */
function createSelect({ id, options, value, onChange }) {
    const select = $('<select>').attr({ id });

    options.forEach(opt => {
        select.append(
            $('<option>')
                .val(opt)
                .text(opt)
                .prop('selected', opt === value)
        );
    });

    select.on('change', e => onChange(e.target.value));
    return select;
}

/* =========================
   SDR HANDLERS (CLEAN)
========================= */
const handlers = {
    gain: (v) => updateSetting({
        url: "./digitiser/digitiserGain",
        key: "digitiserGain",
        value: v,
        apply: val => App.state.sdr.gain = val
    }),

    fps: (v) => updateSetting({
        url: "./control/fps",
        key: "fps",
        value: { set: v, measured: 0 }
    }),

    fft: (v) => updateSetting({
        url: "./spectrum/fftSize",
        key: "fftSize",
        value: v,
        apply: val => App.state.sdr.fftSize = val
    }),

    psd: (v) => updateSetting({
        url: "./spectrum/psd",
        key: "psd",
        value: v,
        apply: val => {
            App.state.sdr.setPsd(val);
            App.state.spectrum.setPsd(val);
        }
    }),

    frequency: (mhz) => {
        const hz = mhz * 1e6;
        updateSetting({
            url: "./tuning/frequency",
            key: "value",
            value: hz,
            apply: () => {
                App.state.sdr.setFrequencyHz(hz);
                App.state.spectrum.setCentreFreqHz(hz);
                App.state.spectrum.updateAxes();
            }
        });
    }
};

/* =========================
   SYNC FUNCTIONS
========================= */
async function syncCurrent() {
    try {
        const obj = await api.get('./status/currentStatus');

        App.state.sdr.setConfigFromJason(obj);
        App.state.snap.setConfigFromJason(obj);

        render.current();
    } catch (e) {
        console.error(e);
    }
}

async function syncFast() {
    try {
        const obj = await api.get('./status/fastStatus');

        App.state.sdr.setConfigFromJason(obj);
        App.state.snap.setConfigFromJason(obj);

        render.fast(obj);
    } catch (e) {
        console.error(e);
    }
}

/* =========================
   RENDERING
========================= */
const render = {
    current() {
        const sdr = App.state.sdr;

        $('#currentSps').text((sdr.sps/1e6).toFixed(6)+' Msps');
        $('#currentGain').text(sdr.gain + ' dB');
    },

    fast(obj) {
        $('#currentDelay').text(obj.delay.toFixed(2));
        $('#currentOverflows').text(obj.overflows);
    }
};

/* =========================
   SNAP TABLE
========================= */
function updateSnapFileList() {
    const snap = App.state.snap;
    $("#snapFileTable tbody").empty();

    snap.directoryList.forEach((file, i) => {
        const row = $(`
            <tr>
                <td><a href="snapshots/${file[0]}">${file[0]}</a></td>
                <td>${file[1]}</td>
                <td><img src="./thumbnails/${file[0]}.png"></td>
                <td><button id="play_${i}">▶</button></td>
                <td><button id="del_${i}">🗑</button></td>
            </tr>
        `);

        row.find(`#play_${i}`).click(() => {
            handlers.input?.("file", file[0]);
        });

        row.find(`#del_${i}`).click(async () => {
            await api.del("./snapshot/snapDelete", { snapDelete: file[0] });
        });

        $('#snapFileTable').append(row);
    });
}

/* =========================
   WEBSOCKET
========================= */
class SpectrumSocket {
    constructor(onData, onStatus) {
        this.onData = onData;
        this.onStatus = onStatus;
    }

    connect() {
        const url = `ws://${location.hostname}:${+location.port + 1}/`;
        const ws = new WebSocket(url);

        this.ws = ws;

        ws.onopen = () => this.onStatus("connected");
        ws.onclose = () => this.onStatus("disconnected");
        ws.onerror = () => this.onStatus("error");

        ws.onmessage = (e) => {
            if (e.data instanceof Blob) {
                this.onData(e.data);
            }
        };
    }
}

/* =========================
   BLOB HANDLER 
========================= */
async function handleBlob(blob) {
    const buffer = await blob.arrayBuffer();
    const view = new DataView(buffer);

    let index = 0;
    const type = view.getInt32(index, false); index += 4;

    if (type !== 1) return;

    const sps = view.getInt32(index, false); index += 4;
    const cfMHz = view.getFloat64(index, false); index += 8;

    index += 16; // skip timestamps

    const num = view.getInt32(index, false); index += 4;

    const peaks = new Float32Array(num);
    for (let i = 0; i < num; i++) {
        peaks[i] = view.getFloat32(index, false);
        index += 4;
    }

    const spec = App.state.spectrum;
    const sdr = App.state.sdr;

    const cfHz = cfMHz * 1e6;

    if (sdr.sps !== sps) {
        sdr.sps = sps;
        spec.setSps(sps);
    }

    if (sdr.sdrFrequencyHz !== cfHz) {
        sdr.sdrFrequencyHz = cfHz;
        spec.setCentreFreqHz(cfHz);
    }

    spec.addData(peaks);
}

/* =========================
   SCHEDULER
========================= */
function scheduler(tasks) {
    tasks.forEach(({ fn, interval }) => {
        setInterval(async () => {
            try { await fn(); }
            catch (e) { console.error(e); }
        }, interval);
    });
}

/* =========================
   MAIN
========================= */
function Main() {

    App.state.snap = window.snapState;
    App.state.sdr = window.sdrState;

    // create spectrum
    $('#specCanvas').append(
        '<canvas id="spectrumanalyser" width="1024" height="600"></canvas>'
    );

    App.state.spectrum = new Spectrum("spectrumanalyser", {
        spectrumPercent: 50
    });

    // websocket
    const socket = new SpectrumSocket(
        handleBlob,
        (status) => console.log("WS:", status)
    );
    socket.connect();

    // initial sync
    syncCurrent();
    syncFast();

    // scheduler
    scheduler([
        { fn: syncCurrent, interval: 1500 },
        { fn: syncFast, interval: 700 }
    ]);

    // example UI binding
    $('#gainInput').on('change', e => handlers.gain(e.target.value));
}

window.onload = Main;
