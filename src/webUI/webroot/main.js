'use strict';

// GLOBALS !!!
var data_active = false; // true when we are connected and receiving data
var spectrum = null;     // don't like this global but can't get onclick in table of markers to work
var sdrState = null;     // holds basics about the front end sdr
var snapState = null;    // holds basics about snapshots
var websocket = null;
var updateTimer = null;  // for when we are not streaming we still need to update the display
var configFormInFocus = false;
var snapFormInFocus = false;

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
    "sample_types": ["8t", "8o", "16tbe", "16tle", "32fle"],
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
        // console.log("control json:", control)

        if (control.type == "snap") {
            let updateTable = snapState.setSnapFromJason(control);
            if (updateTable) {
                updateSnapTable(spectrum);
            }
        }
        else if (control.type == "control") {
            // is there an error at the server we need to communicate to the user
            if (control.error != "") {
                console.log(control.error);
                alert(control.error);
            }
            let updateCfgTable = sdrState.setConfigFromJason(control);
            if (updateCfgTable) {
                spectrum.updateAxes();
                updateConfigTable(spectrum);
            }
        }
        else {
            console.log("Unknown control json:", control)
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
    sdrState.setCentreFrequencyHz(newCfHz);
    spectrum.setCentreFreqHz(newCfHz);
    sdrState.setSdrStateUpdated();
}

function decrementCf() {
    let newCfHz = sdrState.getCentreFrequencyHz();
    let step = (sdrState.getSps() / spectrum.zoom) / 4;
    newCfHz -= step;
    setCfHz(newCfHz);
}

