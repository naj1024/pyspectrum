'use strict';

// GLOBALS !!!
var data_active = false; // true when we are connected and receiving data
var spectrum = null;     // don't like this global but can't get onclick in table of markers to work
var sdrState = null;     // holds basics about the fron end sdr
var websocket = null;
var updateTimer = null;  // for when we are not streaming we still need to update the display

// messages for the controls being sent back on the websocket
var fps = {
    type: "fps",
    value: 20
}
var stop = {
    type: "stop",
    value: false
}


async function handleBlob(spec, binary_blob_data) {
    // TODO: handle different types of data

    // extract the data out of the binary blob, been packed up by the python in a struct.
    // See the python WebSocketServer code for the format of the blob

    let buffer = await binary_blob_data.arrayBuffer();

    // data is network order, i.e. big endian
    // access the data as a buffer of bytes
    let data_bytes = new Uint8Array(buffer);
    // and allow different views on the data
    let dataView = new DataView(data_bytes.buffer);

    let index = 0;
    let data_type = dataView.getInt32((index), false);
    index += 4;

    // assume magnitude data for now
    if (data_type != 1) {
        console.log("Received non-magnitude data from websocket, type", data_type);
    } else {
        // mixed int and floats
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
        // TODO refactor so there is only one holding these values, sdrState
        let update = false;
        if ( (spec.getSps() != spsHz) ||
                (spec.getCentreFreqHz() != parseInt(cfMHz*1e6)) ||
                (spec.getFftSize() != num_floats) ||
                spec.getResetAvgChanged() ||
                spec.getResetZoomChanged() ) {

            sdrState.setCentreFrequencyHz(cfMHz*1e6);
            sdrState.setSps(spsHz);
            sdrState.setBw(spsHz);
            sdrState.setFftSize(num_floats);

            spec.setSps(spsHz);
            spec.setSpanHz(spsHz);
            spec.setCentreFreq(cfMHz);
            // spec.setFftSize(num_floats); // don't do this hear
            spec.updateAxes();
            update=true;
        }
        spec.addData(peaks, start_time_sec, start_time_nsec, end_time_sec, end_time_nsec);
        console.log("add")
        if (update) {
            updateConfigTable(spec);
        }
    }
}

function handleCfChange(newCf) {
    sdrState.setCentreFrequencyHz(newCf*1e6);
    sdrState.setSdrStateUpdated();
}

function handleSpsChange(newSps) {
    sdrState.setSps(newSps*1e6);
    sdrState.setSdrStateUpdated();
}

function handleFftChange(newFft) {
    sdrState.setFftSize(newFft);
    sdrState.setSdrStateUpdated();
}

function handleFpsChange(newFps) {
    if ((websocket.readyState == 1) && newFps != fps.value) {
        fps.value = newFps;
        let jsonString= JSON.stringify(fps);
        websocket.send(jsonString);
    }
}

function handleStopToggle() {
    stop.value = !stop.value;
    let jsonString= JSON.stringify(stop);
    if (websocket.readyState == 1) {
        websocket.send(jsonString);
    }
    if (stop.value) {
        // keep updating while stopped, and turn on the live marker
        updateTimer = setInterval(function() { spectrum.liveMarkersAndUnHideMarkers(); spectrum.updateWhenPaused(); }, 100);
    } else {
        if (updateTimer) {
            clearInterval(updateTimer)
        }
    }
}

function handlePauseToggle() {
    // when we pause we will also set stop if it is not already set
    if (!stop.value) {
        handleStopToggle();
        $("#stopBut").button('toggle'); // update the UI button state
    }
    spectrum.togglePaused();
}

