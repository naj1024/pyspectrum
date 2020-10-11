/*
 * Copyright (c) 2019 Jeppe Ledet-Pedersen
 * This software is released under the MIT license.
 * See the LICENSE file for further details.
 *
 * Modified from original with markers and other bits
 */

'use strict';

Spectrum.prototype.squeeze = function(value, out_min, out_max) {
    if (value <= this.min_db)
        return out_min;
    else if (value >= this.max_db)
        return out_max;
    else
        return Math.round((value - this.min_db) / (this.max_db - this.min_db) * out_max);
}

Spectrum.prototype.rowToImageData = function(bins) {
    let points = parseInt(bins.length / this.zoom);
    let centre  = parseInt(bins.length / 2);

    // account for zoom
    if (this.zoomCentreBin >= 0) {
        centre = this.zoomCentreBin;
    }
    let start = parseInt(centre - (points / 2)); // may be -ve
    let step = points / bins.length;
    let dataPointIndex = start;

    // image data is 4 times the length of the bins due to colour data
    for (var i = 0; i < this.imagedata.data.length; i += 4) {
        // compress data range into the colour map size
        let dataIndex = parseInt(dataPointIndex); // nearest integer bin index
        let cindex = this.squeeze(bins[dataIndex], 0, 255);
        let colour = 0;
        if ( (cindex < this.colourmap.length) && (cindex >= 0) )
            colour = this.colourmap[cindex];
        else
            colour = this.colourmap[0];
        this.imagedata.data[i+0] = colour[0];
        this.imagedata.data[i+1] = colour[1];
        this.imagedata.data[i+2] = colour[2];
        this.imagedata.data[i+3] = 255;

        dataPointIndex = dataPointIndex+step;
    }
}

Spectrum.prototype.drawWaterfall = function() {
    // redraw the current waterfall
    var width = this.ctx.canvas.width;
    var height = this.ctx.canvas.height;

    // Copy scaled FFT canvas to screen. Only copy the number of rows that will
    // fit in waterfall area to avoid vertical scaling.
    this.ctx.imageSmoothingEnabled  = false;
    var rows = Math.min(this.wf_rows, height - this.spectrumHeight);
    this.ctx.drawImage(this.ctx_wf.canvas,
        0, 0, this.wf_size, rows,
        0, this.spectrumHeight, width, height - this.spectrumHeight);
}

Spectrum.prototype.addWaterfallRow = function(bins) {
    // Shift waterfall 1 row down
    this.ctx_wf.drawImage(this.ctx_wf.canvas,
        0, 0, this.wf_size, this.wf_rows - 1,
        0, 1, this.wf_size, this.wf_rows - 1);

    // Draw new line on waterfall canvas
    this.rowToImageData(bins);
    this.ctx_wf.putImageData(this.imagedata, 0, 0);

    this.drawWaterfall();
}

Spectrum.prototype.drawFFT = function(bins, colour) {
    if(typeof bins != 'undefined') {
        this.ctx.beginPath();
        this.ctx.moveTo(-1, this.spectrumHeight + 1);

        // modify what we draw by the zoom factor
        let points = parseInt(bins.length / this.zoom);
        let centre  = parseInt(bins.length / 2);
        if (this.zoomCentreBin >= 0) {
            centre = this.zoomCentreBin;
        }
        let start = parseInt(centre - (points / 2)); // may be -ve
        for (var i = 0; i < points; i++) {
            let point = i + start;
            let y = -1;
            if( point >= 0) {
                y = this.spectrumHeight - this.squeeze(bins[point], 0, this.spectrumHeight);
            }
            if (y > this.spectrumHeight - 1)
                y = this.spectrumHeight + 1; // Hide underflow
            if (y < 0)
                y = 0;
            if (i == 0)
                this.ctx.lineTo(-1, y);
            this.ctx.lineTo(parseInt(i*this.zoom), y);
            if (point == bins.length - 1)
                this.ctx.lineTo(this.wf_size + 1, y);
        }
        //this.ctx.lineTo(this.wf_size + 1, this.spectrumHeight + 1);
        this.ctx.strokeStyle = colour;
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
    }
}

Spectrum.prototype.drawSpectrum = function(bins) {
    var width = this.ctx.canvas.width;
    var height = this.ctx.canvas.height;

    // Fill with canvas
    this.ctx.fillStyle = this.backgroundColour;
    this.ctx.fillRect(0, 0, width, height);

    // should we max hold and average in a paused state?
    // Max hold, before averaging
    if (this.maxHold) {
        if (!this.binsMax || this.binsMax.length != bins.length) {
            this.binsMax = Array.from(bins);
        } else {
            for (var i = 0; i < bins.length; i++) {
                if (bins[i] > this.binsMax[i]) {
                    this.binsMax[i] = bins[i];
                }
            }
        }
    }

    // Averaging
    if (this.averaging > 0) {
        if (!this.binsAverage || this.binsAverage.length != bins.length) {
            this.binsAverage = Array.from(bins);
        } else {
            for (var i = 0; i < bins.length; i++) {
                this.binsAverage[i] += this.alpha * (bins[i] - this.binsAverage[i]);
            }
        }
        bins = this.binsAverage;
    }

    // Do not draw anything if spectrum is not visible
    if (this.ctx_axes.canvas.height < 1)
        return;

    // Scale for FFT
    this.ctx.save();
    this.ctx.scale(width / this.wf_size, 1);

    // Draw maxhold
    if (this.maxHold)
        this.drawFFT(this.binsMax, this.maxHoldColour);

    // Draw FFT bins, note that last drawFFT will get the gradient fill
    this.drawFFT(bins,this.magnitudesColour);

    // Restore scale
    this.ctx.restore();

    // do we wish the spectrum to be gradient filled
    if (this.spectrumGradient) {
        // Fill scaled path
        this.ctx.fillStyle = this.gradient;
        this.ctx.fill();
    }
    // Copy axes from offscreen canvas
    this.ctx.drawImage(this.ctx_axes.canvas, 0, 0);
}