function incrementCf() {
    let newCfHz = sdrState.getCentreFrequencyHz();
    let step = (sdrState.getSps() / spectrum.zoom) / 4;
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

function updateSnapTable() {
    updateSnapTableCurrent();
    updateSnapTableNew();
    if(snapState.directoryListChanged) {
        updateSnapFileList();
    }
}

function updateSnapFileList() {
    $("#snapFileTable tbody tr").remove(); // delete all the current rows
    let row_count = 0;
    for (const file of snapState.getDirectoryList()) {
        let new_row='<tr>';
        let fname = '<div title="'+file[0]+'" class="CropLongTexts180">'+file[0]+'</div>';
        new_row += '<td>'+fname+'</td>';
        // size with a hover over of a png showing a spectrum image
        // new_row += '<td><span>'+file[1]+'</span><img src="./thumbnails/'+file[0]+'.png"></td>';
        new_row += '<td><span>'+file[1]+'</span><img src="./thumbnails/'+file[0]+'.png"></td>';

        let id = row_count;
        new_row += '<td><input type="image" title="play" id="play_'+id+'" src="./icons/play.png"></td>';
        new_row += '<td><input type="image" title="delete" id="delete_'+id+'" src="./icons/bin.png"></td>';
        new_row += "</tr>";
        $('#snapFileTable').append(new_row);

        // handle icon buttons for play and delete
        $('#play_'+id).click(function() {
            // force input change, command goes by sdrState
            handleInputChange("file", snapState.getSnapDirectory()+"/"+file[0]);
        } );
        $('#delete_'+id).click(function() {
            // command goes by snapState
            snapState.setDeleteFilename(file[0]);
            snapState.setSnapStateUpdated();
        } );
        row_count += 1;
    }
    snapState.directoryListChanged = false;
}

function updateSnapTableCurrent() {
    $('#currentSnapState').empty().append(snapState.getSnapState());
    // shorten long names
    let name = '<div title="'+snapState.getBaseName()+'" class="CropLongTexts100">'+snapState.getBaseName()+'</div>'
    $('#currentSnapBaseName').empty().append(name);
    $('#currentSnapTriggerType').empty().append(snapState.getTriggerType());
    $('#currentSnapTriggerState').empty().append(snapState.getTriggerState());
    if (snapState.getTriggerState() == "triggered") {
        $('#currentSnapTriggerState').addClass('redTrigger');
        $('#currentSnapTriggerState').removeClass('greenTrigger');
    } else {
        $('#currentSnapTriggerState').addClass('greenTrigger');
        $('#currentSnapTriggerState').removeClass('redTrigger');
    }

    $('#currentSnapPreTrigger').empty().append(snapState.getPreTriggerMilliSec());
    $('#currentSnapPostTrigger').empty().append(snapState.getPostTriggerMilliSec());

    $('#currentSnapSize').empty().append(snapState.getCurrentSize().toFixed(2)+" MBytes");
}

function updateSnapTableNew() {
    // if we have focus on a form then don't update the table
    if (snapFormInFocus) {
        return;
    }
    let new_html=""

    new_html = '<form ';
    new_html += ' onfocusin="snapTableFocusIn()" onfocusout="snapTableFocusOut()" ';
    new_html += 'action="javascript:handleSnapBaseNameChange(snapBaseName.value)">';
    let help = snapState.getBaseName();
    // shorten long names
    new_html += '<input data-toggle="tooltip" title="'+help+'" type="text" size="10" value="';
    new_html += snapState.getBaseName();
    new_html += '" id="snapBaseName" name="snapBaseName">';
    new_html += '</form>';
    $('#newSnapBaseName').empty().append(new_html);

    let triggerTypes = snapState.getTriggers();
    let triggerType = snapState.getTriggerType();
    if (triggerTypes.length > 0) {
        new_html = '<form';
        new_html += ' onfocusin="snapTableFocusIn()" onfocusout="snapTableFocusOut()" ';
        new_html += ' action="javascript:handleSnapTriggerModeChange(snapTriggerMode.value)">';
        new_html += '<select id="snapTriggerMode" name="snapTriggerMode" onchange="this.form.submit()">';
        triggerTypes.forEach(function(type) {
            new_html += '<option value="'+type+'"'+((type==triggerType)?"selected":"")+'>'+type+'</option>';
        });
        new_html += '</select></form>';
    }
    else {
        new_html = triggerType;
    }
    $('#newSnapTriggerType').empty().append(new_html);

    new_html = '<form ';
    new_html += ' onfocusin="snapTableFocusIn()" onfocusout="snapTableFocusOut()" ';
    new_html += 'action="javascript:handleSnapPreTriggerChange(snapPreTrigMilliSec.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="5" min="0" value="';
    new_html += snapState.getPreTriggerMilliSec();
    new_html += '" id="snapPreTrigMilliSec" name="snapPreTrigMilliSec">';
    new_html += '&nbsp msec</form>';
    $('#newSnapPreTrigger').empty().append(new_html);

    new_html = '<form ';
    new_html += ' onfocusin="snapTableFocusIn()" onfocusout="snapTableFocusOut()" ';
    new_html += 'action="javascript:handleSnapPostTriggerChange(snapPostTrigMilliSec.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="6" min="0" value="';
    new_html += snapState.getPostTriggerMilliSec();
    new_html += '" id="snapPostTrigMilliSec" name="snapPostTrigMilliSec">';
    new_html += '&nbsp msec</form>';
    $('#newSnapPostTrigger').empty().append(new_html);

    $('#newSnapSize').empty().append(snapState.getExpectedSize().toFixed(2)+" MBytes");
}

function snapTableFocusIn(){
    snapFormInFocus = true;
}
function snapTableFocusOut(){
    snapFormInFocus = false;
}

function updateConfigTable(spec) {
    updateConfigTableCurrent(spec);
    updateConfigTableNew(spec);
}

function updateConfigTableCurrent(spec) {
    let src = '<div>'+sdrState.getInputSource()+'</div>';
    src += '<div title="'+sdrState.getInputSourceParams()+'" class="CropLongTexts100">'+sdrState.getInputSourceParams()+'</div>'
    src += '<div>'+(sdrState.getSourceConnected()?'Connected':'Not Connected')+'</div>';
    $('#currentSource').empty().append(src);

    $('#currentFormat').empty().append(sdrState.getDataFormat());
    $('#currentCentre').empty().append((sdrState.getCentreFrequencyHz()/1e6).toFixed(6)+' MHz');
    let sps = sdrState.getSps();
    $('#currentSps').empty().append((sps/1e6).toFixed(6)+' Msps');
    $('#currentSdrBw').empty().append((sdrState.getSdrBwHz()/1e6).toFixed(2)+' MHz');
    $('#currentFft').empty().append(sdrState.getFftSize());
    $('#currentGmode').empty().append(sdrState.getGainMode());
    $('#currentGain').empty().append(sdrState.getGain()+' dB');
    $('#currentFPS').empty().append(sdrState.getMeasuredFps());
    $('#currentRBW').empty().append(spec.convertFrequencyForDisplay(sps / sdrState.getFftSize(),3));
    $('#currentAvg').empty().append(spec.averaging);
    $('#currentZoom').empty().append(spec.zoom);
    let zoomBw = sps/spec.zoom;
    $('#currentSpan').empty().append(spec.convertFrequencyForDisplay(zoomBw,3));
}

function updateConfigTableNew(spec) {
    // this rewrites all the values in the configuration table 'new' column

    // if we have focus on a form then don't update the table
    if (configFormInFocus) {
        return;
    }
    let new_html=""

    /////////////
    // input
    ///////
    let source = sdrState.getInputSource();
    let sourceParams = sdrState.getInputSourceParams();
    let sources = sdrState.getInputSources();
    if (sources.length > 0) {
        new_html = '<form ';
        new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_html += ' action="javascript:handleInputChange(inputSource2.value, inputSourceParams.value)">';
        // the possible sources
        new_html += '<select id="inputSource2" name="inputSource2">';
        sources.forEach(function(src) {
            new_html += '<option value="'+src+'"'+((src==source)?"selected":"")+'>'+src+'</option>';
        });

        // the parameters for the source
        let help = source+' '+sourceParams+'\n'+sdrState.getInputSourceParamHelp(source);
        new_html += '<input data-toggle="tooltip" title="'+help+'" type="text" size="10"';
        new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_html += ' value="'+ sourceParams + '" id="inputSourceParams" name="inputSourceParams">';
        new_html += '<input type="submit" value="Change">';
        new_html += '</form>';
    }
    else {
        new_html = source;
    }
    $('#newSource').empty().append(new_html);

    /////////////
    // data format
    ///////
    let dataFormats = sdrState.getDataFormats();
    if (dataFormats.length > 0) {
        new_html = '<form ';
        new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_html += ' action="javascript:handleDataFormatChange(dataFormatInput.value)">';
        new_html += '<select id="dataFormatInput" name="dataFormatInput" onchange="this.form.submit()">';
        dataFormats.forEach(function(dtype) {
            new_html += '<option value="'+dtype+'"'+((dtype==sdrState.getDataFormat())?"selected":"")+'>'+dtype+'</option>';
        });
        new_html += '</select></form>';
    }
    else {
        new_html = sdrState.getDataFormat();
    }
    $('#newFormat').empty().append(new_html);

    /////////////
    // centre frequency
    ///////
    let cf_step = 0.000001; // 1Hz - annoyingly if we set it to sps/4 say then you can't go finer than that
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += ' action="javascript:handleCfChange(centreFrequencyInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="10" min="0" max="10000" ';
    new_html += ' step="';
    new_html += cf_step;
    new_html += '" value="';
    new_html += (sdrState.getCentreFrequencyHz()/1e6).toFixed(6);
    new_html += '" id="centreFrequencyInput" name="centreFrequencyInput">';
    new_html += '<input type=submit id="submitbtnFreq">';
    new_html += '&nbsp MHz</form>';
    $('#newCentre').empty().append(new_html);

    /////////////
    // sps
    ///////
    let sps = sdrState.getSps();
    let sps_step = 0.000001; // 1Hz
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += 'action="javascript:handleSpsChange(spsInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="9" min="0" max="100" step="';
    new_html += sps_step;
    new_html += '" value="';
    new_html += (sps/1e6).toFixed(6);
    new_html += '" id="spsInput" name="spsInput">';
    new_html += "&nbsp Msps</form>";
    $('#newSps').empty().append(new_html);

    /////////////
    // sdr BW
    ///////
    let sdrBwHz = sdrState.getSdrBwHz();
    let sdrbw_step = 0.01; // 10kHz
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += 'action="javascript:handleSdrBwChange(sdrBwInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="3" min="0" max="100" step="';
    new_html += sdrbw_step;
    new_html += '" value="';
    new_html += (sdrBwHz/1e6).toFixed(2);
    new_html += '" id="sdrBwInput" name="sdrBwInput">';
    new_html += "&nbsp MHz</form>";
    $('#newSdrBw').empty().append(new_html);

    /////////////
    // fft
    ///////
    let fftSize = sdrState.getFftSize();
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += 'action="javascript:handleFftChange(fftSizeInput.value)">';
    new_html += '<select id="fftSizeInput" name="fftSizeInput" onchange="this.form.submit()">';
    new_html += '<option value="16384" '+((fftSize==16384)?"selected":"")+'>16384</option>';
    new_html += '<option value="8192" '+((fftSize==8192)?"selected":"")+'>8192</option>';
    new_html += '<option value="4096" '+((fftSize==4096)?"selected":"")+'>4096</option>';
    new_html += '<option value="2048" '+((fftSize==2048)?"selected":"")+'>2048</option>';
    new_html += '<option value="1024" '+((fftSize==1024)?"selected":"")+'>1024</option>';
    new_html += '<option value="512" '+((fftSize==512)?"selected":"")+'>512</option>';
    new_html += '<option value="256" '+((fftSize==256)?"selected":"")+'>256</option>';
    new_html += '</select></form>';
    $('#newFft').empty().append(new_html);

    /////////////
    // gain mode
    ///////
    let gainModes = sdrState.getGainModes();
    let gainMode = sdrState.getGainMode();
    if (gainModes.length > 0) {
        new_html = '<form';
        new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
        new_html += ' action="javascript:handleGainModeChange(gainModeInput.value)">';
        new_html += '<select id="gainModeInput" name="gainModeInput" onchange="this.form.submit()">';
        gainModes.forEach(function(mode) {
            new_html += '<option value="'+mode+'"'+((mode==gainMode)?"selected":"")+'>'+mode+'</option>';
        });
        new_html += '</select></form>';
    }
    else {
        new_html = gainMode;
    }
    $('#newGmode').empty().append(new_html);

    /////////////
    // gain
    ///////
    let gain_step = 0.1;
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += ' action="javascript:handleGainChange(gainInput.value)">';
    // as we remove the number inc/dec arrows in css the size parameter does work
    new_html += '<input type="number" size="2" min="0" max="100" ';
    new_html += ' step="';
    new_html += gain_step;
    new_html += '" value="';
    new_html += sdrState.getGain();
    new_html += '" id="gainInput" name="gainInput">';
    new_html += '<input type=submit id="submitbtnGain">';
    new_html += '&nbsp dB</form>';
    $('#newGain').empty().append(new_html);

    /////////////
    // fps
    ///////
    let fpsV = sdrState.getFps();
    new_html = '<form ';
    new_html += ' onfocusin="configTableFocusIn()" onfocusout="configTableFocusOut()" ';
    new_html += 'action="javascript:handleFpsChange(fpsSizeInput.value)">';
    new_html += '<select id="fpsSizeInput" name="fpsSizeInput" onchange="this.form.submit()">';
    new_html += '<option value="1" '+((fpsV==1)?"selected":"")+'>1</option>';
    new_html += '<option value="5" '+((fpsV==5)?"selected":"")+'>5</option>';
    new_html += '<option value="10" '+((fpsV==10)?"selected":"")+'>10</option>';
    new_html += '<option value="20" '+((fpsV==20)?"selected":"")+'>20</option>';
    new_html += '<option value="40" '+((fpsV==40)?"selected":"")+'>40</option>';
    new_html += '<option value="80" '+((fpsV==80)?"selected":"")+'>80</option>';
    new_html += '<option value="160" '+((fpsV==160)?"selected":"")+'>160</option>';
    new_html += '<option value="320" '+((fpsV==320)?"selected":"")+'>320</option>';
    new_html += '<option value="640" '+((fpsV==640)?"selected":"")+'>640</option>';
    new_html += '<option value="10000" '+((fpsV==10000)?"selected":"")+'>10000</option>';
    new_html += '</select></form>Max '+spec.getmaxFps();
    $('#newFPS').empty().append(new_html);
}

function configTableFocusIn(){
    configFormInFocus = true;
}
function configTableFocusOut(){
    configFormInFocus = false;
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

        // control back to server
        if (sdrState.getResetSdrStateUpdated()) {
            let jsonString= JSON.stringify(sdrState);
            // console.log(jsonString);
            websocket.send(jsonString);
        }

        // snapshot back to server
        if (snapState.getResetSnapStateUpdated()) {
            let jsonString= JSON.stringify(snapState);
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
        ok += ", Missing canvas support";
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
                ok += ", Missing blob DataView support";
            }
        }catch (err){
            ok += ", Missing blob arrayBuffer support";
        }
    }
    if (!window.jQuery) {
        ok += ", Missing jQuery";
    }
    let bootstrap = (typeof $().emulateTransitionEnd == 'function');
    if (!bootstrap) {
        ok += ", Missing Bootstrap3";
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

    // add the spectrum to the page, set the mouse pointer graphic
    let sp='<canvas id="spectrumanalyser" height="600px" width="1024px" style="cursor: crosshair;"></canvas>';
    $('#specCanvas').append(sp);

    // Create spectrum object on canvas with ID "spectrumanalyser"
    spectrum = new Spectrum(
        "spectrumanalyser", {
            spectrumPercent: 50
    });

    // create sdrState object
    sdrState = new sdrState();

    // create snapState object
    snapState = new snapState();

    let canvas = document.getElementById('spectrumanalyser');

    // key presses
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

    // button events
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
    $('#peakTrackBut').click(function() {spectrum.toggleTrackPeak();});

    $('#snapTriggerBut').click(function() {handleSnapTrigger();});

    updateConfigTable(spectrum);

    // Connect to websocket
    connectWebSocket(spectrum);

//    // checking if config has changed in the UI to send to the server
//    setInterval(function() {
//        if (sdrState.getResetSdrStateUpdated()) {
//            let jsonString= JSON.stringify(sdrState);
//            websocket.send(jsonString);
//            console.log(jsonString);
//        }
//    }, 3000);
//
//    // checking if snap has changed in the UI to send to the server
//    setInterval(function() {
//        if (snapState.getResetSnapStateUpdated()) {
//            let jsonString= JSON.stringify(snapState);
//            if (websocket) {
//                websocket.send(jsonString);
//            }
//        }
//    }, 100);

}

window.onload = Main;