function updateConfigTable(spec) {
    // clear the config
    let num_rows = document.getElementById("configTable").rows.length - 1; // -1 for header
    for (let i=num_rows; i > 0; i--) {
        $("#configTable tr:eq("+i+")").remove();
    }

    let cf =  sdrState.getCentreFrequencyHz();
    let sps = sdrState.getSps();

    let cf_step = 0.000001; // 1Hz - annoyingly if we set it to sps/4 say then you can't go finer than that
    let new_row="<tr><td><b>Centre</b></td>";
    new_row += '<td>';
    new_row += '<form action="javascript:handleCfChange(centreFrequencyInput.value)">';
    new_row += '<input type="number" min="0" step="';
    new_row += cf_step;
    new_row += '" value="';
    new_row += (cf/1e6).toFixed(6);
    new_row += '" id="centreFrequencyInput" name="centreFrequencyInput">';
    new_row += '<input type=submit id="submitbtn">';
    new_row += 'MHz</form></td></tr>';
    $('#configTable').append(new_row);

    let sps_step = 0.000001; // 1Hz
    new_row="<tr><td><b>SPS</b></td>";
    new_row += '<td><form action="javascript:handleSpsChange(spsInput.value)">';
    new_row += '<input type="number" min="0" step="';
    new_row += sps_step;
    new_row += '" value="';
    new_row += (sps/1e6).toFixed(6);
    new_row += '" id="spsInput" name="spsInput">';
    new_row += "Msps</form></td></tr>";
    $('#configTable').append(new_row);

    let fftSize = sdrState.getFftSize();
    new_row="<tr><td><b>FFT</b></td>";
    new_row += '<td><form action="javascript:handleFftChange(fftSizeInput.value)">';
    new_row += '<select id="fftSizeInput" name="fftSizeInput" onchange="this.form.submit()">';
    new_row += '<option value="16384" '+((fftSize==16384)?"selected":"")+'>16384</option>';
    new_row += '<option value="8192" '+((fftSize==8192)?"selected":"")+'>8192</option>';
    new_row += '<option value="4096" '+((fftSize==4096)?"selected":"")+'>4096</option>';
    new_row += '<option value="2048" '+((fftSize==2048)?"selected":"")+'>2048</option>';
    new_row += '<option value="1024" '+((fftSize==1024)?"selected":"")+'>1024</option>';
    new_row += '<option value="512" '+((fftSize==512)?"selected":"")+'>512</option>';
    new_row += '<option value="256" '+((fftSize==256)?"selected":"")+'>256</option>';
    new_row += '</select></form></td></tr>';
    $('#configTable').append(new_row);

    let fpsV = fps.value;
    new_row="<tr><td><b>FPS</b></td>";
    new_row += '<td><form action="javascript:handleFpsChange(fpsSizeInput.value)">';
    new_row += '<select id="fpsSizeInput" name="fpsSizeInput" onchange="this.form.submit()">';
    new_row += '<option value="5" '+((fpsV==5)?"selected":"")+'>5</option>';
    new_row += '<option value="10" '+((fpsV==10)?"selected":"")+'>10</option>';
    new_row += '<option value="20" '+((fpsV==20)?"selected":"")+'>20</option>';
    new_row += '<option value="30" '+((fpsV==30)?"selected":"")+'>30</option>';
    new_row += '<option value="50" '+((fpsV==50)?"selected":"")+'>50</option>';
    new_row += '<option value="100" '+((fpsV==100)?"selected":"")+'>100</option>';
    new_row += '<option value="150" '+((fpsV==150)?"selected":"")+'>150</option>';
    new_row += '<option value="200" '+((fpsV==200)?"selected":"")+'>200</option>';
    new_row += '<option value="400" '+((fpsV==400)?"selected":"")+'>400</option>';
    new_row += "</select></form></td></tr>";
    $('#configTable').append(new_row);

    new_row="<tr><td><b>max FPS</b></td><td>"+spec.getmaxFps()+"</td></tr>";
    $('#configTable').append(new_row);

    new_row="<tr><td><b>BW</b></td><td>"+spec.convertFrequencyForDisplay(sps,3)+"</td></tr>";
    $('#configTable').append(new_row);
    new_row="<tr><td><b>RBW</b></td><td>"+spec.convertFrequencyForDisplay(sps/sdrState.getFftSize(),3)+"</td></tr>";
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
    new_row="<tr><td><b>Span</b></td><td>"+spec.convertFrequencyForDisplay(zoomBw,3)+"</td></tr>";
    $('#configTable').append(new_row);
}