Spectrum.prototype.updateAxes = function() {
    var width = this.ctx_axes.canvas.width;
    var height = this.ctx_axes.canvas.height;

    // Clear axes canvas
    this.ctx_axes.clearRect(0, 0, width, height);

    // Draw axes
    this.ctx_axes.font = "12px sans-serif";
    this.ctx_axes.fillStyle = this.canvasTextColour;
    this.ctx_axes.textBaseline = "middle";

    // y-axis labels
    this.ctx_axes.textAlign = "left";
    var step = 10;
    for (var i = this.min_db + 10; i <= this.max_db - 10; i += step) {
        var y = height - this.squeeze(i, 0, height);
        this.ctx_axes.fillText(i, 5, y);

        this.ctx_axes.beginPath();
        this.ctx_axes.moveTo(20, y);
        this.ctx_axes.lineTo(width, y);
        this.ctx_axes.strokeStyle = "rgba(200, 200, 200, 0.40)"; // TODO: with specified colour/intensity
        this.ctx.lineWidth = 1;
        this.ctx_axes.stroke();
    }

    this.ctx_axes.textBaseline = "bottom";
    // Frequency labels on x-axis
    let centreFreqHz = this.getZoomCfHz();
    let spanHz = this.getZoomSpanHz();

    for (var i = 0; i < 11; i++) {
        var x = Math.round(width / 10) * i;
        // mod 5 to give just the first,middle and last - small screens don't handle lots of marker values
        if ((i%5) == 0) {
            if (spanHz > 0) {
                var adjust = 0;
                if (i == 0) {
                    this.ctx_axes.textAlign = "left";
                    adjust = 3;
                } else if (i == 10) {
                    this.ctx_axes.textAlign = "right";
                    adjust = -3;
                } else {
                    this.ctx_axes.textAlign = "center";
                }

                var freq = centreFreqHz + spanHz / 10 * (i - 5);
                if (centreFreqHz + spanHz > 1e9){
                    freq = freq / 1e9;
                    freq = freq.toFixed(3) + "GHz";
                }
                else if (centreFreqHz + spanHz > 1e6){
                    freq = freq / 1e6;
                    freq = freq.toFixed(3) + "MHz";
                }
                else if (centreFreqHz + spanHz > 1e3){
                    freq = freq / 1e3;
                    freq = freq.toFixed(3) + "kHz";
                }
                this.ctx_axes.fillText(freq, x + adjust, height - 3);
            }
        }

        this.ctx_axes.beginPath();
        this.ctx_axes.moveTo(x, 0);
        this.ctx_axes.lineTo(x, height);
        this.ctx_axes.strokeStyle = "rgba(200, 200, 200, 0.40)";
        this.ctx.lineWidth = 1;
        this.ctx_axes.stroke();
    }
}

