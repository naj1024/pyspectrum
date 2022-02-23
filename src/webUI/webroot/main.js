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

function syncCurrent() {
    // currnet values not covered by fast update method
    // TODO: maybe this should be one big json document instead of lots of small fetch'es

    // from UI interface
    $('#currentAvg').empty().append(spectrum.averaging);
    $('#currentZoom').empty().append(spectrum.zoom);
    let zoomBw = sdrState.getSps()/spectrum.zoom;
    $('#currentSpan').empty().append(spectrum.convertFrequencyForDisplay(zoomBw,3));

    let oldSourceType = sdrState.getInputSource();
    let oldSourceParams = sdrState.getInputSourceParams();

    // from api
    fetch('./input/source').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        let src = '<div>'+sdrState.getInputSource()+'</div>';
        src += '<div title="'+sdrState.getInputSourceParamHelp()+'" class="CropLongTexts100">'+sdrState.getInputSourceParams()+'</div>'
        src += '<div>'+(sdrState.getSourceConnected()?'Connected':'Not Connected')+'</div>';
        $('#currentSource').empty().append(src);
    }).catch(function (error) {
    });

    // flagged that source changed so remove any green highlights from file table
    updateSnapFileList();

    fetch('./tuning/frequency').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentCentre').empty().append((sdrState.getFrequencyHz()/1e6).toFixed(6)+' MHz');
        $('#currentCfOffset').empty().append((sdrState.getFrequencyOffsetHz()/1e6).toFixed(6)+' MHz');
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserFrequency').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentSdrCentre').empty().append((sdrState.getSdrFrequencyHz()/1e6).toFixed(6)+' MHz');
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserFormat').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentFormat').empty().append(sdrState.getDataFormat());
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserSampleRate').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentSps').empty().append((sdrState.getSps()/1e6).toFixed(6)+' Msps');
        $('#currentRBW').empty().append(spectrum.convertFrequencyForDisplay(sdrState.getSps() / sdrState.getFftSize(),2));
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserBandwidth').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentSdrBw').empty().append((sdrState.getSdrBwHz()/1e6).toFixed(2)+' MHz');
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserPartsPerMillion').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentPpm',).empty().append((sdrState.getPpmError()).toFixed(3));
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserGainType').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentGmode').empty().append(sdrState.getGainMode());
    }).catch(function (error) {
    });
    
    fetch('./spectrum/fftSize').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentFft').empty().append(sdrState.getFftSize());
        $('#currentRBW').empty().append(spectrum.convertFrequencyForDisplay(sdrState.getSps() / sdrState.getFftSize(),2));
    }).catch(function (error) {
    });
    
    fetch('./spectrum/fftWindow').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setConfigFromJason(obj);
        $('#currentFftWindow').empty().append(sdrState.getFftWindow());
    }).catch(function (error) {
    });

    fetch('./snapshot/snapTriggerSource').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setSnapFromJason(obj);
        $('#currentSnapTriggerType').empty().append(snapState.getTriggerType());
    }).catch(function (error) {
    });

    fetch('./snapshot/snapName').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setSnapFromJason(obj);
        let name = '<div title="'+snapState.getBaseName()+'" class="CropLongTexts100">'+snapState.getBaseName()+'</div>'
        $('#currentSnapBaseName').empty().append(name);
    }).catch(function (error) {
    });

    fetch('./snapshot/snapFormat').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setSnapFromJason(obj);
        $('#currentFileFormat').empty().append(snapState.getFileFormat());
    }).catch(function (error) {
    });

    fetch('./snapshot/snapPreTrigger').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setSnapFromJason(obj);
        $('#currentSnapPreTrigger').empty().append(snapState.getPreTriggerMilliSec().toFixed(0) + ' msec');
    }).catch(function (error) {
    });

    fetch('./snapshot/snapPostTrigger').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setSnapFromJason(obj);
        $('#currentSnapPostTrigger').empty().append(snapState.getPostTriggerMilliSec().toFixed(0) + ' msec');
    }).catch(function (error) {
    });

}

