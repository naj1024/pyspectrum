'use strict';

var data_active = false; // true when we are connected and receiving data
var spectrum = null;     // don't like this global but can't get onclick in table of markers to work

async function handleData(spec, binary_blob_data) {
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
    let spsHz = dataView.getInt32((index), false);
    index += 4;
    let cfMHz = dataView.getFloat32((index), false);
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

    let peaks = new Float32Array(num_floats);
    for (var i=0; i<num_floats; i++){
        peaks[i]=dataView.getFloat32((index), false);
        index += 4;
    }

    // tell the spectrum how this data is configured, which could change
    let update = false;
    if ( (spec.getSps() != spsHz) ||
            (spec.getcentreFreqHz() != parseInt(cfMHz*1e6)) ||
            (spec.getFftSize() != num_floats) ||
            spec.getResetAvgChanged() ||
            spec.getResetZoomChanged() ) {
        spec.setSps(spsHz);
        spec.setSpanHz(spsHz);
        spec.setcentreFreq(cfMHz);
        spec.updateAxes();
        update=true;
    }
    spec.addData(peaks, start_time_sec, start_time_nsec, end_time_sec, end_time_nsec);
    if (update) {
        updateConfigTable(spec);
    }
}

function updateConfigTable(spec) {
    // clear the config
    let num_rows = 8; // because we know we have 8
    for (let i=num_rows; i > 0; i--) {
        $("#configTable tr:eq("+i+")").remove();
    }
    let new_row="<tr><td><b>Centre</b></td><td>"+spec.convertFrequencyForDisplay(spec.getcentreFreqHz(),3)+"</td></tr>";
    $('#configTable').append(new_row);
    let sps = spec.getSps();
    new_row="<tr><td><b>SPS</b></b></td><td>"+spec.convertFrequencyForDisplay(sps,3)+"</td></tr>";
    $('#configTable').append(new_row);
    new_row="<tr><td><b>BW</b></td><td>"+spec.convertFrequencyForDisplay(sps,3)+"</td></tr>";
    $('#configTable').append(new_row);
    new_row="<tr><td><b>RBW</b></td><td>"+spec.convertFrequencyForDisplay(sps/spec.getFftSize(),3)+"</td></tr>";
    $('#configTable').append(new_row);
    let start=spec.getStartTime();
    let seconds = parseInt(start);
    let usec = parseInt((start-seconds)*1e6);
    new_row="<tr><td><b>Start</b></td><td>"+seconds+"Sec + "+usec.toFixed(0)+"usec</td></tr>";
    $('#configTable').append(new_row);
    new_row="<tr><td><b>Avg</b></td><td>"+spec.averaging+"</td></tr>";
    $('#configTable').append(new_row);
    new_row="<tr><td><b>Zoom</b></td><td>"+spec.zoom+"</td></tr>";
    $('#configTable').append(new_row);
    let zoomBw = sps/spec.zoom;
    new_row="<tr><td><b>Zoom BW</b></td><td>"+spec.convertFrequencyForDisplay(zoomBw,3)+"</td></tr>";
    $('#configTable').append(new_row);
}

function connectWebSocket(spec) {
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
            connectWebSocket(spec);
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
        // TODO: handle different types of data
        handleData(spec, event.data);
    }
}

function check_for_support(){
    let ok="";
    let test_canvas = document.createElement("canvas");
    let canvas_ok = (test_canvas.getContext)? true:false;
    if (!canvas_ok){
        ok += ", No canvas";
    }
    let test_blob = new Blob(["hello"], {type: 'text/html'});
    let blob_ok = (test_blob)? true:false;
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

function showConfig() {
  var x = document.getElementById("config");
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }
}
function showControls() {
  var x = document.getElementById("controls");
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }
}
function showMarkers() {
  var x = document.getElementById("markers");
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }
}