function connectWebSocket(spec) {
    let server_hostname = window.location.hostname;
    let server_port = parseInt(window.location.port) + 1;
    let server = "ws://"+server_hostname+":"+server_port+"/";
    console.log("Connecting to", server);
    websocket = new WebSocket(server);

    websocket.onopen = function(event) {
        // Update the status led
        $("#connection_state").empty();
        let new_element = '<img src="./icons/led-yellow.png" alt="connected" title="Connected" >';
        $('#connection_state').append(new_element);

        stop.value = false;
        let jsonString= JSON.stringify(stop);
        websocket.send(jsonString);
    }

    websocket.onclose = function(event) {
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

    websocket.onerror = function(event) {
        console.log("WebSocket error: " + event.message);
        data_active = false;
        // Update the status led
        let new_element = '<img src="./icons/led-red.png" alt="no connection title="No connection" ">';
        $("#connection_state").empty();
        $('#connection_state').append(new_element);

    }

    websocket.onmessage = function (event) {
        if (data_active == false){
            data_active = true;
            // Update the status led
            $("#connection_state").empty();
            let new_element = '<img src="./icons/led-green.png" alt="data active" title="Data active">';
            $('#connection_state').append(new_element);
        }
        // if we are stopped then ignore this blob
        if (!stop.value) {
            handleBlob(spec, event.data);
        }
        // have we something to send back to the server
        if (sdrState.getResetSdrStateUpdated()) {
            let jsonString= JSON.stringify(sdrState);
            websocket.send(jsonString);
        }
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

function Main() {
    let not_supported=check_for_support();
    if (not_supported != ""){
        alert("Error: Sorry - required support not found"+not_supported);
        return;
    }

    // add the spectrum to the page
    let sp='<canvas id="spectrumanalyser" height="500px" width="1024px" style="cursor: crosshair;"></canvas>';
    $('#specCanvas').append(sp);

    // Create spectrum object on canvas with ID "spectrumanalyser"
    spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 50
    });

    // create sdrState object
    sdrState = new sdrState("unknown");

    // config
    let rhcol = '<table id="configTable" class="table table-hover table-striped table-bordered table-sm">';
    rhcol += '<thead class="thead-dark">';
    rhcol += '<tr>';
    rhcol += '<th scope="col">Param</th>';
    rhcol += '<th scope="col">Value</th>';
    rhcol += '</tr>';
    rhcol += '</thead>';
    rhcol += '<tbody>';
    rhcol += '</tbody>';
    rhcol += '</table>';
    $('#configTab').append(rhcol);

    // controls
    rhcol = '<div id="buttons"></div>'; // standard buttons
    $('#displayTab').append(rhcol);

    // markers
    rhcol = '<b>Live </b>';
    rhcol += '<div class="custom-control custom-radio custom-control-inline">';
    rhcol += '<input type="radio" value="off" class="custom-control-input" id="markerRadio_off" name="markerRadio" checked="checked">';
    rhcol += '<label class="custom-control-label" for="markerRadio_off">Off</label>';
    rhcol += '</div>';
    rhcol += '<div class="custom-control custom-radio custom-control-inline">';
    rhcol += '<input type="radio" value="on" class="custom-control-input" id="markerRadio_on" name="markerRadio">';
    rhcol += '<label class="custom-control-label" for="markerRadio_on">On</label>';
    rhcol += '</div>';

    rhcol += '<div id="marker-buttons"></div>';

    rhcol += '<div id="theMarkerTable">'
    rhcol += '<table id="markerTable" class="table-condensed table-hover table-striped table-bordered table-sm">';
    rhcol += '<thead class="thead-dark">';
    rhcol += '<tr>';
    rhcol += '<th scope="col">#</th>';
    rhcol += '<th scope="col">V</th>';
    rhcol += '<th scope="col">MHz</th>';
    rhcol += '<th scope="col">dB</th>';
    rhcol += '<th scope="col">time</th>';
    rhcol += '<th scope="col" colspan="3">Deltas: Hz, dB, sec</th>';
    rhcol += '<th scope="col">X</th>';
    rhcol += '</tr>';
    rhcol += '</thead>';
    rhcol += '<tbody>';
    rhcol += '</tbody>';
    rhcol += '</table>';
    rhcol += '</div>';

    $('#markersTab').append(rhcol);

    let canvas = document.getElementById('spectrumanalyser');

    // keypresses
    window.addEventListener("keydown", function (e) {
        spectrum.onKeypress(e);
    });

    // mouse events
    canvas.addEventListener('mousemove', function(evt) {
        spectrum.handleMouseMove(evt);
    }, false);
    canvas.addEventListener('mouseout', function(evt) {
        spectrum.handleMouseOut(evt);
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

    // stream button
    let main_buttons = '<h4>Stream</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="stopBut" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Stop</button>';
    main_buttons += '</div>'

     // main buttons
    main_buttons += '<h4>Trace</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="pauseBut" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Hold</button>';
    main_buttons += '<button type="button" id="maxHoldBut" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Peak</button>';
    main_buttons += '<button type="button" id="avgDwnBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg-</button>';
    main_buttons += '<button type="button" id="avgUpBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg+</button>';
    main_buttons += '<button type="button" id="avgOffBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg0</button>';
    main_buttons += '</div>'

    main_buttons += '<h4>Magnitude</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="refUpBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Ref-</button>';
    main_buttons += '<button type="button" id="refDwnBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Ref+</button>';
    main_buttons += '<button type="button" id="rangeDwnBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Rng-</button>';
    main_buttons += '<button type="button" id="rangeUpBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Rng+</button>';
    main_buttons += '<button type="button" id="autoRangeBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Auto</button>';
    main_buttons += '</div>';

    main_buttons += '<h4>Span</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="zoomIn" class="specbuttons btn btn-outline-dark mx-1 my-1">Spn-</button>';
    main_buttons += '<button type="button" id="zoomOut" class="specbuttons btn btn-outline-dark mx-1 my-1">Spn+</button>';
    main_buttons += '<button type="button" id="unZoomBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Full</button>';
    main_buttons += '</div>';

    // btn-block
    $('#buttons').append(main_buttons);

    let marker_buttons = '<div">';
    marker_buttons = '<button type="button" id="hideMarkersBut" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Hide</button>';
    marker_buttons += '<button type="button" id="clearMarkersBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Clr&nbsp</button>';
    marker_buttons += '<button type="button" id="searchPeakBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Peak</button>';
    marker_buttons += '<button type="button" id="searchNextPeakBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Next</button>';
    marker_buttons += '<button type="button" id="peakTrackBut" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Trck</button>';
    marker_buttons += '</div>';
    $('#marker-buttons').append(marker_buttons);

    // events
    $('#configButton').click(function() {showConfig();});
    $('#controlButton').click(function() {showControls();});
    $('#markerButton').click(function() {showMarkers();});

    $('#stopBut').click(function() {handleStopToggle();});

    $('#pauseBut').click(function() {handlePauseToggle();});
    $('#maxHoldBut').click(function() {spectrum.toggleMaxHold();});
    $('#avgUpBut').click(function() {spectrum.incrementAveraging();});
    $('#avgDwnBut').click(function() {spectrum.decrementAveraging();});
    $('#avgOffBut').click(function() {spectrum.setAveraging(0);});

    $('#refDwnBut').click(function() {spectrum.refDown();});
    $('#refUpBut').click(function() {spectrum.refUp();});
    $('#rangeDwnBut').click(function() {spectrum.rangeDecrease();});
    $('#rangeUpBut').click(function() {spectrum.rangeIncrease();});
    $('#autoRangeBut').click(function() {spectrum.autoRange();});

    $('#zoomIn').click(function() {spectrum.zoomIn();});
    $('#zoomOut').click(function() {spectrum.zoomOut();});
    $('#unZoomBut').click(function() {spectrum.resetZoom();});

    $('#markerRadio_off').click(function() {spectrum.liveMarkerOff();});
    $('#markerRadio_on').click(function() {spectrum.liveMarkerOn();});
    $('#clearMarkersBut').click(function() {spectrum.clearMarkers();});
    $('#hideMarkersBut').click(function() {spectrum.hideMarkers();});
    $('#searchPeakBut').click(function() {spectrum.findPeak();});
    $('#searchNextPeakBut').click(function() {spectrum.findNextPeak();});
    $('#peakTrackBut').click(function() {spectrum.toggleTrackPeak();});

    // Connect to websocket
    connectWebSocket(spectrum);
}

window.onload = Main;
