'use strict';

var data_active=false;
var samples_per_second =0.0;
var centre_frequency = 0.0;

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
    let start_time_sec = dataView.getInt32((index), false);
    index += 4;
    let start_time_nsec = dataView.getInt32((index), false);
    index += 4;
    let end_time_sec = dataView.getInt32((index), false);
    index += 4;
    let end_time_nsec = dataView.getInt32((index), false);
    index += 4;
    let num_floats = dataView.getInt32((index), false);
    index += 4;

    // two arrays of floats
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

    // tell the spectrum how this data is configured, which could change
    spectrum.setSpanHz(sps);
    spectrum.setCenterMHz(cf);
    spectrum.addData(magnitudes, peaks, start_time_sec, start_time_nsec, end_time_sec, end_time_nsec);

    updateConfigTable(spectrum, sps, cf, num_floats);
}

function updateConfigTable(spectrum, sps, cf, points) {
    // clear the config
    samples_per_second = sps;
    centre_frequency = cf;
    let num_rows=5; // because we know
    for (let i=num_rows; i>0; i--) {
        $("#config_table tr:eq("+i+")").remove();
    }
    let new_row="<tr><td><b>Centre</b></td><td>"+cf.toFixed(3)+"MHz</td></tr>";
    $('#config_table').append(new_row);
    new_row="<tr><td><b>SPS</b></b></td><td>"+(sps/1E6).toFixed(3)+"MHz</td></tr>";
    $('#config_table').append(new_row);
    new_row="<tr><td><b>BW</b></td><td>"+(sps/1E6).toFixed(3)+"MHz</td></tr>";
    $('#config_table').append(new_row);
    new_row="<tr><td><b>RBW</b></td><td>"+((sps/1E3)/points).toFixed(3)+"kHz</td></tr>";
    $('#config_table').append(new_row);
    new_row="<tr><td><b>Avg</b></td><td>"+spectrum.averaging+"</td></tr>";
    $('#config_table').append(new_row);
}

function connectWebSocket(spectrum) {
    let server_hostname = window.location.hostname;
    console.log("Connecting");
    let ws = new WebSocket("ws://"+server_hostname+":5555/");

    ws.onopen = function(event) {
        // Update the status led
        $("#connection_state").empty();
        let new_element = '<img src="./icons/led-yellow.png" alt="connected" title="Connected" >';
        $('#connection_state').append(new_element);
    }

    ws.onclose = function(event) {
        console.log("WebSocket closed");
        data_active = false;
        // Update the status led
        let new_element = '<img src="./icons/led-red.png" alt="no connection title="No connection" ">';
        $("#connection_state").empty();
        $('#connection_state').append(new_element);
        setTimeout(function() {
            connectWebSocket(spectrum);
        }, 1000);
    }

    ws.onerror = function(event) {
        console.log("WebSocket error: " + event.message);
        data_active = false;
        // Update the status led
        let new_element = '<img src="./icons/led-red.png" alt="no connection title="No connection" ">';
        $("#connection_state").empty();
        $('#connection_state').append(new_element);

    }

    ws.onmessage = function (event) {
        if (data_active == false){
            data_active = true;
            // Update the status led
            $("#connection_state").empty();
            let new_element = '<img src="./icons/led-green.png" alt="data active" title="Data active">';
            $('#connection_state').append(new_element);
        }
        handleData(spectrum, event.data);
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
        ok += ", No blob";
    }else{
        try{
            let test_blob_arrayBuffer = test_blob.arrayBuffer();
            try{
                let data_bytes = new Uint8Array(test_blob_arrayBuffer);
                let dataView = new DataView(data_bytes.buffer);
            } catch (err){
                ok += ", No blob DataView";
            }
        }catch (err){
            ok += ", No blob arrayBuffer";
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
    let spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 50
    });

    // keypresses
    window.addEventListener("keydown", function (e) {
        spectrum.onKeypress(e);
    });

    // mouse events
    let canvas = document.getElementById('spectrumanalyser');
    canvas.addEventListener('mousemove', function(evt) {
        spectrum.handleMouseMove(evt);
    }, false);
    canvas.addEventListener('click', function(evt) { // left mouse click
        spectrum.handleLeftMouseClick(evt);
    }, false);
    canvas.addEventListener('contextmenu', function(evt) { // Right click
        spectrum.handleRightMouseClick(evt);
    }, false);
    canvas.addEventListener('wheel', function(evt) {
        spectrum.handleWheel(evt);
    }, false);

    // remove deafult canvas conext menu
    $('body').on('contextmenu', '#spectrumanalyser', function(e){ return false; });

    // bootstrap buttons
    let main_buttons = '<button type="button" id="pauseBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Pause</button>';
    main_buttons += '<button type="button" id="maxHoldBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">MaxHold</button>';
    main_buttons += '<button type="button" id="peakBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Peaks</button>';
    main_buttons += '<button type="button" id="avgDwnBut" class="btn btn-outline-dark mx-1 my-1">Avg --</button>';
    main_buttons += '<button type="button" id="avgUpBut" class="btn btn-outline-dark mx-1 my-1">Avg ++</button>';
    // btn-block
    $('#buttons').append(main_buttons);

    // todo add auto peak detect button
    let marker_buttons = '<button type="button" id="liveMarkerBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Live</button>';
    marker_buttons += '<button type="button" id="clearMarkersBut" class="btn btn-outline-dark mx-1 my-1">ClearMarkers</button>';
    $('#marker-buttons').append(marker_buttons);

    // bootstrap events
    $('#pauseBut').click(function() {spectrum.togglePaused();});
    $('#maxHoldBut').click(function() {spectrum.toggleMaxHold();});
    $('#peakBut').click(function() {spectrum.toggleLive();});
    $('#avgUpBut').click(function() {spectrum.incrementAveraging();});
    $('#avgDwnBut').click(function() {spectrum.decrementAveraging();});
    $('#liveMarkerBut').click(function() {spectrum.liveMarkerOn();});
    $('#clearMarkersBut').click(function() {spectrum.clearMarkers();});

    // Connect to websocket
    connectWebSocket(spectrum);
}

window.onload = main;