function syncNew() {
    // this rewrites all the values in the configuration table 'new' column

    // if we have focus on a form then don't update the table
    if (configFormInFocus) {
        return;
    }

    // get all the main stuff
    let initUris = ['./input/sources', './digitiser/digitiserFormats', './spectrum/fftSizes', 
                './spectrum/fftWindows', './digitiser/digitiserGainTypes', './control/presetFps',
                './digitiser/digitiserGain', './digitiser/digitiserSampleRate', './tuning/frequency',
                './digitiser/digitiserBandwidth', './digitiser/digitiserPartsPerMillion'];
    for (let i = 0; i < initUris.length; i++) {
        fetch(initUris[i]).then(function (response) {
            return response.json();
        }).then(function (obj) {
            // update the configuration and the html when we get a reply
            sdrState.setConfigFromJason(obj)
            showNew(obj);
        }).catch(function (error) {
        });
    }

    // snap stuff
    initUris = ['./snapshot/snapTriggerSources',
                './snapshot/snapFormats', './snapshot/snaps'];
    for (let i = 0; i < initUris.length; i++) {
        fetch(initUris[i]).then(function (response) {
            return response.json();
        }).then(function (obj) {
            // update the configuration and the html when we get a reply
            snapState.setSnapFromJason(obj);
            showNewSnap(obj);
        }).catch(function (error) {
        });
    }
}

