'use strict';

// GLOBALS !!!
var data_active = false; // true when we are connected and receiving data
var spectrum = null;     // don't like this global but can't get onclick in table of markers to work
var sdrState = null;     // holds basics about the front end sdr
var websocket = null;
var updateTimer = null;  // for when we are not streaming we still need to update the display
var formInFocus = false;

// messages for the controls being sent back on the websocket
var fps = {
    type: "fps",
    value: 20
}
var stop = {
    type: "stop",
    value: false
}
var ack = {
    type: "ack",
    value: 0
}


async function handleBlob(binary_blob_data) {
    // We expect a binary blob in a particular format
    // Extract the data out of the binary blob, which was packed up by the python in a struct.
    // See the python WebSocketServer code for the format of the blob

    try {
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

            let cfMHz = dataView.getFloat64((index), false);
            index += 8;

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

            sdrState.setLastDataTime(start_time_sec);

            // tell the spectrum how this data is configured, which could change
            let update = false;
            if ( (sdrState.getSps() != spsHz) ||
                    (sdrState.getCentreFrequencyHz() != parseInt(cfMHz*1e6)) ||
                    (sdrState.getFftSize() != num_floats) ||
                    spectrum.getResetAvgChanged() ||
                    spectrum.getResetZoomChanged() ) {

                sdrState.setCentreFrequencyHz(cfMHz*1e6);
                sdrState.setSps(spsHz);
                sdrState.setFftSize(num_floats);

                spectrum.setSps(spsHz);
                spectrum.setSpanHz(spsHz);
                spectrum.setCentreFreqHz(cfMHz*1e6);
                // spectrum.setFftSize(num_floats); // don't do this here
                spectrum.updateAxes();
                update=true;
            }
            spectrum.addData(peaks, start_time_sec, start_time_nsec, end_time_sec, end_time_nsec);
            if (update) {
                updateConfigTable(spectrum);
            }
        }
    }
    catch (e)
    {
        console.log("Exception while processing blob from websocket, "+e.message);
    }
}

async function handleJsonControl(controlData) {
    /*
    Don't update UI controls with these values - tends to cause race conditions

    JSON control data, see python Variables.py for expected entries, e.g:
    {
    "fft_size": 2048,
    "sample_rate": 2000000,
    "centre_frequency_hz": 153200000.0,
    "sample_types": ["8t", "8o", "16tbe", "16tle"],
    "sample_type": "16tle",
    "fps": 20,
    "measured_fps": 21,
    "oneInN": 48,
    "update_count": 18,
    "stop": 0,
    "web_port": 8080,
    "input_source": "pluto",
    "input_params": "192.168.2.1",
    "source_sleep": 1e-05,
    "time_first_spectrum": 1606042747878953200,
    "source_connected": false,
    "input_sources": ["audio", "file", "pluto", "rtltcp", "socket"],
    "input_sources_web_helps":
        {
        "audio": "Number - number of the input device e.g. 1",
        "file": "Filename - Filename, binary or wave, e.g. ./xyz.cf123.4.cplx.200000.16tbe", "pluto":
        "IP address - The Ip or resolvable name of the Pluto device, e.g. 192.168.2.1",
        "rtltcp": "IP@port - The Ip or resolvable name and port of an rtltcp server, e.g. 192.168.2.1:12345",
        "socket": "IP:port - The Ip or resolvable name and port of a server, e.g. 192.168.2.1:12345"
        },
    "plugin_options": [],
    "error": ""}
    */
    // console.table(JSON.parse(controlData));
    // console.log(controlData);

    // ignore incoming control if we have updated and NOT sent off that control yet
    if (sdrState.getSdrStateUpdated()) {
        return;
    }

    try {
        let control = JSON.parse(controlData);
        // console.log(control);
        if (control.error.length > 0) {
            alert(control.error);
        }
        let updateCfgTable = sdrState.setFromJason(control);
        if (updateCfgTable) {
            spectrum.updateAxes();
            updateConfigTable(spectrum);
        }

    } catch(err) {
        console.log("JSON control message had an error, ", err, controlData);
    }
}


