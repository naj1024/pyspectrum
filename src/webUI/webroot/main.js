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

    // mixed int and floats
    let index = 0;
    let sps = dataView.getInt32((index), false);
    index += 4;
    let cf = dataView.getFloat32((index), false);
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
    spectrum.setCenterMHz(cf);
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

function check_for_support(){
    let ok="";
    let test_canvas = document.createElement("canvas");
    let canvas_ok=(test_canvas.getContext)? true:false;
    if (!canvas_ok){
        ok += ", No canvas";
    }
    let test_blob = new Blob(["hello"], {type: 'text/html'});
    let blob_ok=(test_blob)? true:false;
    if(!blob_ok){
        ok+=", No blob";
    }else{
        try{
            let test_blob_arrayBuffer = test_blob.arrayBuffer();
            try{
                let data_bytes = new Uint8Array(test_blob_arrayBuffer);
                let dataView = new DataView(data_bytes.buffer);
            } catch (err){
                ok+=", No DataView";
            }
        }catch (err){
            ok+=", No blob arrayBuffer";
        }
    }
    return(ok);
}

function main() {
    let not_supported=check_for_support();
    if (not_supported != ""){
        alert("Error: Sorry - required HTML support not found"+not_supported);
        return;
    }

    // Create spectrum object on canvas with ID "spectrumanalyser"
    var spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 50
    });

    // keypresses
    window.addEventListener("keydown", function (e) {
        spectrum.onKeypress(e);
    });

    // mouse events
    var canvas = document.getElementById('spectrumanalyser');
    canvas.addEventListener('mousemove', function(evt) {
        let mouse_ptr = spectrum.getMouseValue(evt);
        if (mouse_ptr){
            spectrum.setLiveMarker((mouse_ptr.freq / 1e6).toFixed(3)+"MHz", mouse_ptr.x, mouse_ptr.y);
        }
    }, false);
    canvas.addEventListener('click', function(evt) {
        let mouse_ptr = spectrum.getMouseValue(evt);
        if (mouse_ptr){
            spectrum.addMarkerMHz((mouse_ptr.freq / 1e6).toFixed(3), mouse_ptr.x);
        }
    }, false);

    // bootstrap buttons
    var our_buttons = '<button type="button" id="pauseBut" data-toggle="button" class="btn btn-outline-dark btn-sm mr-1">Pause</button>';
    our_buttons += '<button type="button" id="maxHoldBut" data-toggle="button" class="btn btn-outline-dark btn-sm mr-1">MaxHold</button>';
    our_buttons += '<button type="button" id="peakBut" data-toggle="button" class="btn btn-outline-dark btn-sm mr-1">Peaks</button>';
    our_buttons += '<button type="button" id="clearMarkers" class="btn btn-outline-dark btn-sm mr-1">ClearMarkers</button>';
    $('#buttons').append(our_buttons);
    // bootstrap events
    $('#pauseBut').click(function() {spectrum.togglePaused();});
    $('#maxHoldBut').click(function() {spectrum.toggleMaxHold();});
    $('#peakBut').click(function() {spectrum.toggleLive();});
    $('#clearMarkers').click(function() {spectrum.clearMarkers();});

    // Connect to websocket
    connectWebSocket(spectrum);
}

window.onload = main;