function showNew(jsonConfig) {
    // show the values in the new column, may require rebuilding drop down lists
    // check for what we have in jsonConfig and update html appropriately
    let new_html=""

    /////////////
    // input
    ///////
    if( (jsonConfig.sources != undefined) || (jsonConfig.source != undefined)) {
        let source = sdrState.getInputSource();
        let sourceParams = sdrState.getInputSourceParams();
        let sources = sdrState.getInputSources();
        if (sources.length > 0) {
            new_html = '<form ';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += ' action="javascript:handleInputChange(inputSource2.value, inputSourceParams.value)">';
            // the possible sources
            new_html += '<select id="inputSource2" name="inputSource2">';
            sources.forEach(function(src) {
                new_html += '<option value="'+src+'"'+((src==source)?"selected":"")+'>'+src+'</option>';
            });

            // the parameters for the source
            let help = source+' '+sourceParams+'\n'+sdrState.getInputSourceParamHelp(source);
            new_html += '<input data-toggle="tooltip" title="'+help+'" type="text" size="10"';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += ' value="'+ sourceParams + '" id="inputSourceParams" name="inputSourceParams">';
            new_html += '<input type="submit" value="Change">';
            new_html += '</form>';
            $('#newSource').empty().append(new_html);
        }
    }

    /////////////
    // data format
    ///////
    if( (jsonConfig.digitiserFormats != undefined) || (jsonConfig.digitiserFormat != undefined)) {
        let dataFormats = sdrState.getDataFormats();
        if (dataFormats.length > 0) {
            new_html = '<form ';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += ' action="javascript:handleDataFormatChange(dataFormatInput.value)">';
            new_html += '<select id="dataFormatInput" name="dataFormatInput" onchange="this.form.submit()">';
            dataFormats.forEach(function(dtype) {
                new_html += '<option value="'+dtype+'"'+((dtype==sdrState.getDataFormat())?"selected":"")+'>'+dtype+'</option>';
            });
            new_html += '</select></form>';
            $('#newFormat').empty().append(new_html);
        }
    }

    /////////////
    // centre frequency and offset
    ///////
    if (jsonConfig.frequency != undefined) {
        let cf_step = 0.000001; // 1Hz - annoyingly if we set it to sps/4 say then you can't go finer than that
        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
        new_html += ' action="javascript:handleCfChangeMHz(centreFrequencyInput.value)">';
        // as we remove the number inc/dec arrows in css the size parameter does work
        new_html += '<input type="number" size="12" min="0" max="40000" ';
        new_html += ' step="';
        new_html += cf_step;
        new_html += '" value="';
        new_html += (sdrState.getFrequencyHz()/1e6).toFixed(6);
        new_html += '" id="centreFrequencyInput" name="centreFrequencyInput">';
        new_html += '<input type=submit id="submitbtnFreq">';
        new_html += '&nbsp MHz</form>';
        $('#newCentre').empty().append(new_html);

        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
        new_html += ' action="javascript:handleCfOffsetChange(centreFrequencyOffsetInput.value)">';
        // as we remove the number inc/dec arrows in css the size parameter does work
        new_html += '<input type="number" size="12" min="-30000" max="30000" ';
        new_html += ' step="';
        new_html += cf_step;
        new_html += '" value="';
        new_html += (sdrState.getFrequencyOffsetHz()/1e6).toFixed(6);
        new_html += '" id="centreFrequencyOffsetInput" name="centreFrequencyOffsetInput">';
        new_html += '<input type=submit id="submitbtnFreqOffset">';
        new_html += '&nbsp MHz</form>';
        $('#newCfOffset').empty().append(new_html);
    }

    /////////////
    // sps
    ///////
    if(jsonConfig.digitiserSampleRate != undefined) {
        let sps = sdrState.getSps();
        let sps_step = 0.000001; // 1Hz
        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
        new_html += 'action="javascript:handleSpsChange(spsInput.value)">';
        // as we remove the number inc/dec arrows in css the size parameter does work
        new_html += '<input type="number" size="9" min="0" max="100" step="';
        new_html += sps_step;
        new_html += '" value="';
        new_html += (sps/1e6).toFixed(6);
        new_html += '" id="spsInput" name="spsInput">';
        new_html += "&nbsp Msps</form>";
        $('#newSps').empty().append(new_html);
    }

    /////////////
    // sdr BW
    ///////
    if(jsonConfig.digitiserBandwidth != undefined) {
        let sdrBwHz = sdrState.getSdrBwHz();
        let sdrbw_step = 0.01; // 10kHz
        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
        new_html += 'action="javascript:handleSdrBwChange(sdrBwInput.value)">';
        // as we remove the number inc/dec arrows in css the size parameter does work
        new_html += '<input type="number" size="3" min="0" max="100" step="';
        new_html += sdrbw_step;
        new_html += '" value="';
        new_html += (sdrBwHz/1e6).toFixed(2);
        new_html += '" id="sdrBwInput" name="sdrBwInput">';
        new_html += "&nbsp MHz</form>";
        $('#newSdrBw').empty().append(new_html);
    }

    /////////////
    // ppm error
    ///////
    if(jsonConfig.digitiserPartsPerMillion != undefined) {
        let ppm = sdrState.getPpmError();
        let ppm_step = 0.0001;
        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
        new_html += 'action="javascript:handlePpmChange(sdrPpmInput.value)">';
        // as we remove the number inc/dec arrows in css the size parameter does work
        new_html += '<input type="number" size="9" min="-500" max="500" step="';
        new_html += ppm_step;
        new_html += '" value="';
        new_html += (ppm).toFixed(2);
        new_html += '" id="sdrPpmInput" name="sdrPpmInput">';
        new_html += "</form>";
        $('#newPpm').empty().append(new_html);
    }

    /////////////
    // fft
    ///////
    if((jsonConfig.fftSizes != undefined) || (jsonConfig.fftSize != undefined)){
        let fftSizes = sdrState.getFftSizes();
        let fftSize = sdrState.getFftSize();
        if (fftSizes.length > 0) {
            new_html = '<form ';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += 'action="javascript:handleFftChange(fftSizeInput.value)">';
            new_html += '<select id="fftSizeInput" name="fftSizeInput" onchange="this.form.submit()">';
            fftSizes.forEach(function(sizeF) {
                    new_html += '<option value="'+sizeF+'"'+((sizeF==fftSize)?"selected":"")+'>'+sizeF+'</option>';
                });
            new_html += '</select></form>';
            $('#newFft').empty().append(new_html);
        }
    }

    /////////////
    // fft windows
    ///////
    if((jsonConfig.fftWindows != undefined) || (jsonConfig.fftWindow != undefined) ){
        let fftWindow = sdrState.getFftWindow();
        let fftWindows = sdrState.getFftWindows();
        if (fftWindows.length > 0) {
            new_html = '<form ';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += 'action="javascript:handleFftWindowChange(fftWindowInput.value)">';
            new_html += '<select id="fftWindowInput" name="fftWindowInput" onchange="this.form.submit()">';
            fftWindows.forEach(function(win) {
                    new_html += '<option value="'+win+'"'+((win==fftWindow)?"selected":"")+'>'+win+'</option>';
                });
            new_html += '</select></form>';
            $('#newFftWindow').empty().append(new_html);
        }
    }

    /////////////
    // gain mode
    ///////
    if((jsonConfig.digitiserGainTypes != undefined)  || (jsonConfig.digitiserGainType != undefined)) {
        let gainModes = sdrState.getGainModes();
        let gainMode = sdrState.getGainMode();
        if (gainModes.length > 0) {
            new_html = '<form';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += ' action="javascript:handleGainModeChange(gainModeInput.value)">';
            new_html += '<select id="gainModeInput" name="gainModeInput" onchange="this.form.submit()">';
            gainModes.forEach(function(mode) {
                new_html += '<option value="'+mode+'"'+((mode==gainMode)?"selected":"")+'>'+mode+'</option>';
            });
            new_html += '</select></form>';
            $('#newGmode').empty().append(new_html);
        }
    }

    /////////////
    // gain
    ///////
    if(jsonConfig.digitiserGain != undefined) {
        let gain_step = 0.1;
        new_html = '<form ';
        new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
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
    }

    /////////////
    // fps
    ///////
    if(jsonConfig.presetFps != undefined) {
        let fpsV = sdrState.getAllowedFps();
        if (fpsV.length > 0) {
            let actualFps = sdrState.getFps();
            new_html = '<form';
            new_html += ' onfocusin="configFocusIn()" onfocusout="configFocusOut()" ';
            new_html += ' action="javascript:handleFpsChange(fpsSizeInput.value)">';
            new_html += '<select id="fpsSizeInput" name="fpsSizeInput" onchange="this.form.submit()">';
            fpsV.forEach(function(fp) {
                new_html += '<option value="'+fp+'"'+((fp==actualFps)?"selected":"")+'>'+fp+'</option>';
            });
            new_html += '</select></form>';
            $('#newFPS').empty().append(new_html);
        }
    }
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
            if ( (sdrState.getSps() != spsHz) ||
                    (sdrState.getFrequencyHz() != parseInt(cfMHz*1e6)) ||
                    (sdrState.getFftSize() != num_floats) ||
                    spectrum.getResetAvgChanged() ||
                    spectrum.getResetZoomChanged() ) {

                let cfHz = cfMHz*1e6;
                sdrState.setFrequencyHz(cfHz);
                sdrState.setSps(spsHz);
                sdrState.setFftSize(num_floats);

                spectrum.setSps(spsHz);
                spectrum.setSpanHz(spsHz);
                spectrum.setCentreFreqHz(cfHz);
                // spectrum.setFftSize(num_floats); // don't do this here
                spectrum.updateAxes();
            }
            spectrum.addData(peaks, start_time_sec, start_time_nsec, end_time_sec, end_time_nsec);
        }
    }
    catch (e)
    {
        console.log("Exception while processing blob from websocket, "+e.message);
    }
}

