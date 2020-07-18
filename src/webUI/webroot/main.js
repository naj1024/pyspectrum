'use strict';

async function handleData(spectrum, binary_blob_data) {
    // extract the data out of the binary blob, been packed up by the python in a struct.
    // See the python WebSocketServer code for the format of the blob

    let buffer = await binary_blob_data.arrayBuffer();

    // data is network order, i.e. big endian
    // access the data as a buffer of bytes
    let data_bytes = new Uint8Array(buffer);
    // and allow different views on the data
    let dataView = new DataView(data_bytes.buffer);

    // 5 integers
    let index = 0;
    let sps = dataView.getInt32((index), false);
    index += 4;
    let cf = dataView.getInt32((index), false);
    index += 4;
    let time_start = dataView.getInt32((index), false); // note - not populated currently for web
    index += 4;
    let time_end = dataView.getInt32((index), false); // note - not populated currently for web
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

    // tell the spectrum how the data is configured
    spectrum.setSpanHz(sps);
    spectrum.setCenterHz(cf);
    spectrum.addData(magnitudes, peaks);
}

function connectWebSocket(spectrum) {
    let server_hostname = window.location.hostname;
    let ws = new WebSocket("ws://"+server_hostname+":5555/")
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
        console.log("WebSocket error: " + event.message);
    }
    ws.onmessage = function (event) {
        handleData(spectrum, event.data)
    }
}

function main() {
    // Create spectrum object on canvas with ID "waterfall"
    var spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 50
    });

    // Connect to websocket
    connectWebSocket(spectrum);

    // Bind keypress handler, lots of key options for controlling the spectrum, TODO: convert to buttons
    window.addEventListener("keydown", function (e) {
        spectrum.onKeypress(e);
    });
}

window.onload = main;