function handleCfChange(newCfMHz) {
    sdrState.setCentreFrequencyHz(newCfMHz*1e6);
    spectrum.setCentreFreqHz(newCfMHz*1e6);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function setCfHz(newCfHz) {
    console.log(newCfHz);
    sdrState.setCentreFrequencyHz(newCfHz);
    spectrum.setCentreFreqHz(newCfHz);
    sdrState.setSdrStateUpdated();
}
function decrementCf() {
    let newCfHz = sdrState.getCentreFrequencyHz();
    let step = (sdrState.getSps() / spectrum.zoom) / 8;
    newCfHz -= step;
    setCfHz(newCfHz);
}
function incrementCf() {
    let newCfHz = sdrState.getCentreFrequencyHz();
    let step = (sdrState.getSps() / spectrum.zoom) / 8;
    newCfHz += step;
    setCfHz(newCfHz);
}
function zoomedToCf() {
    setCfHz(spectrum.getZoomCfHz());
    spectrum.resetZoom();
}

function handleSpsChange(newSps) {
    sdrState.setSps(newSps*1e6);
    // force the sdr input bw to the same as the sps
    sdrState.setSdrBwHz(newSps*1e6);
    spectrum.setSps(newSps);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function handleSdrBwChange(newBwMHz) {
    sdrState.setSdrBwHz(newBwMHz*1e6);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function handleFftChange(newFft) {
    sdrState.setFftSize(newFft);
    // spec.setFftSize(num_floats); // don't do this here as spectrum has to know it changed
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function handleInputChange(newSource, newParams) {
    sdrState.setInputSource(newSource);
    sdrState.setInputSourceParams(newParams);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function handleDataFormatChange(newFormat) {
    sdrState.setDataFormat(newFormat);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}

function handleFpsChange(newFps) {
    if (websocket.readyState == 1) {
        sdrState.setFps(newFps);
        fps.value = newFps;
        let jsonString= JSON.stringify(fps);
        websocket.send(jsonString);
    }
    configTableFocusOut();
}

function handleGainChange(newGain) {
    sdrState.setGain(newGain);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
}
function handleGainModeChange(newMode) {
    sdrState.setGainMode(newMode);
    configTableFocusOut();
    sdrState.setSdrStateUpdated();
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
    spectrum.togglePaused();
    if(spectrum.paused) {
        if (!stop.value) {
            handleStopToggle();
            $("#stopBut").button('toggle'); // update the UI button state
        }
    }
}

function updateConfigTable(spec) {
    // TODO: use labels for current and new entries and stop deleting / recreating the whole table each time

    // if we have focus on a form then don't update the table
    if (formInFocus) {
        return;
    }

    // clear the config
    let num_rows = document.getElementById("configTable").rows.length - 1; // -1 for header
    for (let i=num_rows; i > 0; i--) {
        $("#configTable tr:eq("+i+")").remove();
    }

    let cf =  sdrState.getCentreFrequencyHz();
    let sps = sdrState.getSps();
    let source = sdrState.getInputSource();
    let sourceParams = sdrState.getInputSourceParams();
    let sources = sdrState.getInputSources();
    let dataFormats = sdrState.getDataFormats();
    let dataFormat = sdrState.getDataFormat();
    let gainModes = sdrState.getGainModes();
    let fftSize = sdrState.getFftSize();
    let gainMode = sdrState.getGainMode();
    let gain = sdrState.getGain();
    let fpsV = sdrState.getFps();
    let sdrBwHz = sdrState.getSdrBwHz();

    let new_row = '';

    /////////////
    // input
    ///////
    new_row = '<tr><td><b>Source</b></td>';
    new_row += '<td><div>'+source+'</div>';
    new_row += '<div title="'+sourceParams+'" class="CropLongTexts">'+sourceParams+'</div>'
    new_row += '<div>'+(sdrState.getSourceConnected()?'Connected':'Not Connected')+'</div></td>';
    if (sources.length > 0) {
        new_row += '<td>';
        new_row += '<form name="myForm"';
        new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_row += ' action="javascript:handleInputChange(inputSource.value, inputSourceParams.value)">';
        // the possible sources
        new_row += '<select id="inputSource" name="inputSource">';
        sources.forEach(function(src) {
            new_row += '<option value="'+src+'"'+((src==source)?"selected":"")+'>'+src+'</option>';
        });

        // the parameters for the source
        // TODO: when the source changes update the help, but it is already built here by then - so how?
        let help = source+' '+sourceParams+'\n'+sdrState.getInputSourceParamHelp(source);
        new_row += '<input data-toggle="tooltip" title="'+help+'" type="text" size="10"';
        new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_row += ' value="'+ sourceParams + '" id="inputSourceParams" name="inputSourceParams">';
        new_row += '<input type="submit" value="Change">';
        new_row += '</td>';
    }
    else {
        new_row += '<td>'+source+'</td>';
    }
    new_row += '</tr>';
    $('#configTable').append(new_row);

    /////////////
    // data format
    ///////
    new_row = '<tr><td><b>Format</b></td>';
    new_row += '<td>'+dataFormat+'</td>';
    if (dataFormats.length > 0) {
        new_row += '<td><form ';
        new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_row += ' action="javascript:handleDataFormatChange(dataFormatInput.value)">';
        new_row += '<select id="dataFormatInput" name="dataFormatInput" onchange="this.form.submit()">';
        dataFormats.forEach(function(dtype) {
            new_row += '<option value="'+dtype+'"'+((dtype==dataFormat)?"selected":"")+'>'+dtype+'</option>';
        });
        new_row += '</td>';
    }
    else {
        new_row += '<td>'+dataFormat+'</td>';
    }
    new_row += '</tr>';
    $('#configTable').append(new_row);

    /////////////
    // centre frequency
    ///////
    let cf_step = 0.000001; // 1Hz - annoyingly if we set it to sps/4 say then you can't go finer than that
    new_row = '<tr><td><b>Centre</b></td>';
    new_row += '<td>'+(cf/1e6).toFixed(6)+'&nbsp MHz</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += ' action="javascript:handleCfChange(centreFrequencyInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_row += '<input type="number" size="10" min="0" max="10000" ';
    new_row += ' step="';
    new_row += cf_step;
    new_row += '" value="';
    new_row += (cf/1e6).toFixed(6);
    new_row += '" id="centreFrequencyInput" name="centreFrequencyInput">';
    new_row += '<input type=submit id="submitbtnFreq">';
    new_row += '&nbsp MHz</form></td></tr>';
    $('#configTable').append(new_row);

    /////////////
    // sps
    ///////
    let sps_step = 0.000001; // 1Hz
    new_row = '<tr><td><b>SPS</b></td>';
    new_row += '<td>'+(sps/1e6).toFixed(6)+'&nbsp Msps</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += 'action="javascript:handleSpsChange(spsInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_row += '<input type="number" size="9" min="0" max="100" step="';
    new_row += sps_step;
    new_row += '" value="';
    new_row += (sps/1e6).toFixed(6);
    new_row += '" id="spsInput" name="spsInput">';
    new_row += "&nbsp Msps</form></td></tr>";
    $('#configTable').append(new_row);

    /////////////
    // sdr BW
    ///////
    let sdrbw_step = 0.01; // 10kHz
    new_row = '<tr><td><b>sdr Bw</b></td>';
    new_row += '<td>'+(sdrBwHz/1e6).toFixed(2)+'&nbsp MHz</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += 'action="javascript:handleSdrBwChange(sdrBwInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_row += '<input type="number" size="3" min="0" max="100" step="';
    new_row += sdrbw_step;
    new_row += '" value="';
    new_row += (sdrBwHz/1e6).toFixed(2);
    new_row += '" id="sdrBwInput" name="sdrBwInput">';
    new_row += "&nbsp MHz</form></td></tr>";
    $('#configTable').append(new_row);

    /////////////
    // fft
    ///////
    new_row = '<tr><td><b>FFT</b></td>';
    new_row += '<td>'+fftSize+'</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += 'action="javascript:handleFftChange(fftSizeInput.value)">';
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

    /////////////
    // gain mode
    ///////
    new_row = '<tr><td><b>Gmode</b></td>';
    new_row += '<td>'+gainMode+'</td>';
    if (gainModes.length > 0) {
        new_row += '<td><form';
        new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_row += ' action="javascript:handleGainModeChange(gainModeInput.value)">';
        new_row += '<select id="gainModeInput" name="gainModeInput" onchange="this.form.submit()">';
        gainModes.forEach(function(mode) {
            new_row += '<option value="'+mode+'"'+((mode==gainMode)?"selected":"")+'>'+mode+'</option>';
        });
        new_row += '</td>';
    }
    else {
        new_row += '<td>'+gainMode+'</td>';
    }
    new_row += '</tr>';
    $('#configTable').append(new_row);

    /////////////
    // gain
    ///////
    let gain_step = 0.1;
    new_row = '<tr><td><b>Gain</b></td>'
    new_row += '<td>'+gain+'&nbsp dB</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += ' action="javascript:handleGainChange(gainInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_row += '<input type="number" size="2" min="0" max="100" ';
    new_row += ' step="';
    new_row += gain_step;
    new_row += '" value="';
    new_row += sdrState.getGain();
    new_row += '" id="gainInput" name="gainInput">';
    new_row += '<input type=submit id="submitbtnGain">';
    new_row += '&nbsp dB</form></td></tr>';
    $('#configTable').append(new_row);

    /////////////
    // fps
    ///////
    new_row = '<tr><td><b>FPS</b></td>';
    new_row += '<td>Max:'+spec.getmaxFps()+', Actual:'+sdrState.getMeasuredFps()+'</td>';
    new_row += '<td><form ';
    new_row += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_row += 'action="javascript:handleFpsChange(fpsSizeInput.value)">';
    new_row += '<select id="fpsSizeInput" name="fpsSizeInput" onchange="this.form.submit()">';
    new_row += '<option value="1" '+((fpsV==1)?"selected":"")+'>1</option>';
    new_row += '<option value="5" '+((fpsV==5)?"selected":"")+'>5</option>';
    new_row += '<option value="10" '+((fpsV==10)?"selected":"")+'>10</option>';
    new_row += '<option value="20" '+((fpsV==20)?"selected":"")+'>20</option>';
    new_row += '<option value="40" '+((fpsV==40)?"selected":"")+'>40</option>';
    new_row += '<option value="80" '+((fpsV==80)?"selected":"")+'>80</option>';
    new_row += '<option value="160" '+((fpsV==160)?"selected":"")+'>160</option>';
    new_row += '<option value="320" '+((fpsV==320)?"selected":"")+'>320</option>';
    new_row += '<option value="640" '+((fpsV==640)?"selected":"")+'>640</option>';
    new_row += '<option value="10000" '+((fpsV==10000)?"selected":"")+'>10000</option>';
    new_row += '</select>';
    new_row += '</form></td></tr>';
    $('#configTable').append(new_row);

    /////////////
    // the rest, not configurable
    ///////
    new_row = '<tr><td><b>RBW</b></td>'
    new_row += '<td>'+spec.convertFrequencyForDisplay(sps / sdrState.getFftSize(),3)+'</td><td>&nbsp</td></tr>';
    $('#configTable').append(new_row);
    new_row = '<tr><td><b>Avg</b></td><td>'+spec.averaging+'</td><td>&nbsp</td></tr>';
    $('#configTable').append(new_row);
    new_row = '<tr><td><b>Zoom</b></td><td>'+spec.zoom+'</td><td>&nbsp</td></tr>';
    $('#configTable').append(new_row);
    let zoomBw = sps/spec.zoom;
    new_row = '<tr><td><b>Span</b></td><td>'+spec.convertFrequencyForDisplay(zoomBw,3)+'</td><td>&nbsp</td></tr>';
    $('#configTable').append(new_row);
}

function configTableFocusIn(){
    formInFocus = true;
}

function configTableFocusOut(){
    formInFocus = false;
}

function connectWebSocket(spec) {
    let server_hostname = window.location.hostname;
    let server_port = parseInt(window.location.port) + 1;
    let server = "ws://"+server_hostname+":"+server_port+"/";
    console.log("WebSocket connecting to", server);
    websocket = new WebSocket(server);

    websocket.onopen = function(event) {
        console.log("WebSocket connected to", server);
        // Update the status led
        $("#connection_state").empty();
        let new_element = '<img src="./icons/led-yellow.png" alt="connected" title="Connected" >';
        $('#connection_state').append(new_element);

        // sending a control message to the server will cause it to give us its current configuration as json
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
            if (event.data instanceof Blob) {
                handleBlob(event.data);
            } else {
                handleJsonControl(event.data);
            }
        }
        // have we something to send back to the server
        if (sdrState.getResetSdrStateUpdated()) {
            let jsonString= JSON.stringify(sdrState);
            // console.log(jsonString);
            websocket.send(jsonString);
        }

        // send acks back as required
        if (sdrState.getLastDataTime() >= sdrState.getNextAckTime()) {
            ack.value = sdrState.getLastDataTime();
            let jsonString= JSON.stringify(ack);
            sdrState.setNextAckTime(sdrState.getLastDataTime()+1);  // every second
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
    } else {
        try{
            let test_blob_arrayBuffer = test_blob.arrayBuffer();
            try {
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
    let sp='<canvas id="spectrumanalyser" height="600px" width="1024px" style="cursor: crosshair;"></canvas>';
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
    rhcol += '<th scope="col">Set</th>';
    rhcol += '<th scope="col">New</th>';
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
    rhcol += '<th scope="col">cf</th>';
    rhcol += '<th scope="col">MHz</th>';
    rhcol += '<th scope="col">dB</th>';
    rhcol += '<th scope="col">time</th>';
    rhcol += '<th scope="col">Deltas: Hz, dB, sec</th>';
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

    // remove default canvas context menu if need to handle right mouse click
    // then you can add an event listener for contextmenu as the right mouse click
    // $('body').on('contextmenu', '#spectrumanalyser', function(e){ return false; });

    // stream button
    let main_buttons = '<h4>Stream</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="stopBut" title="stop front end sending data" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Stop</button>';
    main_buttons += '<button type="button" id="cfDwnBut" title="decrease centre frequency by 1/8th displayed BW" class="specbuttons btn btn-outline-dark mx-1 my-1">cf-</button>';
    main_buttons += '<button type="button" id="cfUpBut" title="increase centre frequency by 1/8th displayed BW" class="specbuttons btn btn-outline-dark mx-1 my-1">cf+</button>';
    main_buttons += '<button type="button" id="zoomToCfBut" title="set the displayed centre frequency as the centre frequency " class="specbuttons btn btn-outline-dark mx-1 my-1">z->cf</button>';
    main_buttons += '</div>'

     // main buttons
    main_buttons += '<h4>Trace 0</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="pauseBut" title="pause and allow scroll throuh previous spectrums" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Hold</button>';
    main_buttons += '<button type="button" id="maxHoldBut" data-toggle="button" title="record max dB level" class="specbuttons btn btn-outline-dark mx-1 my-1">Peak</button>';
    main_buttons += '<button type="button" id="avgDwnBut" title="decrease the number of averages" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg-</button>';
    main_buttons += '<button type="button" id="avgUpBut" title="increase number of averages" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg+</button>';
    main_buttons += '<button type="button" id="avgOffBut" title="turn averaging off" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg0</button>';
    main_buttons += '<button type="button" id="diffBut" title="difference to trace1" data-toggle="button" class="specbuttons btn btn-outline-dark mx-1 my-1">Diff</button>';
    main_buttons += '</div>'

     // main buttons
    main_buttons += '<h4>Trace 1</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="maxToTrc1But" title="peak to trace1" class="specbuttons btn btn-outline-dark mx-1 my-1">peak-></button>';
    main_buttons += '<button type="button" id="avgToTrc1But" title="average to trace1" class="specbuttons btn btn-outline-dark mx-1 my-1">Avg-></button>';
    main_buttons += '<button type="button" id="curToTrc1But" title="current to trace1" class="specbuttons btn btn-outline-dark mx-1 my-1">Curr-></button>';
    main_buttons += '<button type="button" id="clrToTrc1But" title="clear trace1" class="specbuttons btn btn-outline-dark mx-1 my-1">clr</button>';
    main_buttons += '</div>'

    main_buttons += '<h4>Magnitude</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="refUpBut" title="decrease the reference dB" class="specbuttons btn btn-outline-dark mx-1 my-1">Ref-</button>';
    main_buttons += '<button type="button" id="refDwnBut" title="increase the reference dB" class="specbuttons btn btn-outline-dark mx-1 my-1">Ref+</button>';
    main_buttons += '<button type="button" id="rangeDwnBut" title="decrease the dB range" class="specbuttons btn btn-outline-dark mx-1 my-1">Rng-</button>';
    main_buttons += '<button type="button" id="rangeUpBut" title="increase the dB range" class="specbuttons btn btn-outline-dark mx-1 my-1">Rng+</button>';
    main_buttons += '<button type="button" id="autoRangeBut" title="autorange on dB acros full spectrum" class="specbuttons btn btn-outline-dark mx-1 my-1">Auto</button>';
    main_buttons += '</div>';

    main_buttons += '<h4>Span</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="zoomInBut" title="decrease span" class="specbuttons btn btn-outline-dark mx-1 my-1">Spn-</button>';
    main_buttons += '<button type="button" id="zoomOutBut" title="increase span" class="specbuttons btn btn-outline-dark mx-1 my-1">Spn+</button>';
    main_buttons += '<button type="button" id="unZoomBut" title="reset span" class="specbuttons btn btn-outline-dark mx-1 my-1">Full</button>';
    main_buttons += '</div>';

    main_buttons += '<h4>Visualisation</h4>';
    main_buttons += '<div">';
    main_buttons += '<button type="button" id="SpecPcUpBut" title="decrease spectrum size" class="specbuttons btn btn-outline-dark mx-1 my-1">Spc-</button>';
    main_buttons += '<button type="button" id="SpecPcDownBut" title="increase spectrum size" class="specbuttons btn btn-outline-dark mx-1 my-1">Spc+</button>';
    main_buttons += '<button type="button" id="ColourMapBut" title="cycle through colour maps" class="specbuttons btn btn-outline-dark mx-1 my-1">Map</button>';
    main_buttons += '<button type="button" id="ColourGradientBut" title="toggle gradient fill on spectrum" class="specbuttons btn btn-outline-dark mx-1 my-1">Grad</button>';
    main_buttons += '</div>';

    // btn-block
    $('#buttons').append(main_buttons);

    let marker_buttons = '<div">';
    marker_buttons = '<button type="button" id="hideMarkersBut" data-toggle="button" title="hide all markers" class="specbuttons btn btn-outline-dark mx-1 my-1">Hide</button>';
    marker_buttons += '<button type="button" id="clearMarkersBut" title="clear all markers" class="specbuttons btn btn-outline-dark mx-1 my-1">Clr&nbsp</button>';
    marker_buttons += '<button type="button" id="searchPeakBut"title="find and record peak in spectrogram data, may be zoomed" class="specbuttons btn btn-outline-dark mx-1 my-1">Peak</button>';
    //marker_buttons += '<button type="button" id="searchNextPeakBut" class="specbuttons btn btn-outline-dark mx-1 my-1">Next</button>';
    marker_buttons += '<button type="button" id="peakTrackBut" data-toggle="button" title="follow the peak" class="specbuttons btn btn-outline-dark mx-1 my-1">Trck</button>';
    marker_buttons += '</div>';
    $('#marker-buttons').append(marker_buttons);

    // events
    $('#configButton').click(function() {showConfig();});
    $('#controlButton').click(function() {showControls();});
    $('#markerButton').click(function() {showMarkers();});

    $('#stopBut').click(function() {handleStopToggle();});
    $('#cfDwnBut').click(function() {decrementCf();});
    $('#cfUpBut').click(function() {incrementCf();});
    $('#zoomToCfBut').click(function() {zoomedToCf();});

    $('#pauseBut').click(function() {handlePauseToggle();});
    $('#maxHoldBut').click(function() {spectrum.toggleMaxHold();});
    $('#avgUpBut').click(function() {spectrum.incrementAveraging();});
    $('#avgDwnBut').click(function() {spectrum.decrementAveraging();});
    $('#avgOffBut').click(function() {spectrum.setAveraging(0);});
    $('#diffBut').click(function() {spectrum.setDiff();});

    $('#maxToTrc1But').click(function() {spectrum.pkToTrace1();});
    $('#avgToTrc1But').click(function() {spectrum.avgToTrace1();});
    $('#curToTrc1But').click(function() {spectrum.curToTrace1();});
    $('#clrToTrc1But').click(function() {spectrum.clrTrace1();});

    $('#refDwnBut').click(function() {spectrum.refDown();});
    $('#refUpBut').click(function() {spectrum.refUp();});
    $('#rangeDwnBut').click(function() {spectrum.rangeDecrease();});
    $('#rangeUpBut').click(function() {spectrum.rangeIncrease();});
    $('#autoRangeBut').click(function() {spectrum.autoRange();});

    $('#zoomInBut').click(function() {spectrum.zoomIn();});
    $('#zoomOutBut').click(function() {spectrum.zoomOut();});
    $('#unZoomBut').click(function() {spectrum.resetZoom();});

    $('#SpecPcUpBut').click(function() {spectrum.decrementSpectrumPercent();});
    $('#SpecPcDownBut').click(function() {spectrum.incrementSpectrumPercent();});
    $('#ColourMapBut').click(function() {spectrum.toggleColour();});
    $('#ColourGradientBut').click(function() {spectrum.toggleGradient();});

    $('#markerRadio_off').click(function() {spectrum.liveMarkerOff();});
    $('#markerRadio_on').click(function() {spectrum.liveMarkerOn();});
    $('#clearMarkersBut').click(function() {spectrum.clearMarkers();});
    $('#hideMarkersBut').click(function() {spectrum.hideMarkers();});
    $('#searchPeakBut').click(function() {spectrum.findPeak();});
    //$('#searchNextPeakBut').click(function() {spectrum.findNextPeak();});
    $('#peakTrackBut').click(function() {spectrum.toggleTrackPeak();});

    updateConfigTable(spectrum);

    // Connect to websocket
    connectWebSocket(spectrum);
}

window.onload = Main;