function handleCfChangeMHz(newCfMHz) {
    let newCfHz = newCfMHz*1e6;
    let f = { value: (newCfHz), conversion: sdrState.getFrequencyOffsetHz()};
    fetch("./tuning/frequency", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(f)
    }).then(response => {
        return response.json();
    });

    sdrState.setFrequencyHz(newCfHz);
    spectrum.setCentreFreqHz(newCfHz);
    spectrum.updateAxes();
    spectrum.resetZoom();
    configFocusOut();
}

function handleCfOffsetChange(newCfOffsetMHz) {
    // update the cf to include the offset
    let cf = sdrState.getFrequencyHz();
    cf = cf - sdrState.getFrequencyOffsetHz(); // old
    if (cf < 0) {
        cf = sdrState.getFrequencyHz();
    }
    cf = cf + newCfOffsetMHz * 1e6;
    let f = { value: cf, conversion: (newCfOffsetMHz*1e6)}
    fetch("./tuning/frequency", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(f)
    }).then(response => {
        return response.json();
    });

    sdrState.setFrequencyOffsetHz(newCfOffsetMHz*1e6);
    spectrum.setCentreFreqHz(cf);
    spectrum.updateAxes();
    spectrum.resetZoom();
    configFocusOut();
}

function incrementCf(divisor) {
    let newCfHz = sdrState.getFrequencyHz();
    let step = (sdrState.getSps() / spectrum.zoom) / divisor;
    newCfHz += step;
    console.log("incrementCf", divisor, newCfHz, sdrState.getFrequencyHz())
    handleCfChangeMHz(newCfHz/1e6);
}

