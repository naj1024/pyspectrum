'use strict';

async function handleData(spectrum, binary_blob_data) {
    let buffer = await binary_blob_data.arrayBuffer();

    // data is network order, i.e. big endian
    // access the data as a buffer of bytes
    let data_bytes = new Uint8Array(buffer);
    // and allow different vies on the data
    let dataView = new DataView(data_bytes.buffer);

    // 5 integers
    let index = 0;
    let sps = dataView.getInt32((index), false);
    index += 4;
    let cf = dataView.getInt32((index), false);
    index += 4;
    let time_start = dataView.getInt32((index), false);
    index += 4;
    let time_end = dataView.getInt32((index), false);
    index += 4;
    let num_floats = dataView.getInt32((index), false);
    index += 4;

    // floats
    let magnitudes = new Float32Array(num_floats);
    for (var i=0; i<num_floats; i++){
        magnitudes[i]=dataView.getFloat32((index), false);
        index += 4;
    }
    let peaks = new Float32Array(num_floats);
    for (var i=0; i<num_floats; i++){
        peaks[i]=dataView.getFloat32((index), false);
        index += 4;
    }

    // console.log(sps+" "+cf+" "+time_start+" "+time_end+" "+num_floats+" "+magnitudes[0]);
    spectrum.addData(magnitudes);
}

function connectWebSocket(spectrum) {
    var ws = new WebSocket("ws://127.0.0.1:5555/")
    ws.onopen = function(event) {
        console.log("WebSocket connected");
    }
    ws.onclose = function(event) {
        console.log("WebSocket closed");
        setTimeout(function() {
            connectWebSocket(spectrum);
        }, 1000);
    }
    ws.onerror = function(event) {
        console.log("WebSocket error: " + evt.message);
    }
    ws.onmessage = function (event) {
        handleData(spectrum, event.data)
    }
}

function main() {
    // Create spectrum object on canvas with ID "waterfall"
    var spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 20
    });

    // Connect to websocket
    connectWebSocket(spectrum);

    // Bind keypress handler
    window.addEventListener("keydown", function (e) {
        spectrum.onKeypress(e);
    });
}

window.onload = main;
