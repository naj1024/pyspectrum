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
    for (var i = 0; i < this.imagedata.data.length; i += 4) {
        var cindex = this.squeeze(bins[i/4], 0, 255);
        var color = this.colormap[cindex];
        this.imagedata.data[i+0] = color[0];
        this.imagedata.data[i+1] = color[1];
        this.imagedata.data[i+2] = color[2];
        this.imagedata.data[i+3] = 255;
    }
}

Spectrum.prototype.drawWaterfall = function() {
    // redraw the current waterfall
    var width = this.ctx.canvas.width;
    var height = this.ctx.canvas.height;

    // Copy scaled FFT canvas to screen. Only copy the number of rows that will
    // fit in waterfall area to avoid vertical scaling.
    //this.ctx.imageSmoothingEnabled = false;
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
    if(bins!=undefined) {
        this.ctx.beginPath();
        this.ctx.moveTo(-1, this.spectrumHeight + 1);
        for (var i = 0; i < bins.length; i++) {
            var y = this.spectrumHeight - this.squeeze(bins[i], 0, this.spectrumHeight);
            if (y > this.spectrumHeight - 1)
                y = this.spectrumHeight + 1; // Hide underflow
            if (y < 0)
                y = 0;
            if (i == 0)
                this.ctx.lineTo(-1, y);
            this.ctx.lineTo(i, y);
            if (i == bins.length - 1)
                this.ctx.lineTo(this.wf_size + 1, y);
        }
        this.ctx.lineTo(this.wf_size + 1, this.spectrumHeight + 1);
        this.ctx.strokeStyle = colour;
        this.ctx.stroke();
    }
}

Spectrum.prototype.drawSpectrum = function(bins) {
    var width = this.ctx.canvas.width;
    var height = this.ctx.canvas.height;

    // Fill with canvas
    this.ctx.fillStyle = this.backgroundColour;
    this.ctx.fillRect(0, 0, width, height);

    // bounding box around canvas
    this.ctx.beginPath();
    this.ctx.moveTo(0, 0);
    this.ctx.lineTo(width, 0);
    this.ctx.lineTo(width, height);
    this.ctx.lineTo(0, height);
    this.ctx.lineTo(0, 0);
    this.ctx.strokeStyle = "black";
    this.ctx.stroke();

    if (!this.paused) {
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
        this.ctx_axes.stroke();
    }

    this.ctx_axes.textBaseline = "bottom";
    // Frequency labels on x-axis
    for (var i = 0; i < 11; i++) {
        var x = Math.round(width / 10) * i;
        // mod 5 to give just the first,middle and last - small screens don't handle lots of marker values
        if ((i%5) == 0) {
            if (this.spanHz > 0) {
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

                var freq = this.centerHz + this.spanHz / 10 * (i - 5);
                if (this.centerHz + this.spanHz > 1e9){
                    freq = freq / 1e9;
                    freq = freq.toFixed(3) + "G";
                }
                else if (this.centerHz + this.spanHz > 1e6){
                    freq = freq / 1e6;
                    freq = freq.toFixed(3) + "M";
                }
                else if (this.centerHz + this.spanHz > 1e3){
                    freq = freq / 1e3;
                    freq = freq.toFixed(3) + "k";
                }
                this.ctx_axes.fillText(freq, x + adjust, height - 3);
            }
        }

        this.ctx_axes.beginPath();
        this.ctx_axes.moveTo(x, 0);
        this.ctx_axes.lineTo(x, height);
        this.ctx_axes.strokeStyle = "rgba(200, 200, 200, 0.40)";
        this.ctx_axes.stroke();
    }
}

Spectrum.prototype.addData = function(peaks, start_sec, start_nsec, end_sec, end_nsec) {
    if (!this.paused) {
        // remember the data so we can pause and still use markers
        // start times are for the first mag we peak detected on between updates
        // end times are for the last mag we peak detected on to give the peaks
        // start and end times can be the same
        this.peaks = peaks;    // peak magnitudes between updates

        // magnitudes are from a single fft, peaks are from all the fft magnitudes since the last update
        // both magnitudes and peaks are same length
        if (peaks.length != this.wf_size) {
            this.wf_size = peaks.length;
            this.ctx_wf.canvas.width = peaks.length;
            //this.ctx_wf.fillStyle = this.backgroundColour;
            //this.ctx_wf.fillRect(0, 0, this.wf.width, this.wf.height);
            this.imagedata = this.ctx_wf.createImageData(peaks.length, 1);
        }
        this.drawSpectrum(peaks);
        this.addWaterfallRow(peaks);

        this.updateMarkers();
        this.resize();
    } else {
        this.updateWhenPaused();
    }
}