function zoomedToCf() {
    let newCfHz = spectrum.getZoomCfHz()
    handleCfChangeMHz(newCfHz/1e6);
    spectrum.resetZoom();
}

function ack() {
    fetch("./control/ackTime", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"ackTime":sdrState.getLastDataTime()})
    }).then(response => {
        return response.json();
    });
}

function handleSpsChange(newSps) {
    fetch("./digitiser/digitiserSampleRate", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserSampleRate":(newSps*1e6)})
    }).then(response => {
        return response.json();
    });

    sdrState.setSps(newSps*1e6);
    // force the sdr input bw to the same as the sps
    sdrState.setSdrBwHz(newSps*1e6);
    spectrum.setSps(newSps);
    spectrum.updateAxes();
    spectrum.resetZoom();
    configFocusOut();
}

function handleSdrBwChange(newBwMHz) {
    fetch("./digitiser/digitiserBandwidth", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserBandwidth":(newBwMHz*1e6)})
    }).then(response => {
        return response.json();
    });

    sdrState.setSdrBwHz(newBwMHz*1e6);
    configFocusOut();
}

function handlePpmChange(newPpm) {
    fetch("./digitiser/digitiserPartsPerMillion", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserPartsPerMillion":(newPpm)})
    }).then(response => {
        return response.json();
    });

    sdrState.setPpmError(newPpm);
    configFocusOut();
}

function handleFftChange(newFft) {
    fetch("./spectrum/fftSize", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"fftSize":(newFft)})
    }).then(response => {
        return response.json();
    });

    sdrState.setFftSize(newFft);
    // spec.setFftSize(num_floats); // don't do this here as spectrum has to know it changed
    configFocusOut();
}

function handleFftWindowChange(newWindow) {
    fetch("./spectrum/fftWindow", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"fftWindow":(newWindow)})
    }).then(response => {
        return response.json();
    });

    sdrState.setFftWindow(newWindow);
    configFocusOut();
}

function handleInputChange(newSource, newParams) {
    let input = { source:newSource, params:newParams, connected:'false'};
    fetch("./input/source", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(input)
    }).then(response => {
        return response.json();
    });

    sdrState.setInputSource(newSource);
    sdrState.setInputSourceParams(newParams);
    configFocusOut();
}

function handleDataFormatChange(newFormat) {
    fetch("./digitiser/digitiserFormat", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserFormat":(newFormat)})
    }).then(response => {
        return response.json();
    });

    sdrState.setDataFormat(newFormat);
    configFocusOut();
}

function handleFpsChange(newFps) {
    let fps = { set: newFps, measured: 0};
    fetch("./control/fps", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"fps":(fps)})
    }).then(response => {
        return response.json();
    });
    configFocusOut();
}