Spectrum.prototype.addData = function(magnitudes, start_sec, start_nsec, end_sec, end_nsec) {
    if (!this.paused) {
        // remember the data so we can pause and still use markers
        // start times are for the first magnitude between updates
        // end times are for the last magnitude
        // start and end times can be the same

        // pack it all up to record of everything
        let spec = {
            magnitudes: new Array(magnitudes),
            start_sec: start_sec,
            start_nsec: start_nsec,
            end_sec: end_sec,
            end_nsec: end_nsec,
            inputCount: this.inputCount
        }
        this.currentMagnitudes = magnitudes;    // peak magnitudes between updates, easy access
        this.currentSpectrum = spec;

        // if the next index exists then we have wrapped and we can update the
        // oldest time value
        if (this.inputCount >= this.spectrums.length) {
            let ind = this.spectrumsIndex + 1;
            if (ind >= this.spectrums.length) {
                ind = 0;
            }
            this.oldestTime = this.spectrums[ind].start_sec + (this.spectrums[ind].start_nsec/1e9);
        }
        this.spectrums[this.spectrumsIndex] = spec;
        this.spectrumsIndex = (this.spectrumsIndex + 1) % this.spectrums.length;
        this.inputCount += 1;

        // if the fftSize changes then we need to  do things
        if (magnitudes.length != this.fftSize) {
            this.wf_size = magnitudes.length;
            this.fftSize = magnitudes.length;
            this.ctx_wf.canvas.width = magnitudes.length;
            this.imagedata = this.ctx_wf.createImageData(magnitudes.length, 1);
        }
        this.drawSpectrum(magnitudes);
        this.addWaterfallRow(magnitudes);

        if (this.live_peak_search) {
            this.searchForPeak();
        }
        this.updateMarkers();
        this.resize();

        this.currentTime = start_sec + (start_nsec/1e9);
        if (this.firstTime == 0) {
            this.firstTime = this.currentTime;
            this.oldestTime = this.currentTime;
        }
    } else {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.updateWhenPaused = function() {
    // keep things as they are but allow markers to work
    // currentMagnitudes can change by moving mouse in spectrogram
    this.drawSpectrum(this.currentMagnitudes);
    this.drawWaterfall();
    this.updateMarkers();
    this.resize();
}

Spectrum.prototype.updateSpectrumRatio = function() {
    this.spectrumHeight = Math.round(this.canvas.height * this.spectrumPercent / 100.0);

    this.gradient = this.ctx.createLinearGradient(0, 0, 0, this.spectrumHeight);
    for (var i = 0; i < this.colourmap.length; i++) {
        var c = this.colourmap[this.colourmap.length - 1 - i];
        this.gradient.addColorStop(i / this.colourmap.length,
            "rgba(" + c[0] + "," + c[1] + "," + c[2] + ", 1.0)");
    }
}

Spectrum.prototype.resize = function() {
    // the canvas width/height is set to the same as the client width height
    var width = this.canvas.clientWidth;
    var height = this.canvas.clientHeight;

    if (this.canvas.width != width ||
        this.canvas.height != height) {
        this.canvas.width = width;
        this.canvas.height = height;
        this.updateSpectrumRatio();
    }

    if (this.axes.width != width ||
        this.axes.height != this.spectrumHeight) {
        this.axes.width = width;
        this.axes.height = this.spectrumHeight;
        this.updateAxes();
    }
}

Spectrum.prototype.setSpectrumPercent = function(percent) {
    if (percent >= 0 && percent <= 100) {
        this.spectrumPercent = percent;
        this.updateSpectrumRatio();
    }
}

Spectrum.prototype.incrementSpectrumPercent = function() {
    if (this.spectrumPercent + this.spectrumPercentStep <= 100) {
        this.setSpectrumPercent(this.spectrumPercent + this.spectrumPercentStep);
    }
}

Spectrum.prototype.decrementSpectrumPercent = function() {
    if (this.spectrumPercent - this.spectrumPercentStep >= 0) {
        this.setSpectrumPercent(this.spectrumPercent - this.spectrumPercentStep);
    }
}

Spectrum.prototype.togglecolour = function() {
    this.colourindex++;
    if (this.colourindex >= colourmaps.length)
        this.colourindex = 0;
    this.colourmap = colourmaps[this.colourindex];
    this.updateSpectrumRatio();
}

Spectrum.prototype.setRange = function(min_db, max_db) {
    this.min_db = min_db;
    this.max_db = max_db;
    this.updateAxes();
}

Spectrum.prototype.refUp = function() {
    // keep range the same
    this.setRange(this.min_db - 5, this.max_db - 5);
}

Spectrum.prototype.refDown = function() {
    // keep range the same
    this.setRange(this.min_db + 5, this.max_db + 5);
}

Spectrum.prototype.rangeIncrease = function() {
    // keep max same, i.e. reference level
    this.setRange(this.min_db - 5, this.max_db);
}

Spectrum.prototype.rangeDecrease = function() {
    // keep max the same, i.e. reference level
    if ( (this.max_db - this.min_db) > 10)
        // don't change range below 10dB
        this.setRange(this.min_db + 5, this.max_db);
}

Spectrum.prototype.roundTo10 =  function(num) {
    let smallest = parseInt(parseInt(num / 10) * 10);
    let largest = parseInt(smallest + 10);
    // Return of closest of two
    return (num - smallest > largest - num)? largest : smallest;
}

Spectrum.prototype.autoRange = function() {
    // Find max and min
    let max = -1000; // suitable small dB
    let min = 1000; // suitable large dB
    for (const s of this.spectrums) {
        if (s) {
            let smax = Math.max(...s.magnitudes[0]);
            let smin = Math.min(...s.magnitudes[0]);
            if (smin < min)
                min = smin;
            if (smax > max)
                max = smax;
        }
    }
    if (max != -1000 && min != 1000) {
        // to nearest 10dB
        this.max_db = this.roundTo10(max+16); // 10dB headroom
        this.min_db = this.roundTo10(min-6);
        this.setRange(this.min_db, this.max_db);
    }
}

Spectrum.prototype.setCentreFreq = function(MHz) {
    this.centreHz = Math.trunc(MHz * 1e6);
}

Spectrum.prototype.getCentreFreqHz = function() {
    return this.centreHz;
}

Spectrum.prototype.setSps = function(sps) {
    this.sps = sps;
}

Spectrum.prototype.getSps = function() {
    return this.sps;
}

Spectrum.prototype.getFftSize = function() {
    return this.fftSize;
}

Spectrum.prototype.setFftSize = function(fftSize) {
    this.fftSize = fftSize;
}

Spectrum.prototype.setSpanHz = function(hz) {
    this.spanHz = hz;
}

Spectrum.prototype.getSpanHz = function() {
    return this.spanHz;
}

Spectrum.prototype.getStartTime = function() {
    return this.firstTime;
}

Spectrum.prototype.setAveraging = function(num) {
    if (num >= 0) {
        this.averaging = num;
        this.alpha = 2 / (this.averaging + 1)
        this.updatedAveraging = true;
    }
}

Spectrum.prototype.incrementAveraging = function() {
    this.setAveraging(this.averaging + 1);
    this.updatedAveraging = true;
}

Spectrum.prototype.decrementAveraging = function() {
    if (this.averaging > 0) {
        this.setAveraging(this.averaging - 1);
        this.updatedAveraging = true;
    }
}

Spectrum.prototype.getResetAvgChanged = function() {
    let updated = this.updatedAveraging;
    this.updatedAveraging = false;
    return updated;
}

Spectrum.prototype.getResetZoomChanged = function() {
    let updated = this.updatedZoom;
    this.updatedZoom = false;
    return updated;
}

Spectrum.prototype.liveMarkersAndUnHideMarkers = function() {
    this.liveMarkerOn(); // Expected operation when paused
    $('input:radio[name=markerRadio]')[1].checked = true; // for completeness
    if (this.hideAllMarkers) {
        this.hideAllMarkers = false;
        $("#hideMarkersBut").button('toggle'); // update the UI button state
    }
}

Spectrum.prototype.setPaused = function(paused) {
    // pause or unpause must unlock any locked spectrogram
    this.lockedSpectrogram = false;
    this.lockedSpectrogramMarkerValues = undefined;
    this.lockedSpectrogramIndex = null;

    this.paused = paused;
    this.liveMarkersAndUnHideMarkers();
}

Spectrum.prototype.togglePaused = function() {
    this.setPaused(!this.paused);
}

Spectrum.prototype.setMaxHold = function(maxhold) {
    this.maxHold = maxhold;
    this.binsMax = undefined;
}

Spectrum.prototype.toggleMaxHold = function() {
    this.setMaxHold(!this.maxHold);
}

Spectrum.prototype.toggleFullscreen = function() {
    // TODO: Exit from full screen does not put the size back correctly
    // This is full screen just for the spectrum & spectrogram
    if (!this.fullscreen) {
        if (this.canvas.requestFullscreen) {
            this.canvas.requestFullscreen();
        } else if (this.canvas.mozRequestFullScreen) {
            this.canvas.mozRequestFullScreen();
        } else if (this.canvas.webkitRequestFullscreen) {
            this.canvas.webkitRequestFullscreen();
        } else if (this.canvas.msRequestFullscreen) {
            this.canvas.msRequestFullscreen();
        }
        this.fullscreen = true;
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
        this.fullscreen = false;
    }
}

Spectrum.prototype.onKeypress = function(e) {
    // only respond if the mouse is in the canvas
    if (this.mouseInCanvas) {
        if (e.key == "f") {
            this.toggleFullscreen();
        } else if (e.key == "c") {
            this.togglecolour();
        } else if (e.key == "+") {
            this.incrementAveraging();
        } else if (e.key == "-") {
            this.decrementAveraging();
        } else if (e.key == "m") {
            this.toggleMaxHold();
            $("#maxHoldBut").button('toggle'); // update the UI button state
        } else if (e.key == "l") {
            this.updateSpectrogramLock();
        } else if (e.key == "p") {
            this.togglePaused();
            $("#pauseBut").button('toggle'); // update the UI button state
        } else if (e.key == "ArrowUp") {
            this.refUp();
        } else if (e.key == "ArrowDown") {
            this.refDown();
        } else if (e.key == "ArrowLeft") {
            this.rangeDecrease();
        } else if (e.key == "ArrowRight") {
            this.rangeIncrease();
        }
    }
}

Spectrum.prototype.addMarker = function(frequencyHz, magdB, time_start, spectrogram_canvas_y, inputCount, spectrum_flag) {
    // force showing of markers if we are adding markers
    this.liveMarkersAndUnHideMarkers();

    let marker = {};
    marker['spectrogram_canvas_y'] = parseInt(spectrogram_canvas_y);
    marker['freqHz'] = frequencyHz;
    marker['power'] = magdB;
    marker['diffTime'] = time_start;
    marker['visible'] = true;
    marker['inputCount'] = inputCount;
    marker['spectrumFlag'] = spectrum_flag;

    let deltaHz = 0;
    let deltadB = 0;
    let deltaTime = 0;
    if (this.markersSet.size != 0){
        let as_array = Array.from(this.markersSet);
        let previous_marker = as_array[this.markersSet.size-1];
        deltaHz = (frequencyHz - previous_marker.freqHz);
        deltadB = (magdB - previous_marker.power);
        deltaTime = (time_start - previous_marker.diffTime);
    }
    // we will allow duplicate markers, otheriwise we have to decide what is a duplicate - freq or time
    this.markersSet.add(marker);
    let number = this.markersSet.size-1;
    let marker_id = "marker_" + number;
    let bin_id = "bin_marker_" + number;

    // add to table of markers
    let new_row="<tr>";

    // marker number and checkbox
    new_row += '<td>'+number+'</td>';
    new_row += '<td>';
    new_row += '<input type="checkbox" checked="true" id="'+marker_id+'"> ';
    new_row += '<label for="'+marker_id+'" /label>';
    new_row += '</td>';

    // data
    new_row += "<td>"+(frequencyHz/1e6).toFixed(6)+"</td>";
    new_row += "<td>"+magdB.toFixed(1)+"</td>";
    new_row += "<td>"+time_start.toFixed(6)+"</td>";
    new_row += "<td>"+this.convertFrequencyForDisplay(deltaHz,3)+"</td>";
    new_row += "<td>"+deltadB.toFixed(1)+"</td>";
    new_row += "<td>"+deltaTime.toFixed(6)+"</td>";

    // bin
    new_row += '<td>';
    new_row += '<input type="image" id="'+bin_id+'" src="./icons/bin.png"> ';
    new_row += '</td>';

    new_row += "</tr>";
    $('#markerTable').append(new_row);

    // todo: had to use a global, can't work out how to get hold of this'
    $('#'+marker_id).click(function() {spectrum.markerCheckBox(number);});
    $('#'+bin_id).click(function() {spectrum.deleteMarker(number);});
}

Spectrum.prototype.markerCheckBox = function(id) {
    // toggle visible - bit open loop, TODO: better to have the state of the tick box
    let marker_num = 0;
    for (let item of this.markersSet) {
        if (id == marker_num) {
            item.visible = ! item.visible;
            break;
        }
        marker_num += 1;
    }
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.liveMarkerOn = function() {
    this.live_marker_on = true;
    if (!data_active) {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.liveMarkerOff = function() {
    this.live_marker_on = false;
    this.liveMarker = undefined;
    if (!data_active) {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.clearMarkers = function() {
    // clear the table
    //  $(this).parents("tr").remove();
    let num_rows=this.markersSet.size;
    for (let i=num_rows; i>0; i--) {
        $("#markerTable tr:eq("+i+")").remove(); //to delete row 'i', delrowId should be i+1
    }
    this.markersSet.clear();
    this.liveMarker = undefined;
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.deleteMarker =  function(id) {
    let marker_num = 0;
    let oldMarkers = new Set(this.markersSet);
    this.clearMarkers();
    // add back all markers but the one we need to delete
    for (let item of oldMarkers) {
        if (id != marker_num) {
            this.addMarker(item.freqHz, item.power, item.diffTime, item.spectrogram_canvas_y, item.inputCount, item.spectrumFlag);
        }
        marker_num += 1;
    }
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.hideMarkers = function() {
    this.hideAllMarkers = !this.hideAllMarkers;
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.toggleTrackPeak = function() {
    this.live_peak_search = !this.live_peak_search;
    if( this.live_peak_search) {
        this.liveMarkersAndUnHideMarkers();
    }
}

Spectrum.prototype.findPeak = function() {
    // called from button

    this.liveMarkersAndUnHideMarkers();
    if (this.live_peak_search) {
        // we don't want live peak tracking on if we asked for the peak
        this.toggleTrackPeak();
        $("#peakTrackBut").button('toggle'); // update the UI button state
    }

    // if we are in max-hold then we need the peak of the maximum trace
    // else if we are locked to a spectrogram row then find max in that spectrum
    // else find the maximum in the spectrogram
    let markerValues = undefined;

    if (this.maxHold) {
        markerValues = this.getMarkerValuesForMaxHold();
    } else if (this.lockedSpectrogramMarkerValues) {
        // find peak in spectrum of the locked spectrogram
        markerValues = this.getMarkerValuesFromSpectrum(this.lockedSpectrogramMarkerValues.spectrum);
    } else if (this.averaging > 0) {
        markerValues = this.getMarkerValuesForAveraging();
    } else {
        // find row holding peak power in spectrogram data
        let max = -1000;
        let peakSpectrum = undefined;
        for (const s of this.spectrums) {
            if (s) {
                let smax = Math.max(...s.magnitudes[0]);
                if (smax > max) {
                    max = smax;
                    peakSpectrum = s; // best so far
                }
            }
        }
        if (typeof peakSpectrum != 'undefined') {
            markerValues = this.getMarkerValuesFromSpectrum(peakSpectrum);
        }
    }
    if (markerValues != undefined) {
        this.liveMarker = markerValues;
        this.addMarker(markerValues.freqHz, markerValues.power, markerValues.diffTime,
                        markerValues.spectrogram_canvas_y, markerValues.inputCount, markerValues.spectrum_flag);
    }

    if (!data_active) {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.findNextPeak = function() {
    console.log("Next peak button support not available yet");
}

Spectrum.prototype.getMarkerValuesForAveraging = function() {
    // return a marker set from the average values
    let values = undefined;
    if ((this.averaging > 0) && this.binsAverage != undefined) {
        let basic = this.getBasicValuesFromMagnitudes(this.binsAverage);

        // markers format
        values = {
              freqHz: basic.freqHz,
              spectrum_flag: true,
              power: basic.power,
              diffTime: -1,
              spectrogram_canvas_y: -1,
              bin: basic.bin,
              spectrum: undefined,
              magnitudes: this.binsMax
        };
    }
    return values;
}

Spectrum.prototype.getMarkerValuesForMaxHold = function() {
    // return a marker set from the max held values
    let values = undefined;
    if (this.maxHold && this.binsMax != undefined) {
        let basic = this.getBasicValuesFromMagnitudes(this.binsMax);

        // markers format
        values = {
              freqHz: basic.freqHz,
              spectrum_flag: true,
              power: basic.power,
              diffTime: -1,
              spectrogram_canvas_y: -1,
              bin: basic.bin,
              spectrum: undefined,
              magnitudes: this.binsMax
        };
    }
    return values;
}

Spectrum.prototype.getBasicValuesFromMagnitudes = function(mags) {
    // return basic info about the magnitudes
    // we account for the zoom we have

    // When zoomed in only look over the zoomed spectrum
    let magnitudes = mags;
    let offset = 0;
    if (this.zoom > 1) {
        magnitudes = mags.slice(this.zoomStartBin, this.zoomEndBin);
        offset = this.zoomStartBin;
    }

    // stackoverflow 11301438, index of peak value
    let indexOfPeak = magnitudes.reduce((bestIndexSoFar, currentlyTestedValue, currentlyTestedIndex, array) => currentlyTestedValue > array[bestIndexSoFar] ? currentlyTestedIndex : bestIndexSoFar, 0);
    indexOfPeak += offset; // patch up where we are in the given array

    let freq_value = this.convertFftBinToFrequency(indexOfPeak);
    let power = mags[indexOfPeak];

    return {
        freqHz: freq_value,
        power: power,
        bin: indexOfPeak
    };
}

Spectrum.prototype.getMarkerValuesFromSpectrum = function(spec) {
    // return marker type values from a spectrum, spectrum includes time etc

    let basic = this.getBasicValuesFromMagnitudes(spec.magnitudes[0]);

    // calculate the time of this spectrum
    let t =  spec.start_sec;
    t += spec.start_nsec/1e9;
    let diff_time =  t - this.firstTime;

    // markers format
    let values = {
          freqHz: basic.freqHz,
          spectrum_flag: true,
          power: basic.power,
          diffTime: diff_time,
          spectrogram_canvas_y: -1,
          bin: basic.bin,
          spectrum: spec,
          magnitudes: spec
    };
    return values;
}

Spectrum.prototype.searchForPeak = function() {
    // look through current spectrum and set the live marker to the peak
    this.liveMarker = this.getMarkerValuesFromSpectrum(this.currentSpectrum);
    if (!data_active) {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.convertFftBinToFrequency =  function(binNumber) {
    let freq_value = (this.centreHz - (this.spanHz / 2)) + (binNumber * (this.spanHz / this.fftSize));
    return freq_value;
}

Spectrum.prototype.convertFrequencyToFftBin =  function(frequencyHz) {
    let binNumber = (frequencyHz - this.centreHz + (this.spanHz/ 2)) * (this.fftSize / this.spanHz)
    return parseInt(binNumber);
}

Spectrum.prototype.convertCanvasXToFrequencyHz = function(xpos) {
    // no checks for being in range
    let spanHz = this.getZoomSpanHz();
    let centreHz = this.getZoomCfHz();
    let perHz = spanHz / this.canvas.width;
    let freq_value = (centreHz - (spanHz / 2)) + (xpos * perHz);
    return freq_value;
}

Spectrum.prototype.convertFrequencyHzToCanvasX = function(freqHz) {
    // convert a frequency into the x-axis on the spectrum or spectrogram
    // return -1 if not in current display range
    let xAxisValue = -1;

    let cfHz = this.getZoomCfHz();     // will be the same as unzoomed cf if not zoomed
    let spanHz = this.getZoomSpanHz(); // ditto
    let startFreqHz = cfHz - spanHz/2;
    let endFreqHz = cfHz + spanHz/2;

    if( (freqHz >= startFreqHz) || (freqHz <= endFreqHz) ) {
        // in the canvas window
        // how many Hz per x value
        let hzPerX = (endFreqHz - startFreqHz) / this.canvas.width;
        xAxisValue = (freqHz-startFreqHz) / hzPerX;
    }
    return parseInt(xAxisValue);
}

Spectrum.prototype.convertdBtoCanvasYOnSpectrum = function(db_value) {
    // as we can move the y axis around we need to be able to convert a dB value
    // to the correct y axis offset
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let range_db = this.max_db - this.min_db;
    let db_point = range_db / spectrum_height;
    let db_offset_from_top = this.max_db - db_value;
    let yaxis_cord = db_offset_from_top / db_point;
    if (yaxis_cord < 0) {
        yaxis_cord = 0;
    }
    return (parseInt(yaxis_cord));
}

Spectrum.prototype.convertSpectrogramCanvasRowToCurrentRow = function(row, inputCount) {
    // convert a markers row to the current row on the spectrogram
    let countDiff = this.inputCount - inputCount;
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let actualRow = row + countDiff;
    return (parseInt(actualRow));
}

Spectrum.prototype.convertInputCountToSpectrogramCanvasRow = function(inputCount) {
    let canvas_row = this.inputCount - inputCount;
    if (canvas_row >= this.wf_rows) {
        canvas_row = -1;
    }
    return canvas_row;
}

Spectrum.prototype.updateMarkers = function() {
    if (this.hideAllMarkers)
        return;

    this.updateLiveMarker();
    this.updateLockedMarker();
    this.updateIndexedMarkers();
}

Spectrum.prototype.updateLiveMarker = function() {
    if (!this.live_marker_on)
        return;

    if (!this.liveMarker)
        return;

    var context = this.canvas.getContext('2d');
    context.font = '12px sans-serif'; // if text px changed y offset for diff text has to be changed
    context.fillStyle = this.liveMarkerColour;
    context.textAlign = "left";

    // live marker lines
    let canvasX = this.convertFrequencyHzToCanvasX(this.liveMarker.freqHz);

    // vertical frequency marker
    this.ctx.beginPath();
    this.ctx.moveTo(canvasX, 0);
    this.ctx.lineTo(canvasX, this.canvas.height);
    this.ctx.setLineDash([10,10]);
    this.ctx.strokeStyle = this.liveMarkerColour;
    this.ctx.lineWidth = 1;
    this.ctx.stroke();

    // horizontal db marker on spectrum, or time in spectrogram
    let canvasY = 0;
    if(this.liveMarker.spectrum_flag) {
        canvasY = this.convertdBtoCanvasYOnSpectrum(this.liveMarker.power);  // spectrum
    } else {
        canvasY = this.liveMarker.spectrogram_canvas_y; // spectrogram
    }

    this.ctx.beginPath();
    this.ctx.moveTo(0, canvasY);
    this.ctx.lineTo(this.canvas.width, canvasY);
    this.ctx.setLineDash([10,10]);
    this.ctx.strokeStyle = this.liveMarkerColour;
    this.ctx.lineWidth = 1;
    this.ctx.stroke();
    this.ctx.setLineDash([]); // reset line style lest we forget

    context.fillStyle = this.liveMarkerColour

    let marker_value = this.getValuesAtCanvasPosition(canvasX, canvasY);
    if (typeof marker_value != 'undefined') {
        let marker_text = " " + this.convertFrequencyForDisplay(marker_value.freqHz, 3);

        if (typeof marker_value.power !== 'undefined') // TODO: fix undefined - but only on power, why?
            marker_text += " " + marker_value.power.toFixed(1) + "dB ";
        else {
            marker_text += " missing "; // may be fixed
            marker_value.power = 0;
        }

        marker_text += " " + marker_value.diffTime.toFixed(3) + "s ";

        // are we past half way, then put text on left
        if (canvasX > (this.canvas.clientWidth/2)) {
            context.textAlign = "right";
        } else {
            context.textAlign = "left";
        }
        context.fillText(marker_text, canvasX, 20);

        // Difference from the last indexed marker to the live marker
        if (this.markersSet.size > 0) {
            let mvalues = Array.from(this.markersSet);
            let last = mvalues[this.markersSet.size-1];
            let freq_diff = marker_value.freqHz - last.freqHz;
            let db_diff = marker_value.power - last.power;
            let time_diff = marker_value.diffTime - last.diffTime;

            let diff_text = " " + this.convertFrequencyForDisplay(freq_diff, 3);
            diff_text += " " + db_diff.toFixed(1) + "dB ";
            diff_text += " " + time_diff.toFixed(3) + "s ";
            context.fillText(diff_text, canvasX, 42);
        }
    }
}

Spectrum.prototype.updateLockedMarker = function() {
    // if we are locked to a spectrogram line while paused draw a line on the spectrogram
    if (this.paused && this.lockedSpectrogram) {
        this.ctx.beginPath();
        this.ctx.moveTo(0, this.lockedSpectrogramMarkerValues.spectrogram_canvas_y);
        this.ctx.lineTo(this.canvas.width, this.lockedSpectrogramMarkerValues.spectrogram_canvas_y);
        this.ctx.setLineDash([10,2,10]);
        this.ctx.strokeStyle = this.lockedSpectrumColour;
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
        this.ctx.setLineDash([]);
    }
}

Spectrum.prototype.updateIndexedMarkers = function() {
    if (this.markersSet.size == 0) {
        $('#theMarkerTable').hide();
        return;
    }
    $('#theMarkerTable').show();

    var context = this.canvas.getContext('2d');
    context.font = '12px sans-serif'; // if text px changed y offset for diff text has to be changed
    context.fillStyle = this.liveMarkerColour;
    context.textAlign = "left";

    // indexed marker lines and horizontal last marker if live marker on
    context.fillStyle = this.markersColour;
    let last_indexed_marker = this.markersSet.size -1;
    let current_index = 0;
    for (let item of this.markersSet) {
        let xpos = this.convertFrequencyHzToCanvasX(item.freqHz);
        if (item.visible && xpos >= 0) {
            this.ctx.beginPath();
            this.ctx.moveTo(xpos, 0);
            this.ctx.lineTo(xpos, this.canvas.height);
            this.ctx.strokeStyle = this.markersColour;
            this.ctx.lineWidth = 1;
            this.ctx.stroke();

            // spectrogram horizontal markers
            //if (!item.spectrumFlag) {
                let spectrogramRow = this.convertSpectrogramCanvasRowToCurrentRow(item.spectrogram_canvas_y, item.inputCount);
                this.ctx.beginPath();
                this.ctx.moveTo(0, spectrogramRow);
                this.ctx.lineTo(this.canvas.width, spectrogramRow);
                this.ctx.strokeStyle = this.markersColour;
                this.ctx.lineWidth = 1;
                this.ctx.stroke();
                context.fillText(current_index, this.canvas.width-15, spectrogramRow);
            //}

            // horizontal line to last indexed marker if live marker on
            if ( this.live_marker_on && (last_indexed_marker == current_index) ) {
                let y_pos = this.convertdBtoCanvasYOnSpectrum(item.power);
                this.ctx.beginPath();
                this.ctx.moveTo(0, y_pos);
                this.ctx.lineTo(this.canvas.width, y_pos);
                this.ctx.strokeStyle = this.markersColour;
                this.ctx.lineWidth = 1;
                this.ctx.stroke();

                // show the marker index on the right hand edge
                context.textAlign = "right";
                context.fillText(last_indexed_marker, this.canvas.width, y_pos);
            }
        }
        current_index += 1;
    }

    // markers text
    let marker_num=0;
    context.fillStyle = this.markersColour; //liveMarkerColour
    for (let item of this.markersSet) {
        if (item.visible) {
            let xpos = this.convertFrequencyHzToCanvasX(item.freqHz);
            if(xpos >= 0) {
                context.textAlign = "left";
                if (xpos > (this.canvas.clientWidth/2)) {
                    context.textAlign = "right";
                }
                // offset by 15 where we put text
                context.fillText(marker_num, xpos, 15);
            }
        }
        marker_num+=1;
    }
}
Spectrum.prototype.handleMouseWheel = function(evt) {
    let rect = this.canvas.getBoundingClientRect();
    let x_pos = evt.clientX - rect.left;
    let y_pos = evt.clientY - rect.top;
    let inSpectrum = this.inSpectrum(y_pos);
    let allowZoom = true;

    // Are we in spectrogram and paused then update the spectrum for this spectrogram row
    // note we will snap to the current mouse position if the mouse moves
    if ( !data_active || this.paused) {
        if (!inSpectrum) {
            allowZoom = false; // if we are paused and in the spectrogram then don't zoom

            // fine movement of selected spectrogram line on wheel changes
            if (evt.deltaY > 0) {
                this.spectrogramLiveMakerY += 1;
            } else if (evt.deltaY < 0) {
                this.spectrogramLiveMakerY -= 1;
            }
            this.updateLiveMarkerAtPosition(x_pos, this.spectrogramLiveMakerY);
        }
    }

    if (allowZoom) {
        // zoom the spectrum
        // fix centre on first zoom
        if (this.zoomCentreBin < 0) {
            this.zoomCentreBin = this.getSpectrumMarkerValues(x_pos, y_pos).bin;
        }
        // zooming or unzooming
        // powers of 2 keeps things in sync between spectrum and spectrogram as canvas and fft is power of 2
        if (evt.deltaY > 0){
            this.zoom /= 2.0;
        }
        else {
            this.zoom *= 2.0;
        }
        if (this.zoom <= 1.0) {
            this.zoom = 1.0;
            this.zoomCentreBin = -1;
            this.zoomStartBin = -1;
            this.zoomEndBin = -1;
        } else if ((this.fftSize / this.zoom) <= 64) {
            this.zoom /= 2.0; // put zoom back to have at least 128 points across
        }
        if(this.zoom > 1) {
            let bins = this.fftSize / this.zoom;
            this.zoomStartBin = this.zoomCentreBin - bins/2;
            this.zoomEndBin = this.zoomStartBin + bins;
        }
        this.updatedZoom = true;
    }
}

Spectrum.prototype.handleMouseMove = function(evt) {
    let rect = this.canvas.getBoundingClientRect();
    this.canvasX = evt.clientX - rect.left;
    this.canvasY = evt.clientY - rect.top;
    this.mouseInCanvas = true;
    // live maker is on
    if (this.live_marker_on) {
        this.spectrogramLiveMakerY = this.canvasY; // we may not be in the spectrogram though
        this.updateLiveMarkerAtPosition(this.canvasX, this.canvasY);
    }
}
Spectrum.prototype.handleMouseOut = function(evt) {
    this.mouseInCanvas = false;
}

Spectrum.prototype.updateSpectrogramLock = function() {
    if (this.paused && this.mouseInCanvas && !this.inSpectrum(this.canvasY)) {
        this.lockedSpectrogram = !this.lockedSpectrogram;
        if (this.lockedSpectrogram) {
            // allow for wheel correction, so don't use canvasY
            this.lockedSpectrogramMarkerValues = this.getValuesAtCanvasPosition(this.canvasX,
                                                    this.spectrogramLiveMakerY, this.canvas.width);
            this.liveMarker = this.lockedSpectrogramMarkerValues;
            if (this.lockedSpectrogramMarkerValues.magnitudes) {
                this.currentMagnitudes = this.lockedSpectrogramMarkerValues.magnitudes; // will update the spectrum display
            }
            this.lockedSpectrogramIndex = this.getSpectrogramArrayIndex(this.spectrogramLiveMakerY);
        } else {
            this.lockedSpectrogramIndex = null;
            this.lockedSpectrogramMarkerValues = undefined;
        }
        this.updateWhenPaused();
    }
}

Spectrum.prototype.updateLiveMarkerAtPosition = function(x_pos, y_pos) {
    let values = this.getValuesAtCanvasPosition(x_pos, y_pos, this.canvas.width);
    if (typeof values == 'undefined') {
        return;
    }
    if (this.inSpectrum(y_pos)) {
        this.liveMarker = values;
    } else {
        // in spectrogram
        if (!data_active || this.paused) {
            if (!this.lockedSpectrogram) {
                // not locked to a row
                this.liveMarker = values;
                if (values.magnitudes) {
                    this.currentMagnitudes = values.magnitudes;
                }
            }
        } else {
            // not paused
            this.liveMarker = values;
        }
    }
}

Spectrum.prototype.handleLeftMouseClick = function(evt) {
    // limit the number of markers
    if (this.markersSet.size < this.maxNumMarkers) {
        let rect = this.canvas.getBoundingClientRect();
        let x_pos = evt.clientX - rect.left;
        let y_pos = evt.clientY - rect.top;

        // if in spectrogram and mouse wheel has moved the live marker then use
        // that as the y position instead
        if ( this.live_marker_on && !this.inSpectrum(y_pos) ) {
            y_pos = this.spectrogramLiveMakerY;
        }

        let values = this.getValuesAtCanvasPosition(x_pos, y_pos);

        if (typeof values !== 'undefined') {
            this.addMarker(values.freqHz, values.power, values.diffTime,
                values.spectrogram_canvas_y, this.inputCount, values.spectrum_flag);
            // allow markers to be added even when connection down
            if (!data_active){
                this.updateWhenPaused();
            }
        }
    }
}

Spectrum.prototype.resetZoom = function() {
    this.zoom = 1.0;
    this.zoomCentreBin = -1;
    this.updatedZoom = true;
}

Spectrum.prototype.convertFrequencyForDisplay = function(freqHz, decimalPoints) {
    // take in a Hz frequency and convert it to meaningful Hz,kHz,MHz,GHz
    let displayValue = "";
    let dec = parseInt(decimalPoints);
    let modFreq = Math.abs(freqHz);
    if (modFreq < 1.0e3){
        displayValue = freqHz.toFixed(dec)+"Hz ";
    }else if (modFreq < 1.0e6){
        displayValue = (freqHz / 1e3).toFixed(dec)+"kHz ";
    }else if (modFreq < 1.0e9){
        displayValue = (freqHz / 1e6).toFixed(dec)+"MHz ";
    }else {
        displayValue = (freqHz / 1e9).toFixed(dec)+"GHz ";
    }

    return displayValue;
}

Spectrum.prototype.inSpectrum = function(y_pos) {
    // true if we are in the spectrum part of the canvas
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    if (y_pos <= spectrum_height) {
        return true;
    }
    return false;
}

Spectrum.prototype.getZoomCfHz = function() {
    let zoomCfHz = this.centreHz;
    if (this.zoomCentreBin >= 0) {
         zoomCfHz = this.convertFftBinToFrequency(this.zoomCentreBin);
    }
    return zoomCfHz;
}

Spectrum.prototype.getZoomSpanHz = function() {
    return this.spanHz / this.zoom;;
}

Spectrum.prototype.getValuesAtCanvasPosition = function(xpos, ypos) {
    // get signal frequency and dB values for the given canvas position
    if(this.inSpectrum(ypos) ) {
        return this.getSpectrumMarkerValues(xpos, ypos);
    }
    return this.getSpectrogramMarkerValues(xpos, ypos);
}

Spectrum.prototype.getSpectrumMarkerValues = function(xpos, ypos) {
     // even when locked to a spectrogram row the xpos will still give valid values for these two
    let freq_value = this.convertCanvasXToFrequencyHz(xpos); // may be out of range
    let bin_index = this.convertFrequencyToFftBin(freq_value);

     // bomb out now if we are off the array
    if((bin_index<0) || (bin_index >= this.fftSize)) {
        return undefined;
    }

    let signal_db = 0.0; // to be found
    let time_value = this.currentTime - this.firstTime; // i.e. now but relative
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let spectrogram_canvas_y = spectrum_height; // current spectrum is first spectrogram row (unless paused !)

    if (this.lockedSpectrogram) {
        let spectrum = this.spectrums[this.lockedSpectrogramIndex];
        signal_db = spectrum.magnitudes[0][bin_index];
        // update the time
        let t =  spectrum.start_sec;
        t += spectrum.start_nsec/1e9;
        time_value =  t - this.firstTime;

        // need y position on the spectrogram canvas for this spectrum
        spectrogram_canvas_y = spectrum_height +
                this.convertInputCountToSpectrogramCanvasRow(spectrum.inputCount);
    } else {
        if (this.binsMax) {
            signal_db = this.binsMax[bin_index];      // if in max hold then get that power
        } else if (this.averaging > 0 ) {
            signal_db = this.binsAverage[bin_index];  // or average
        } else {
            signal_db = this.currentMagnitudes[bin_index]; // or current
        }
    }

    // return the frequency in Hz, the power and where we are on the display
    return {
          freqHz: freq_value,
          spectrum_flag: true,
          power: signal_db,
          diffTime: time_value,
          spectrogram_canvas_y: spectrogram_canvas_y,
          bin: bin_index,
          spectrum: this.currentSpectrum,
          magnitudes: this.currentMagnitudes
    };
}

Spectrum.prototype.getSpectrogramMarkerValues = function(xpos, ypos) {
    let freq_value = this.convertCanvasXToFrequencyHz(xpos); // may be out of range
    let bin_index = this.convertFrequencyToFftBin(freq_value);

     // bomb out now if we are off the array
    if((bin_index<0) || (bin_index >= this.fftSize)) {
        return undefined;
    }

    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let spectrogram_height = this.canvas.height * (1.0-(this.spectrumPercent/100));

    let signal_db = 0.0;
    let time_value = 0.0;
    let mags = undefined;
    let spectrogram_array_index = this.getSpectrogramArrayIndex(ypos);

    // find signal_db and time
    let spec = undefined;
    if ( (spectrogram_array_index >= 0) && (spectrogram_array_index < this.spectrums.length)) {
        spec = this.spectrums[spectrogram_array_index];
        if (spec) {
            mags = spec.magnitudes[0];
            if(mags) {
                if (bin_index < mags.length) {
                    signal_db = mags[bin_index];
                }
            }
            time_value = spec.start_sec - this.firstTime + (spec.start_nsec/1e9); // relative to start of run
        }
    }

    // if we don't have magnitudes then we are in the spectrogram display but the row is not yet filled
    if (!mags) {
        return undefined;
    }

    // return details of the row
    return {
          freqHz: freq_value,
          spectrum_flag: false,
          power: signal_db,
          diffTime: time_value,
          spectrogram_canvas_y: ypos, // TODO: remove, only used for keeping track of scrolling on spectrogram
          bin: bin_index,
          spectrum: spec,
          magnitudes: mags
    };
}

Spectrum.prototype.getSpectrogramArrayIndex = function(ypos) {
    // where are we in the rows, ypos != row

    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let spectrogram_height = this.canvas.height * (1.0-(this.spectrumPercent/100));
    let row_per_canvas_row = this.spectrums.length / spectrogram_height;
    // where do we think we are from the top, yes spectrum_height
    let actual_spectrogram_row = ypos - spectrum_height;
    let spectrogram_row =  0;
    if (row_per_canvas_row < 1.0) {
        // spectrogram is adding lines
        spectrogram_row = parseInt(actual_spectrogram_row * row_per_canvas_row);
    } else {
        // spectrogram canvas shows actual rows
        spectrogram_row = parseInt(actual_spectrogram_row);
    }

    // because the display scrolls and our array does not we must modify the array index
    let spectrogram_array_index = 0;
    spectrogram_array_index = this.inputCount - spectrogram_row;
    spectrogram_array_index = spectrogram_array_index % this.spectrums.length;

    return spectrogram_array_index;
}

function Spectrum(id, options) {
    // Handle options
    this.centreHz = (options && options.centreHz) ? options.centreHz : 0;
    this.spanHz = (options && options.spanHz) ? options.spanHz : 0;
    this.wf_size = (options && options.wf_size) ? options.wf_size : 0;
    this.wf_rows = (options && options.wf_rows) ? options.wf_rows : 256;
    this.spectrumPercent = (options && options.spectrumPercent) ? options.spectrumPercent : 50;
    this.spectrumPercentStep = (options && options.spectrumPercentStep) ? options.spectrumPercentStep : 5;
    this.averaging = (options && options.averaging) ? options.averaging : 0;
    this.maxHold = (options && options.maxHold) ? options.maxHold : false;

    // useful values
    this.sps = 0;
    this.fftSize = 0;
    this.updatedAveraging = false;

    // markers
    this.markersSet = new Set();
    this.liveMarker = undefined;
    this.live_marker_on = false;
    this.live_peak_search = false;

    this.maxNumMarkers = 16;
    this.hideAllMarkers = false; // true would require updating the button
    this.firstTime = 0;          // set to time of first spectrum so we can do relative to the start of the run
    this.currentTime = 0;        // the most recent time we have, not updated when paused
    this.oldestTime = 0;         // the oldest timestamp we have in the spectrums

    // copies of the data that went to the canvas, allows replay when paused or disconnected
    this.spectrums = new Array(this.wf_rows); // copy of all fft data in spectrogram along with times
    this.spectrumsIndex = 0;

    this.currentMagnitudes = null; // copy of just the current fft data for use when disconnected or paused
    this.currentSpectrum = null;   // as above but also includes times etc
    this.binsMax = undefined;      // only present when max hold on

    // one up count of all spectrums received when not paused
    this.inputCount = 0;

    // Setup state
    this.paused = false;
    this.fullscreen = false;
    this.min_db = -80;
    this.max_db = 20;
    this.spectrumHeight = 0;
    
    // when paused we can lock to a particular spectrogram row
    this.lockedSpectrogram = false;                 // are we locked to a row
    this.lockedSpectrogramIndex = null;             // index into the spectrums[] when we are locked to a row
    this.lockedSpectrogramMarkerValues = undefined; // the marker values for the locked row

    // mouse position, as we need to know this for some events
    this.canvasX = 0;
    this.canvasY = 0;
    this.spectrogramLiveMakerY = 0;  // for the scroll wheel moving the spectrogram row away from the mouse position
    this.mouseInCanvas = false;

    // zoom
    this.zoom = 1.0;
    this.zoomCentreBin = -1;
    this.zoomStartBin = -1;
    this.zoomEndBin = -1;
    this.updatedZoom = false;

    // Colours
    this.colourindex = 0;
    this.colourmap = colourmaps[0]; // map for spectrogram only
    this.liveMarkerColour = "black";
    this.lockedSpectrumColour = "black"
    this.markersColour = "red";
    this.backgroundColour = "white";
    this.maxHoldColour = "green";
    this.magnitudesColour = "blue";
    this.canvasTextColour = "black";
    this.spectrumGradient = false;

    // Create main canvas and adjust dimensions to match actual
    this.canvas = document.getElementById(id);
    this.canvas.height = this.canvas.clientHeight;
    this.canvas.width = this.canvas.clientWidth;
    this.ctx = this.canvas.getContext("2d");
    this.ctx.fillStyle = this.backgroundColour;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // Create off screen canvas for axes
    this.axes = document.createElement("canvas");
    this.axes.height = 1; // Updated later
    this.axes.width = this.canvas.width;
    this.ctx_axes = this.axes.getContext("2d");

    // Create off screen canvas for waterfall
    this.wf = document.createElement("canvas");
    this.wf.height = this.wf_rows;
    this.wf.width = this.wf_size;
    this.ctx_wf = this.wf.getContext("2d");

    // Trigger first render
    this.setAveraging(this.averaging);
    this.updateSpectrumRatio();
    this.resize();
}