Spectrum.prototype.updateWhenPaused = function() {
    // keep things as they are but allow markers to work
    this.drawSpectrum(this.peaks);
    this.drawWaterfall();
    this.updateMarkers();
    this.resize();
}

Spectrum.prototype.updateSpectrumRatio = function() {
    this.spectrumHeight = Math.round(this.canvas.height * this.spectrumPercent / 100.0);

    this.gradient = this.ctx.createLinearGradient(0, 0, 0, this.spectrumHeight);
    for (var i = 0; i < this.colormap.length; i++) {
        var c = this.colormap[this.colormap.length - 1 - i];
        this.gradient.addColorStop(i / this.colormap.length,
            "rgba(" + c[0] + "," + c[1] + "," + c[2] + ", 1.0)");
    }
}

Spectrum.prototype.resize = function() {
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

Spectrum.prototype.toggleColor = function() {
    this.colorindex++;
    if (this.colorindex >= colormaps.length)
        this.colorindex = 0;
    this.colormap = colormaps[this.colorindex];
    this.updateSpectrumRatio();
}

Spectrum.prototype.setRange = function(min_db, max_db) {
    this.min_db = min_db;
    this.max_db = max_db;
    this.updateAxes();
}

Spectrum.prototype.rangeUp = function() {
    this.setRange(this.min_db - 5, this.max_db - 5);
}

Spectrum.prototype.rangeDown = function() {
    this.setRange(this.min_db + 5, this.max_db + 5);
}

Spectrum.prototype.rangeIncrease = function() {
    this.setRange(this.min_db - 5, this.max_db + 5);
}

Spectrum.prototype.rangeDecrease = function() {
    if (this.max_db - this.min_db > 10)
        this.setRange(this.min_db + 5, this.max_db - 5);
}

Spectrum.prototype.setCenterHz = function(Hz) {
    this.centerHz = Hz;
    this.updateAxes();
}

Spectrum.prototype.setCenterMHz = function(MHz) {
    this.centerHz = Math.trunc(MHz * 1e6);
    this.updateAxes();
}

Spectrum.prototype.setSpanHz = function(hz) {
    this.spanHz = hz;
    this.updateAxes();
}

Spectrum.prototype.setAveraging = function(num) {
    if (num >= 0) {
        this.averaging = num;
        this.alpha = 2 / (this.averaging + 1)
    }
}

Spectrum.prototype.incrementAveraging = function() {
    this.setAveraging(this.averaging + 1);
}

Spectrum.prototype.decrementAveraging = function() {
    if (this.averaging > 0) {
        this.setAveraging(this.averaging - 1);
    }
}

Spectrum.prototype.setPaused = function(paused) {
    this.paused = paused;
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
    if (e.key == "f") {
        this.toggleFullscreen();
    } else if (e.key == "c") {
        this.toggleColor();
    } else if (e.key == "+") {
        this.incrementAveraging();
    } else if (e.key == "-") {
        this.decrementAveraging();
    } else if (e.key == "m") {
        this.toggleMaxHold();
        $("#maxHoldBut").button('toggle'); // update the UI button state
    } else if (e.key == "l") {
        this.toggleLive();
        $("#peakBut").button('toggle'); // update the UI button state
    } else if (e.key == "p") {
        this.togglePaused();
        $("#pauseBut").button('toggle'); // update the UI button state
    } else if (e.key == "ArrowUp") {
        this.rangeUp();
    } else if (e.key == "ArrowDown") {
        this.rangeDown();
    } else if (e.key == "ArrowLeft") {
        this.rangeDecrease();
    } else if (e.key == "ArrowRight") {
        this.rangeIncrease();
     } else if (e.key == "s") {
        this.incrementSpectrumPercent();
    } else if (e.key == "w") {
        this.decrementSpectrumPercent();
    }
}

Spectrum.prototype.addMarkerMHz = function(frequencyMHz, magdB, x_pos, y_pos) {
    // show markers if we are adding markers
    if (this.hideAllMarkers){
        this.hideAllMarkers = false;
        $("#hideMarkersBut").button('toggle'); // update the UI button state
    }

    let marker = {};
    marker['xpos'] = parseInt(x_pos);
    marker['ypos'] = parseInt(y_pos);
    marker['freqMHz'] = frequencyMHz;
    marker['db'] = magdB;
    marker['visible'] = true;

    let delta = 0;
    if (this.markersSet.size != 0){
        let as_array = Array.from(this.markersSet);
        let previous_marker = as_array[this.markersSet.size-1];
        delta = (frequencyMHz - previous_marker.freqMHz).toFixed(3);
    }
    // do we have this one already, note .has(marker) doesn't work
    let new_entry = true;
    for (let item of this.markersSet) {
        if (item.xpos == marker.xpos){
            new_entry = false;
        }
    }
    if (new_entry) {
        this.markersSet.add(marker);
        let number = this.markersSet.size-1;
        let marker_id = "marker_" + number;

        // add to table of markers
        let new_row="<tr>";

        // marker number and checkbox
        new_row += '<td>';
        new_row += '<input type="checkbox" checked="true" id="'+marker_id+'"> ';
        new_row += '<label for="'+marker_id+'"> '+number+'</label>';
        new_row += '</div>';
        new_row += '</td>';

        // data
        new_row += "<td>"+frequencyMHz+"</td>";
        new_row += "<td>"+magdB+"</td>";
        new_row += "<td>"+0.0+"</td>";
        new_row += "<td>"+delta+"</td>";

        new_row += "</tr>";
        $('#marker_table').append(new_row);

        // todo: had to use a global, can't work out how to get hold of this'
        $('#'+marker_id).click(function() {spectrum.markerCheckBox(number);});
    }
}

Spectrum.prototype.markerCheckBox = function(id) {
    // toggle visible - bit open loop, TODO: better to have the state of the tick box
    let marker_num = 0;
    for (let item of this.markersSet) {
        if (id == marker_num) {
            item.visible = ! item.visible;
            break;
        }
        marker_num+=1;
    }
}

Spectrum.prototype.liveMarkerOn = function() {
    if (this.live_marker_type == 0) {
        this.live_marker_type = 4;
    } else {
        this.live_marker_type = 0;
        this.liveMarker = undefined;
        if (!data_active) {
            this.updateWhenPaused();
        }
    }
}

Spectrum.prototype.clearMarkers = function() {
    // clear the table
    //  $(this).parents("tr").remove();
    let num_rows=this.markersSet.size;
    for (let i=num_rows; i>0; i--) {
        $("#marker_table tr:eq("+i+")").remove(); //to delete row 'i', delrowId should be i+1
    }
    this.markersSet.clear();
    this.liveMarker = undefined;
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.clearUncheckedMarkers =  function() {
    let oldMarkers = new Set(this.markersSet);
    this.clearMarkers();
    for (let item of oldMarkers) {
        if (item.visible == true) {
            this.addMarkerMHz(item.freqMHz, item.db, item.xpos, item.ypos)
        }
    }
}

Spectrum.prototype.hideMarkers = function() {
    this.hideAllMarkers = !this.hideAllMarkers;
    if (!data_active){
        this.updateWhenPaused();
    }
}

Spectrum.prototype.convertdBtoY = function(db_value) {
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

// writeMarkers
Spectrum.prototype.updateMarkers = function() {
    // TODO: refactor this function

    if (this.hideAllMarkers)
        return;

    let width = this.ctx.canvas.width;
    let height = this.ctx.canvas.height;
    var context = this.canvas.getContext('2d');
    context.font = '12px sans-serif'; // if text px changed y offset for diff text has to be changed
    context.fillStyle = this.liveMarkerColour;
    context.textAlign = "left";

    // live marker lines
    if ((this.live_marker_type > 0) && this.liveMarker){
        // what kind of marker
        // 0 - none
        // 1 - frequency (vertical)
        // 2 - frequency + power/time (vertical and horizontal

        // vertical frequency marker
        if(this.live_marker_type & 1) {
            this.ctx.beginPath();
            this.ctx.moveTo(this.liveMarker.x, 0);
            this.ctx.lineTo(this.liveMarker.x, height);
            this.ctx.setLineDash([10,10]);
            this.ctx.strokeStyle = this.liveMarkerColour;
            this.ctx.stroke();
        }
        // horizontal db marker on spectrum, or time in spectrogram
        if((this.live_marker_type & 2) && this.liveMarker.spectrum_flag) {
            let y_pos = this.convertdBtoY(this.liveMarker.power);
            this.ctx.beginPath();
            this.ctx.moveTo(0, y_pos);
            this.ctx.lineTo(width, y_pos);
            this.ctx.setLineDash([10,10]);
            this.ctx.strokeStyle = this.liveMarkerColour;
            this.ctx.stroke();
        }
        // triangular marker on spectrum, or time in spectrogram
        if((this.live_marker_type & 4) && this.liveMarker.spectrum_flag) {
            let y_pos = this.convertdBtoY(this.liveMarker.power);
            this.ctx.beginPath();
            this.ctx.moveTo(this.liveMarker.x-5, y_pos-5);
            this.ctx.lineTo(this.liveMarker.x+5, y_pos-5);
            this.ctx.lineTo(this.liveMarker.x, y_pos);
            this.ctx.lineTo(this.liveMarker.x-5, y_pos-5);
            this.ctx.setLineDash([]);
            this.ctx.strokeStyle = this.liveMarkerColour;
            this.ctx.stroke();
        }
    }
    // reset line style lest we forget
    this.ctx.setLineDash([]);

    // indexed marker lines and horizontal last marker if live marker on
    context.fillStyle = this.markersColour;
    if (this.markersSet) {
        let last_indexed_marker = this.markersSet.size -1;
        let current_index = 0;
        for (let item of this.markersSet) {
            if (item.visible) {
                let xpos = item.xpos;
                let height = this.ctx.canvas.height;
                this.ctx.beginPath();
                this.ctx.moveTo(xpos, 0);
                this.ctx.lineTo(xpos, height);
                this.ctx.strokeStyle = this.markersColour;
                this.ctx.stroke();

                // horizontal line to last indexed marker if live marker on
                if ( (this.live_marker_type > 0) && (last_indexed_marker==current_index) ) {
                    let y_pos = this.convertdBtoY(item.db);
                    this.ctx.beginPath();
                    this.ctx.moveTo(0, y_pos);
                    this.ctx.lineTo(width, y_pos);
                    this.ctx.strokeStyle = this.markersColour;
                    this.ctx.stroke();

                    // show the marker index on the right hand edge
                    context.textAlign = "right";
                    context.fillText(last_indexed_marker, width, y_pos);
                }
            }
            current_index += 1;
        }
    }

    // live marker text
    context.fillStyle = this.liveMarkerColour
    if ((this.live_marker_type > 0) && this.liveMarker) {
        // update the value, so we get a live update
        let marker_value = this.getValues(this.liveMarker.x, this.liveMarker.y, this.liveMarker.width);
        if (marker_value) {
            let marker_text = "";
            // live_marker_type bit fields 0=off, 1=freq, 2=level/time, 4=triangle
            // bit display
            //  0  Freq
            //  1  Power/time
            //  2  Freq + Power/time
            let both = true;
            if (this.live_marker_type == 2 ) {
                both = false;
            }
            if (this.liveMarker.spectrum_flag) {
                // in spectrum
                if (both) {
                    marker_text = " " + this.convertFrequencyForDisplay(marker_value.freq, 3);
                    marker_text += " " + marker_value.power.toFixed(1) + "dB ";
                } else {
                    marker_text = " " + marker_value.power.toFixed(1) + "dB ";
                }
            } else {
                // in spectrogram
                if (both) {
                    marker_text = " " + this.convertFrequencyForDisplay(marker_value.freq, 3);
                    marker_text += " " + marker_value.time.toFixed(3) + "s ";
                } else {
                    marker_text = " " + marker_value.time.toFixed(3) + "s ";
                }
            }

            // are we past half way, then put text on left
            if (this.liveMarker.x > (this.canvas.clientWidth/2)) {
                context.textAlign = "right";
            } else {
                context.textAlign = "left";
            }
            context.fillText(marker_text, this.liveMarker.x, 30); //this.liveMarker.y);

            // Now if we have a set marker we also show the difference to the live marker
            // TODO handle non visible last marker
            if (this.markersSet.size > 0) {
                let mvalues = Array.from(this.markersSet);
                let last = mvalues[this.markersSet.size-1];
                let freq_diff = marker_value.freq - last.freqMHz*1e6;
                let db_diff = marker_value.power - last.db;
                let time_diff = marker_value.time - last.time;

                let diff_text="";
                if (this.liveMarker.spectrum_flag) {
                    // in spectrum
                    if (both) {
                        diff_text = " " + this.convertFrequencyForDisplay(freq_diff, 3);
                        diff_text += " " + db_diff.toFixed(1) + "dB ";
                    } else {
                        diff_text = " " + db_diff.toFixed(1) + "dB ";
                    }
                } else {
                    // in spectrogram
                    if (both) {
                        diff_text = " " + this.convertFrequencyForDisplay(freq_diff, 3);
                        diff_text += " " + db_diff.toFixed(3) + "s ";
                    } else {
                        diff_text = " " + time_diff.toFixed(3) + "s ";
                    }
                }
                context.fillText(diff_text, this.liveMarker.x, 42); //this.liveMarker.y+12); // 12px text
            }
        }
    }

    // indexed markers text
    let marker_num=0;
    context.fillStyle = this.markersColour; //liveMarkerColour
    for (let item of this.markersSet) {
        if (item.visible) {
            let xpos = item.xpos;
            context.textAlign = "left";
            if (xpos > (this.canvas.clientWidth/2)) {
                context.textAlign = "right";
            }
            context.fillText(marker_num, xpos, 15);
        }
        marker_num+=1;
    }
}


Spectrum.prototype.handleMouseWheel = function(evt){
    // only change range if in spectrum
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let rect = this.canvas.getBoundingClientRect();
    let y_pos = evt.clientY - rect.top;

    if (y_pos <= spectrum_height) {
        if (evt.buttons ==0) {
            if (evt.deltaY > 0){
                this.rangeUp();
            }
            else{
                this.rangeDown();
            }
        } else if(evt.buttons == 4) {
            if (evt.deltaY > 0){
                this.rangeIncrease();
            }
            else{
                this.rangeDecrease();
            }
        }
    }
}

Spectrum.prototype.handleMouseMove = function(evt) {
    if (this.live_marker_type > 0) {
        let rect = this.canvas.getBoundingClientRect();
        let x_pos = evt.clientX - rect.left;
        let y_pos = evt.clientY - rect.top;
        let width = rect.width;

        let values = this.getValues(x_pos, y_pos, width);
        if (values) {
            this.liveMarker = values;
        }
    }
}

Spectrum.prototype.handleLeftMouseClick = function(evt) {
    let rect = this.canvas.getBoundingClientRect();
    let x_pos = evt.clientX - rect.left;
    let y_pos = evt.clientY - rect.top;
    let width = rect.width;

    let values = this.getValues(x_pos, y_pos, width);
    if (values){
        // limit the number of markers
        if (this.markersSet.size < this.maxNumMarkers){
            this.addMarkerMHz((values.freq / 1e6).toFixed(3), values.power.toFixed(1), values.x, values.y);
            // allow markers ot be added even when we are receiving no data
            if (!data_active){
                this.updateWhenPaused();
            }
        }
    }
}

Spectrum.prototype.handleRightMouseClick = function(evt) {
    // change the type of live marker line
    if (this.live_marker_type == 0) {
        this.live_marker_type = 4;
        $("#liveMarkerBut").button('toggle'); // update the UI button state
    } else {
        this.live_marker_type -= 1;
        if(this.live_marker_type < 1) {
            this.live_marker_type = 0;
            $("#liveMarkerBut").button('toggle'); // update the UI button state
        }
    }
}

Spectrum.prototype.convertFrequencyForDisplay = function(freq, decimalPoints){
    // take in a Hz frequency and convert it to meaningful Hz,kHz,MHz,GHz
    let displayValue = "";
    let dec = parseInt(decimalPoints);
    let modFreq = Math.abs(freq);
    if (modFreq < 1.0e3){
        displayValue = freq.toFixed(dec)+"Hz ";
    }else if (modFreq < 1.0e6){
        displayValue = (freq / 1e3).toFixed(dec)+"kHz ";
    }else if (modFreq < 1.0e9){
        displayValue = (freq / 1e6).toFixed(dec)+"MHz ";
    }else {
        displayValue = (freq / 1e9).toFixed(dec)+"GHz ";
    }

    return displayValue;
}

Spectrum.prototype.getValues = function(xpos, ypos, width) {
    // get signal frequency and dB values for the given canvas position

    if(!this.peaks)
        return undefined;

    let per_hz = this.spanHz / width;
    let freq_value = (this.centerHz - (this.spanHz / 2)) + (xpos * per_hz);

    // dB value where the mouse pointer is and also signal dB
    let spectrum_height = this.canvas.height * (this.spectrumPercent/100);
    let mouse_power_db = 0.0;
    let signal_db = 0.0;
    let spectrum_flag = false;  // are we in spectrum or spectrogram
    let time_value = 0.0;
    if (ypos <= spectrum_height) {
        spectrum_flag = true;
        let range_db = this.max_db - this.min_db;
        let db_point = range_db / spectrum_height;
        mouse_power_db = this.max_db - (ypos * db_point);

        // signal related, where are we in the array of powers
        let pwr_index = xpos * this.peaks.length / width;

        // if in max hold then return that power otherwise eithe mags or peaks
        if (this.binsMax) {
            signal_db = this.binsMax[parseInt(pwr_index)];
       }else {
            signal_db = this.peaks[parseInt(pwr_index)];
        }
        // console.log("pwr "+xpos+" "+pwr_index+" "+mouse_power_db+" "+signal_db+" ");
    } else {
        time_value = ypos - spectrum_height;
    }

    // return the frequency in Hz, the power and where we are on the display
    return {
          freq: freq_value,
          spectrum_flag: spectrum_flag,
          power: signal_db,
          time: time_value,
          x: xpos,
          y: ypos,
          width: width
    };
}

function Spectrum(id, options) {
    // Handle options
    this.centerHz = (options && options.centerHz) ? options.centerHz : 0;
    this.spanHz = (options && options.spanHz) ? options.spanHz : 0;
    this.wf_size = (options && options.wf_size) ? options.wf_size : 0;
    this.wf_rows = (options && options.wf_rows) ? options.wf_rows : 2048;
    this.spectrumPercent = (options && options.spectrumPercent) ? options.spectrumPercent : 25;
    this.spectrumPercentStep = (options && options.spectrumPercentStep) ? options.spectrumPercentStep : 5;
    this.averaging = (options && options.averaging) ? options.averaging : 0;
    this.maxHold = (options && options.maxHold) ? options.maxHold : false;

    // markers
    this.markersSet = new Set();
    this.liveMarker = undefined;
    this.live_marker_type = 0;  // bit fields 0=off, 1=freq, 2=level/time, 4=triangle
    this.maxNumMarkers = 16;
    this.hideAllMarkers = false;

    // Setup state
    this.paused = false;
    this.fullscreen = false;
    this.min_db = -80;
    this.max_db = 20;
    this.spectrumHeight = 0;

    // Colors
    this.colorindex = 0;
    this.colormap = colormaps[0];
    this.liveMarkerColour = "black";
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

    // Create offscreen canvas for axes
    this.axes = document.createElement("canvas");
    this.axes.height = 1; // Updated later
    this.axes.width = this.canvas.width;
    this.ctx_axes = this.axes.getContext("2d");

    // Create offscreen canvas for waterfall
    this.wf = document.createElement("canvas");
    this.wf.height = this.wf_rows;
    this.wf.width = this.wf_size;
    this.ctx_wf = this.wf.getContext("2d");

    // Trigger first render
    this.setAveraging(this.averaging);
    this.updateSpectrumRatio();
    this.resize();
}