function handleGainChange(newGain) {
    fetch("./digitiser/digitiserGain", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserGain":(newGain)})
    }).then(response => {
        return response.json();
    });

    sdrState.setGain(newGain);
    configFocusOut();
}
function handleGainModeChange(newMode) {
    fetch("./digitiser/digitiserGainType", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"digitiserGainType":(newMode)})
    }).then(response => {
        return response.json();
    });

    sdrState.setGainMode(newMode);
    configFocusOut();
}

function handleStopToggle() {
    stop.value = !stop.value;

    fetch("./control/stop", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"stop":(stop.value)})
    }).then(response => {
        return response.json();
    });

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

function showSnapTable() {
    // only update if the list length is different
    if(snapState.getDirectoryListEntries() !=  ($('#snapFileTable tr').length-1)) {
        updateSnapFileList();
    }
}

function updateSnapFileList() {
    $("#snapFileTable tbody tr").remove(); // delete all the current rows
    let row_count = 0;
    for (const file of snapState.getDirectoryList()) {
        let new_row='<tr>';
        let fname = '<div title="'+file[0]+'" class="CropLongTexts180">';
        // link to the file so we can download it, hardcoded snapshot directory name !
        fname += '<a href="snapshots/'+file[0]+'">'+file[0]+'</a>';
        fname +='</div>';
        new_row += '<td>'+fname+'</td>';
        // size with a hover over of a png showing a spectrum image
        // new_row += '<td><span>'+file[1]+'</span><img src="./thumbnails/'+file[0]+'.png"></td>';
        new_row += '<td>'+file[1]+'</td>';
        new_row += '<td><img src="./thumbnails/'+file[0]+'.png"></td>';

        let id = row_count;
        new_row += '<td><input type="image" title="play" id="play_'+id+'" src="./icons/play.png"></td>';
        new_row += '<td><input type="image" title="delete" id="delete_'+id+'" src="./icons/bin.png"></td>';
        new_row += "</tr>";
        $('#snapFileTable').append(new_row);

        // show which file is playing
        if (sdrState.getInputSource() == "file") {
            if (sdrState.getInputSourceParams() == file[0]) {
                $('#play_'+id).closest("td").css("background-color", "#00ff00");
            } else {
                $('#play_'+id).closest("td").css("background-color");
            }
        }

        // handle icon buttons for play and delete
        $('#play_'+id).click(function() {
            // force input change, command goes by sdrState
            handleInputChange("file", file[0]);
        } );
        $('#delete_'+id).click(function() {
            // indicate that we have deleted the file
            $('#delete_'+id).closest("td").css("background-color", "#ff0000");
            fetch("./snapshot/snapDelete", {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({"snapDelete":(file[0])})
                
            }).then(response => {
                return response.json();
            });
        
            // command goes by snapState
            snapState.setDeleteFilename(file[0]);
        } );
        row_count += 1;
    }
}

function showNewSnap() {
    // show all the values fro the snap
    // if we have focus on a form then don't update the table
    if (snapFormInFocus) {
        return;
    }
    let new_html=""

    new_html = '<button type="button" id="snapTriggerBut" title="Manual trigger" class="specbuttons btn btn-outline-dark mx-1 my-1">Trigger</button>';
    $('#newSnapTriggerState').empty().append(new_html);
    $('#snapTriggerBut').click(function() {handleSnapTrigger();});

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

    let fileFormats = snapState.getFileFormats();
    let fileFormat = snapState.getFileFormat();
    new_html = '<form';
    new_html += ' onfocusin="snapTableFocusIn()" onfocusout="snapTableFocusOut()" ';
    new_html += ' action="javascript:handleSnapFileFormatChange(snapFileFormat.value)">';
    new_html += '<select id="snapFileFormat" name="snapFileFormat" onchange="this.form.submit()">';
    fileFormats.forEach(function(type) {
        new_html += '<option value="'+type+'"'+((type==fileFormat)?"selected":"")+'>'+type+'</option>';
    });
    new_html += '</select></form>';
    $('#newFileFormat').empty().append(new_html);

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

}

function snapTableFocusIn(){
    snapFormInFocus = true;
}
function snapTableFocusOut(){
    snapFormInFocus = false;
}