function main() {
    let not_supported=check_for_support();
    if (not_supported != ""){
        alert("Error: Sorry - required support not found"+not_supported);
        return;
    }

    // add the spectrum to the page
    let sp='<canvas id="spectrumanalyser" height="500px" width="1024px" style="cursor: crosshair;"></canvas>';
    $('#specCanvas').append(sp);

    // the controls etc
    let rhcol = '<div>';
    // config
    rhcol += '<button type="button" id="configButton" data-toggle="button" class="btn-block btn btn-outline-dark mx-1 my-1">Config</button>';
    rhcol += '<div id="config">';
    rhcol += '<table id="configTable" class="table table-hover table-striped table-bordered table-sm">';
    rhcol += '<thead class="thead-dark">';
    rhcol += '<tr>';
    rhcol += '<th scope="col">Param</th>';
    rhcol += '<th scope="col">Value</th>';
    rhcol += '</tr>';
    rhcol += '</thead>';
    rhcol += '<tbody>';
    rhcol += '</tbody>';
    rhcol += '</table>';
    rhcol += '</div>';
    rhcol += '</div>';

    // controls
    rhcol += '<div>';
    rhcol += '<button type="button" id="controlButton" data-toggle="button" class="btn-block btn btn-outline-dark mx-1 my-1">Control</button>';
    rhcol += '<div id="controls">';
    rhcol += '<div id="buttons"></div>'; // standard buttons
    rhcol += '</div>';
    rhcol += '</div>';

    // markers
    rhcol += '<div>';
    rhcol += '<button type="button" id="markerButton" data-toggle="button" class="btn-block btn btn-outline-dark mx-1 my-1">Markers</button>';
    rhcol += '<div id="markers">';
    rhcol += '<b>Live </b>';
    rhcol += '<div class="custom-control custom-radio custom-control-inline">';
    rhcol += '<input type="radio" value="off" class="custom-control-input" id="markerRadio_off" name="markerRadio" checked="checked">';
    rhcol += '<label class="custom-control-label" for="markerRadio_off">Off</label>';
    rhcol += '</div>';
    rhcol += '<div class="custom-control custom-radio custom-control-inline">';
    rhcol += '<input type="radio" value="on" class="custom-control-input" id="markerRadio_on" name="markerRadio">';
    rhcol += '<label class="custom-control-label" for="markerRadio_on">On</label>';
    rhcol += '</div>';

    rhcol += '<div id="marker-buttons"></div>';

    rhcol += '<table id="markerTable" class="table-condensed table-hover table-striped table-bordered table-sm">';
    rhcol += '<thead class="thead-dark">';
    rhcol += '<tr>';
    rhcol += '<th scope="col">#</th>';
    rhcol += '<th scope="col">V</th>';
    rhcol += '<th scope="col">MHz</th>';
    rhcol += '<th scope="col">dB</th>';
    rhcol += '<th scope="col">time</th>';
    rhcol += '<th scope="col">D MHz</th>';
    rhcol += '<th scope="col">D dB</th>';
    rhcol += '<th scope="col">D Sec</th>';
    rhcol += '<th scope="col">x</th>';
    rhcol += '</tr>';
    rhcol += '</thead>';
    rhcol += '<tbody>';
    rhcol += '</tbody>';
    rhcol += '</table>';
    rhcol += '</div>';

    rhcol += '</div>';
    rhcol += '</div>';

    $('#metaData').append(rhcol);

    // Create spectrum object on canvas with ID "spectrumanalyser"
    spectrum = new Spectrum(
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
    canvas.addEventListener('click', function(evt) { // left mouse click by default
        spectrum.handleLeftMouseClick(evt);
    }, false);
    canvas.addEventListener('wheel', function(evt) {
        spectrum.handleMouseWheel(evt);
    }, false);

    // remove default canvas context menu if need to handle right mluse click
    // then you can add an event listener for contextmenu as the right mouse click
    // $('body').on('contextmenu', '#spectrumanalyser', function(e){ return false; });

     // main buttons
    let main_buttons = '<div class="btn-group">';
    main_buttons += '<button type="button" id="pauseBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Pause</button>';
    main_buttons += '<button type="button" id="maxHoldBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Max</button>';
    main_buttons += '<button type="button" id="avgDwnBut" class="btn btn-outline-dark mx-1 my-1">Avg--</button>';
    main_buttons += '<button type="button" id="avgUpBut" class="btn btn-outline-dark mx-1 my-1">Avg++</button>';
    main_buttons += '</div>'

    main_buttons += '<div class="btn-group">';
    main_buttons += '<button type="button" id="refUpBut" class="btn btn-outline-dark mx-1 my-1">Ref--</button>';
    main_buttons += '<button type="button" id="refDwnBut" class="btn btn-outline-dark mx-1 my-1">Ref++</button>';
    main_buttons += '<button type="button" id="rangeDwnBut" class="btn btn-outline-dark mx-1 my-1">Range--</button>';
    main_buttons += '<button type="button" id="rangeUpBut" class="btn btn-outline-dark mx-1 my-1">Range++</button>';
    main_buttons += '</div>';

    main_buttons += '<div class="btn-group">';
    main_buttons += '<button type="button" id="unZoomBut" class="btn btn-outline-dark mx-1 my-1">UnZoom</button>';
    main_buttons += '</div>';


    // btn-block
    $('#buttons').append(main_buttons);

    // todo add auto peak detect button
    let marker_buttons = '<button type="button" id="hideMarkersBut" data-toggle="button" class="btn btn-outline-dark mx-1 my-1">Hide</button>';
    marker_buttons += '<button type="button" id="clearMarkersBut" class="btn btn-outline-dark mx-1 my-1">Clear</button>';
    $('#marker-buttons').append(marker_buttons);

    // events
    $('#configButton').click(function() {showConfig();});
    $('#controlButton').click(function() {showControls();});
    $('#markerButton').click(function() {showMarkers();});

    $('#pauseBut').click(function() {spectrum.togglePaused();});
    $('#maxHoldBut').click(function() {spectrum.toggleMaxHold();});
    $('#avgUpBut').click(function() {spectrum.incrementAveraging();});
    $('#avgDwnBut').click(function() {spectrum.decrementAveraging();});
    $('#unZoomBut').click(function() {spectrum.resetZoom();});

    $('#refDwnBut').click(function() {spectrum.rangeDown();});
    $('#refUpBut').click(function() {spectrum.rangeUp();});
    $('#rangeDwnBut').click(function() {spectrum.rangeDecrease();});
    $('#rangeUpBut').click(function() {spectrum.rangeIncrease();});
    $('#clearMarkersBut').click(function() {spectrum.clearMarkers();});
    $('#hideMarkersBut').click(function() {spectrum.hideMarkers();});

    $('#markerRadio_off').click(function() {spectrum.liveMarkerOff();});
    $('#markerRadio_on').click(function() {spectrum.liveMarkerOn();});

    // Connect to websocket
    connectWebSocket(spectrum);
}

window.onload = main;