function syncCurrentFast() {
    // things that we wish to update faster
    
    fetch('./control/delay').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setUiDelay(obj.delay);
        $('#currentDelay').empty().append(sdrState.getUiDelay().toFixed(2));
    }).catch(function (error) {
    });

    fetch('./control/readRatio').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setReadRatio(obj.readRatio);
        $('#currentReadRatio').empty().append(sdrState.getReadRatio().toFixed(2));
    }).catch(function (error) {
    });

    fetch('./control/headroom').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setHeadroom(obj.headroom);
        $('#currentHeadroom').empty().append(sdrState.getHeadroom().toFixed(1) +'%');
    }).catch(function (error) {
    });

    fetch('./control/overflows').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setOverflows(obj.overflows);
        $('#currentOverflows').empty().append(sdrState.getOverflows());
    }).catch(function (error) {
    });

    fetch('./control/fps').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setFps(obj.fps);
        let maxFps = sdrState.getSps() / sdrState.getFftSize();
        $('#currentFPS').empty().append(sdrState.getMeasuredFps().toFixed(1), "/", sdrState.getFps().toFixed(0),", max:", maxFps.toFixed(1));
    }).catch(function (error) {
    });
    
    fetch('./control/oneInN').then(function (response) {
        return response.json();
    }).then(function (obj) {
        $('#currentOneInN').empty().append(obj.oneInN.toFixed(1));
    }).catch(function (error) {
    });

    fetch('./digitiser/digitiserGain').then(function (response) {
        return response.json();
    }).then(function (obj) {
        sdrState.setGain(obj.digitiserGain);
        $('#currentGain').empty().append(sdrState.getGain() + ' dB');
    }).catch(function (error) {
    });
    
    fetch('./snapshot/snapSize').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setCurrentSize(obj.snapSize.current);
        snapState.setExpectedSize(obj.snapSize.limit);
        $('#currentSnapSize').empty().append(snapState.getCurrentSize().toFixed(2) + ' MBytes');
        $('#newSnapSize').empty().append(snapState.getExpectedSize().toFixed(2) + ' MBytes');
    }).catch(function (error) {
    });

    fetch('./snapshot/snapTriggerState').then(function (response) {
        return response.json();
    }).then(function (obj) {
        snapState.setTriggerState(obj.snapTriggerState);
        $('#currentSnapTriggerState').empty().append(snapState.getTriggerState());
        if (snapState.getTriggerState() == "triggered") {
            $('#currentSnapTriggerState').addClass('redTrigger');
            $('#currentSnapTriggerState').removeClass('greenTrigger');
        } else {
            $('#currentSnapTriggerState').addClass('greenTrigger');
            $('#currentSnapTriggerState').removeClass('redTrigger');
        }
    }).catch(function (error) {
    });
}

function configFocusIn(){
    configFormInFocus = true;
}
function configFocusOut(){
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
            }
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
    $('#cfDwnBut4').click(function() {incrementCf(-4);});
    $('#cfDwnBut1').click(function() {incrementCf(-10);});
    $('#cfUpBut1').click(function() {incrementCf(10);});
    $('#cfUpBut4').click(function() {incrementCf(4);});
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
    $('#clrToTrc1But').click(function() {spectrum.clearTrace1();});
    $('#hideTrc1But').click(function() {spectrum.hideTrace1();});

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

    let offset = sessionStorage.getItem("FrequencyOffsetHz");
    if (offset != null) {
        sdrState.setFrequencyOffsetHz(offset);
    }

    // first paas
    syncCurrent();
    syncNew();
    syncCurrentFast();

    // Connect to websocket
    connectWebSocket(spectrum);

    // continually get and show the current state
    setInterval(function() {
        syncCurrent();
        }, 2000);

    // continually get and show the new possible states
    setInterval(function() {
        syncNew();
        showSnapTable();
        }, 4000);

    // fast update stuff
    setInterval(function() {
        syncCurrentFast();
        ack();
    }, 500);
}

window.onload = Main;
