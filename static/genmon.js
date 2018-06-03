// Define header
$("#myheader").html('<header>Generator Monitor</header>');

// Define main menu
$("#navMenu").html('<ul>' +
      '<li id="status"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="status" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Status</td></tr></table></a></li>' +
      '<li id="maint"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="maintenance" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Maintenance</td></tr></table></a></li>' +
      '<li id="outage"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="outage" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Outage</td></tr></table></a></li>' +
      '<li id="logs"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="log" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Logs</td></tr></table></a></li>' +
      '<li id="monitor"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="monitor" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Monitor</td></tr></table></a></li>' +
      '<li id="notifications"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="notifications" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Notifications</td></tr></table></a></li>' +
      '<li id="settings"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="settings" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Settings</td></tr></table></a></li>' +
    '</ul>') ;

// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var currentClass = "active";    // CSS class for menu color
var menuElement = "status";
var ajaxErrors = {errorCount: 0, lastSuccessTime: 0, log: ""};
var windowActive = true;
var latestVersion = "";
var resizeTimeout;

var myGenerator = {sitename: "", nominalRPM: 3600, nominalfrequency: 60, Controller: "", model: "", nominalKW: 22, fueltype: "", UnsentFeedback: false, SystemHealth: false, EnhancedExerciseEnabled: false, OldExerciseParameters:[-1,-1,-1,-1,-1,-1]};
var regHistory = {updateTime: {}, _10m: {}, _60m: {}, _24h: {}, historySince: "", count_60m: 0, count_24h: 0};
var kwHistory = {data: [], plot:"", kwDuration: "h", tickInterval: "10 minutes", formatString: "%H:%M", defaultPlotWidth: 4, oldDefaultPlotWidth: 4};
var prevStatusValues = {};
var pathname = window.location.href;
var baseurl = pathname.concat("cmd/");
var DaysOfWeekArray = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];
var MonthsOfYearArray = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
var BaseRegistersDescription = {};

vex.defaultOptions.className = 'vex-theme-os'

//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
GetGeneratorModel();
GetBaseStatus();
SetFavIcon();
GetkWHistory();
GetRegisterNames();
$(document).ready(function() {
    $("#footer").html('<table border="0" width="100%" height="30px"><tr><td width="5%"><img class="tooltip alert_small" id="ajaxWarning" src="images/transparent.png" height="28px" width="28px" style="display: none;"></td><td width="90%"><a href="https://github.com/jgyates/genmon" target="_blank">GenMon Project on GitHub</a></td><td width="5%"></td></tr></table>');
    $('#ajaxWarning').tooltipster({minWidth: '280px', maxWidth: '480px', animation: 'fade', updateAnimation: 'null', contentAsHTML: 'true', delay: 100, animationDuration: 200, side: ['top', 'left'], content: "No Communicatikon Errors occured"});
    UpdateRegisters(true, false);
    setInterval(GetBaseStatus, 3000);       // Called every 3 sec
    setInterval(UpdateDisplay, 5000);       // Called every 5 sec
    DisplayStatusFullWhenReady();
    $("#status").find("a").addClass(GetCurrentClass());
    $("li").on('click',  function() {  MenuClick($(this));});
    resizeDiv();
});


window.onresize = function(event) {
    resizeDiv();
}


//*****************************************************************************
//  Manage AJAX responsees
//*****************************************************************************
function processAjaxSuccess() {
    var now = new moment();
    if (ajaxErrors["errorCount"]>5) {
      ajaxErrors["log"] = ajaxErrors["errorCount"]+" messages missed between "+ajaxErrors["lastSuccessTime"].format("H:mm:ss") + " and " +now.format("H:mm:ss") +"<br>" + ajaxErrors["log"];
      if ((myGenerator['UnsentFeedback'] == false) && (myGenerator['SystemHealth'] == false)) {
        $("#footer").removeClass("alert");
        $("#ajaxWarning").hide(400);
      }
    }
    ajaxErrors["errorCount"] = 0;
    ajaxErrors["lastSuccessTime"] = new moment();
}

function processAjaxError(xhr, ajaxOptions, thrownError) {
    // alert(xhr.status);
    // alert(thrownError);
    ajaxErrors["errorCount"]++;
    if (ajaxErrors["errorCount"]>5) {
      var tempMsg = '<b><span style="font-size:14px">Disconnected from server</span></b><br>'+ajaxErrors["errorCount"]+' messages missed since '+ajaxErrors["lastSuccessTime"].format("H:mm:ss")+"</b><br><br>"+((ajaxErrors["log"].length>500) ? ajaxErrors["log"].substring(0, 500)+"<br>[...]" : ajaxErrors["log"]);
      $("#footer").addClass("alert");
      $("#ajaxWarning").show(400);
      $('#ajaxWarning').tooltipster('content', tempMsg);
    }
}


//*****************************************************************************
//  Make Sure window resize is handled correctly
//*****************************************************************************
function resizeDiv() {
     vpw = $(window).width();
     vph = $(window).height();
     $('#mytable').css({'height': vph + 'px'});
     $('#mytable').css({'width': vpw + 'px'});
     $('#myheader').css({'height': '30px'});
     $('#myheader').css({'width': vpw + 'px'});
     $('#myDiv').css({'height': (vph-60) + 'px'});
     $('#myDiv').css({'width': (vpw-200) + 'px'});
     $('#navMenu').css({'height': (vph-60) + 'px'});
     $('#navMenu').css({'width': '200px'});
     $('#footer').css({'height': '30px'});
     $('#footer').css({'width': vpw + 'px'});
     
     if ((menuElement == "status") && ($('.packery').length > 0)) {
        var gridWidth = Math.round((vpw-240)/190);
            gridWidth = (gridWidth < 1) ? 1 : gridWidth;
        kwHistory["defaultPlotWidth"] = ((gridWidth > 4) ? 4 : (gridWidth < 1) ? 1 : gridWidth);
        if (kwHistory["defaultPlotWidth"] != kwHistory["oldDefaultPlotWidth"]) {
           kwHistory["oldDefaultPlotWidth"] = kwHistory["defaultPlotWidth"];
           $('.plotField').css({'width': (kwHistory["defaultPlotWidth"] * 180)+((kwHistory["defaultPlotWidth"]-1)*10) + 'px'});
        
           if ((windowActive == true) && (typeof kwHistory["plot"].replot !== "undefined")) {
              var now = new moment();
              var max = now.format("YYYY-MM-DD H:mm:ss");
              if (kwHistory["kwDuration"] == "h")
                 max = now.add(1, "m").format("YYYY-MM-DD H:mm:ss")
              if (kwHistory["kwDuration"] == "d")
                 max = now.add(1, "h").format("YYYY-MM-DD H:mm:ss")
              kwHistory["plot"].replot({data: [kwHistory["data"]], axes:{xaxis:{tickInterval: kwHistory["tickInterval"], tickOptions:{formatString:kwHistory["formatString"]}, max:now.format("YYYY-MM-DD H:mm:ss"), min:now.add(-1, kwHistory["kwDuration"]).format("YYYY-MM-DD H:mm:ss")}}});
           }
        }

        $('.packery').css({'width': (vpw - 240) + 'px'});
     }
     
}

//*****************************************************************************
//  Make sure we stop replots when windows in inactive. Chrome has a bug
//  that causes crashes otherwise:
//  https://plumbr.io/blog/performance-blog/leaking-gpu-memory-google-chrome-edition
//*****************************************************************************

$(window).focus(function() {
    windowActive = true;
    // console.log(moment().format("YYYY-MM-DD HH:mm:ss") + " window became active. Starting background replots for jqplot");
});

$(window).blur(function() {
    windowActive = false;
    // console.log(moment().format("YYYY-MM-DD HH:mm:ss") + " window became inactive. Stopping background replots for jqplot");
});

//*****************************************************************************
//
//*****************************************************************************
Number.prototype.pad = function(size) {
      var s = String(this);
      while (s.length < (size || 2)) {s = "0" + s;}
      return s;
    }

//*****************************************************************************
// called when setting a remote command
//*****************************************************************************
function SetRemoteCommand(command){

    // set remote command
    var url = baseurl.concat("setremote");
    $.getJSON(  url,
                {setremote: command},
                function(result){
   });

}


//*****************************************************************************
// DisplayStatusFull - show the status page at the beginning or when switching
// from another page
//*****************************************************************************
var gauge = [];

function DisplayStatusFullWhenReady() {
    if(myGenerator["tiles"] == undefined) {//we want it to match
        setTimeout(DisplayStatusFullWhenReady, 50);//wait 50 millisecnds then recheck
        return false;
    }
    DisplayStatusFull();
    return true;
}

function DisplayStatusFull()
{
    var vpw = $(window).width();
    var gridWidth = Math.round((vpw-240)/190);
        gridWidth = (gridWidth < 1) ? 1 : gridWidth;
    kwHistory["defaultPlotWidth"] = ((gridWidth > 4) ? 4 : (gridWidth < 1) ? 1 : gridWidth);
    kwHistory["oldDefaultPlotWidth"] = kwHistory["defaultPlotWidth"];
        
    var outstr = 'Dashboard:<br><br>';
    outstr += '<center><div class="packery">';
    for (var i = 0; i < myGenerator["tiles"].length; ++i) {
       switch (myGenerator["tiles"][i].type) {
          case "gauge":
             if (myGenerator["tiles"][i].title == "Fuel") { 
               outstr += '<div id="fuelField_'+i+'" class="grid-item gaugeField"><br>'+myGenerator["tiles"][i].title+'<br><div style="display: inline-block; width:100%; height:65%; position: relative;"><canvas class="gaugeCanvas" id="gauge'+i+'_bg" style="height: 100%; position: absolute; left: 0; top: 0; z-index: 1;"></canvas><canvas class="gaugeCanvas" id="gauge'+i+'" style="height: 100%; position: absolute; left: 0; top: 0; z-index: 0;"></canvas></div><br><div id="text'+i+'" class="gaugeDiv"></div></div>';          
             } else {
               outstr += '<div id="gaugeField_'+i+'" class="grid-item gaugeField"><br>'+myGenerator["tiles"][i].title+'<br><canvas class="gaugeCanvas" id="gauge'+i+'"></canvas><br><div id="text'+i+'" class="gaugeDiv"></div></div>';
             }
             break;
          case "graph":
             outstr += '<div id="plotField" class="grid-item plotField"><br>'+myGenerator["tiles"][i].title+'<br><div id="plotkW" class="kwPlotCanvas"></div><span class="kwPlotText">Time (<div class="kwPlotSelection selection" id="1h">1 hour</div> | <div class="kwPlotSelection" id="1d">1 day</div> | <div class="kwPlotSelection" id="1w">1 week</div> | <div class="kwPlotSelection" id="1m">1 month</div>)</span></div>';
             break;
       }
    }
    outstr += '</div></center><br>';
    $("#mydisplay").html(outstr + '<div style="clear:both" id="statusText"></div>');
    
    $('.packery').css({'width': (vpw-240) + 'px'});
    $('.plotField').css({'width': (kwHistory["defaultPlotWidth"] * 180)+((kwHistory["defaultPlotWidth"]-1)*10) + 'px'});

    $('.packery').packery({itemSelector: '.grid-item', gutter: 10, columnWidth: 85, rowHeight: 95, percentPosition: false, originLeft: true, resize: true});

    var $itemElems = $(".grid-item");
    $itemElems.draggable().resizable();
    $('.packery').packery( 'bindUIDraggableEvents', $itemElems );

    var resizeTimeout;
    var $itemElems = $( $('.packery').packery('getItemElements') );
    $itemElems.on( 'resize', function( event, ui ) {
           if ( resizeTimeout ) {
               clearTimeout( resizeTimeout );
           }
           resizeTimeout = setTimeout( function() {
               if (ui == undefined) /// don't know why. but this gets called twice. Once without ui set and we want to avoid that!
                 return;
               var newWidth = Math.round(ui.size.width/85)*85 + (Math.round(ui.size.width/85)-1)*10;
               var newHeight = Math.round(ui.size.height/95)*95 + (Math.round(ui.size.height/95)-1)*10;
               ui.element[0].style.width =  newWidth + "px";
               ui.element[0].style.height =  newHeight + "px";
               if ((newWidth <= 85) || (newHeight <= 95)) {
                   if (newWidth <= 85)
                     ui.element[0].style.width = '85px';
                   if (newHeight <= 95)
                     ui.element[0].style.height = '95px';
                   ui.element[0].style.fontSize = '10px';
                   if (ui.element[0].id == "plotField")
                     ui.element[0].children[3].style.fontSize = '7px';
               } else {
                   ui.element[0].style.fontSize = '18px';
                   if (ui.element[0].id == "plotField")
                     ui.element[0].children[3].style.fontSize = '10px';
               }
               if (ui.element[0].id.match("^gaugeField_")) {
                  var curr_i = replaceAll(ui.element[0].id, 'gaugeField_', '');
                  $('<canvas class="gaugeCanvas" id="gauge'+curr_i+'">').replaceAll($("#gauge"+curr_i));
                  $("#gauge"+curr_i).css("width", newWidth + "px");
                  $("#gauge"+curr_i).css("height", newHeight - ((newHeight == 95) ? 35 : 70) + "px");
                  gauge[curr_i] = createGauge($("#gauge"+curr_i), $("#text"+curr_i), 0, myGenerator["tiles"][curr_i].minimum, myGenerator["tiles"][curr_i].maximum,
                                           myGenerator["tiles"][curr_i].labels, myGenerator["tiles"][curr_i].colorzones, myGenerator["tiles"][curr_i].divisions, myGenerator["tiles"][curr_i].subdivisions);
               }
               if (ui.element[0].id.match("^fuelField_")) {
                  var curr_i = replaceAll(ui.element[0].id, 'fuelField_', '');
                  $('<canvas class="gaugeCanvas" id="gauge'+curr_i+'">').replaceAll($("#gauge"+curr_i));
                  $("#gauge"+curr_i).css("width", newWidth + "px");
                  $("#gauge"+curr_i).css("height", newHeight - ((newHeight == 95) ? 35 : 70) + "px");
                  $("#gauge"+curr_i+"_bg").css("width", newWidth + "px");
                  $("#gauge"+curr_i+"_bg").css("height", newHeight - ((newHeight == 95) ? 35 : 70) + "px");
                  gauge[curr_i] = createFuel($("#gauge"+curr_i), $("#text"+curr_i), $("#gauge"+curr_i+"_bg"));
               }
               if (ui.element[0].id == "plotField") {
                  $("#plotkW").css("width", newWidth + "px");
                  $("#plotkW").css("height", newHeight - ((newHeight == 95) ? 35 : 70) + "px");
                  // $("#plotkW").width = newWidth;
                  // $("#plotkW").height = newHeight - ((newHeight == 95) ? 35 : 70);
               }
               $('.packery').packery( 'fit', ui.element[0] );
           }, 100 );
    });

    for (var i = 0; i < myGenerator["tiles"].length; ++i) {
       switch (myGenerator["tiles"][i].type) {
          case "gauge":
             if (myGenerator["tiles"][i].title == "Fuel") {
                gauge[i] = createFuel($("#gauge"+i), $("#text"+i), $("#gauge"+i+"_bg"));
             } else {
                gauge[i] = createGauge($("#gauge"+i), $("#text"+i), 0, myGenerator["tiles"][i].minimum, myGenerator["tiles"][i].maximum,
                                                   myGenerator["tiles"][i].labels, myGenerator["tiles"][i].colorzones, myGenerator["tiles"][i].divisions, myGenerator["tiles"][i].subdivisions);
             }
             if ((prevStatusValues["tiles"] != undefined) && (prevStatusValues["tiles"].length > i) && (prevStatusValues["tiles"][i].value !== "")) {
                gauge[i].set(prevStatusValues["tiles"][i].value); // set current value
                $("#text"+i).html(prevStatusValues["tiles"][i].text);
             }
             break;
          case "graph":
             createGraph(myGenerator["tiles"][i].title, myGenerator["tiles"][i].minimum, myGenerator["tiles"][i].maximum);
             break;
       }     
    }
    
    var url = baseurl.concat("status_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        $("#statusText").html(json2html(result, "", "root"));
    }});
    return;
}

function json2html(json, intent, parentkey) {
    var outstr = '';
    if (typeof json === 'string') {
      outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div><br>';
    } else if (typeof json === 'number') {
      outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json + '</div><br>';
    } else if (typeof json === 'boolean') {
      outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json + '</div><br>';
    } else if (json === null) {
      outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">null</div><br>';
    }
    else if (json instanceof Array) {
      if (json.length > 0) {
        intent += "&nbsp;&nbsp;&nbsp;&nbsp;";
        for (var i = 0; i < json.length; ++i) {
          outstr += json2html(json[i], intent, parentkey+"_"+i);
        }
      }
    }
    else if (typeof json === 'object') {
      var key_count = Object.keys(json).length;
      if (key_count > 0) {
        intent += "&nbsp;&nbsp;&nbsp;&nbsp;";
        for (var key in json) {
          if (json.hasOwnProperty(key)) {
            if ((typeof json[key] === 'string') || (typeof json[key] === 'number') || (typeof json[key] === 'boolean') || (typeof json[key] === null)) {
               outstr += intent + key + ' : ' + json2html(json[key], intent, key);
            } else {
               outstr += "<br>" + intent + key + ' :<br>' + json2html(json[key], intent, key);
            }
          }
        }
      }
    }
    return outstr;
}

function createGauge(pCanvas, pText, pTextPrecision, pMin, pMax, pLabels, pZones, pDiv, pSubDiv) {
    var opts = {
      angle: -0.2, // The span of the gauge arc
      lineWidth: 0.2, // The line thickness
      radiusScale: 0.73, // Relative radius
      pointer: {
        length: 0.6, // // Relative to gauge radius
        strokeWidth: 0.038, // The thickness
        color: '#000000' // Fill color
      },
      limitMax: false,     // If false, max value increases automatically if value > maxValue
      limitMin: false,     // If true, the min value of the gauge will be fixed
      generateGradient: true,
      highDpiSupport: true,     // High resolution support
      staticLabels: {
        font: "10px sans-serif",  // Specifies font
        labels: pLabels,  // Print labels at these values
        color: "#000000",  // Optional: Label text color
        fractionDigits: pTextPrecision  // Optional: Numerical precision. 0=round off.
      },
      staticZones: pZones,
      // renderTicks is Optional
      renderTicks: {
        divisions: pDiv,
        divWidth: 0.1,
        divLength: 0.48,
        divColor: '#333333',
        subDivisions: pSubDiv,
        subLength: 0.17,
        subWidth: 0.1,
        subColor: '#666666'
      }
    };

    var gauge = new Gauge(pCanvas[0]).setOptions(opts);
    gauge.minValue = pMin; // set max gauge value
    gauge.maxValue = pMax; // set max gauge value
    // gauge.setTextField(pText, pTextPrecision);
    gauge.animationSpeed = 1; // set animation speed (32 is default value)
    gauge.set(pMin); // setting starting point
    gauge.animationSpeed = 1000; // set animation speed (32 is default value)

    return gauge;
}


function createFuel(pCanvas, pText, pFG) {
    var opts = {
      angle: 0.23, // The span of the gauge arc
      lineWidth: 0, // The line thickness
      radiusScale: 1, // Relative radius
      pointer: {
        length: 0.4, // // Relative to gauge radius
        strokeWidth: 0.045, // The thickness
        color: '#FF0000' // Fill color
      },
      limitMax: true,     // If false, max value increases automatically if value > maxValue
      limitMin: true,     // If true, the min value of the gauge will be fixed
      colorStart: '#E0E0E0',   // Colors
      colorStop: '#E0E0E0',    // just experiment with them
      strokeColor: '#E0E0E0',  // to see which ones work best for you
      generateGradient: false,
      highDpiSupport: true,     // High resolution support
    };
    
    var gauge = new Gauge(pCanvas[0]).setOptions(opts);
    gauge.minValue = 0; // set max gauge value
    gauge.maxValue = 100; // set max gauge value
    // gauge.setTextField(pText, pTextPrecision);
    gauge.animationSpeed = 1; // set animation speed (32 is default value)
    
    var w = gauge.canvas.width / 2;
    var r = gauge.radius * 0.7 ;
    var h = (gauge.canvas.height * gauge.paddingTop + gauge.availableHeight) - ((gauge.radius + gauge.lineWidth / 2) * gauge.extraPadding);
    
    pFG[0].width = gauge.canvas.width;
    pFG[0].height = gauge.canvas.height;
    var ctx = pFG[0].getContext('2d');

    ctx.fillStyle = "#363636";
    ctx.strokeStyle = "#363636";
    ctx.beginPath();
    ctx.arc( w, h, Math.round(r/6), 0, 2 * Math.PI);
    ctx.fill();
    
    var bgImage = new Image;
    bgImage.src = "images/sprites.png";
    bgImage.onload = function() {
      ctx.drawImage(bgImage, 0, 206, 400, 189, w-r, 10, 2*r, 2*r * 189/400);
    };

    return gauge;
}

function createGraph(title, minimum, maximum) {
    kwHistory["kwDuration"] = "h";
    kwHistory["tickInterval"] = "10 minutes";
    kwHistory["formatString"] = "%H:%M";
    var now = new moment();
    kwHistory["plot"] =  $.jqplot('plotkW', (kwHistory["data"].length > 0) ? [kwHistory["data"]] : [[[now.format("YYYY-MM-DD H:mm:ss"), 0]]], {
                axesDefaults: { labelOptions:  { fontFamily: 'Arial', textColor: '#000000', fontSize: '8pt' },
                tickOptions: { fontFamily: 'Arial', textColor: '#000000', fontSize: '6pt' }},
                grid: { drawGridLines: true, gridLineColor: '#cccccc', background: '#e1e1e1', borderWidth: 0, shadow: false, shadowWidth: 0 },
                gridPadding: {right:40, left:55},
                axes: {
                    xaxis:{
                        renderer:$.jqplot.DateAxisRenderer,
                        tickInterval: kwHistory["tickInterval"],
                        tickOptions:{formatString:kwHistory["formatString"]},
                        min: now.add(-1, kwHistory["kwDuration"]).format("YYYY-MM-DD H:mm:ss"),
                        max: now.format("YYYY-MM-DD H:mm:ss")
                    },
                    yaxis:{
                        label:"kW",
                        labelRenderer: $.jqplot.CanvasAxisLabelRenderer,
                        min: minimum,
                        max: maximum
                    }
                },
                highlighter: {
                    show: true,
                    sizeAdjust: 7.5
                },
                cursor:{
                    show: true,
                    zoom:true,
                    showTooltip:true
                }
    });
    $(".kwPlotSelection").on('click', function() {
               $(".kwPlotSelection").removeClass("selection");
               $(this).addClass("selection");
               switch ($(this).attr("id")) {
                 case "1h":
                   kwHistory["kwDuration"] = "h";
                   kwHistory["tickInterval"] = "10 minutes";
                   kwHistory["formatString"] = "%H:%M";
                   break;
                 case "1d":
                   kwHistory["kwDuration"] = "d";
                   kwHistory["tickInterval"] = "1 hour";
                   kwHistory["formatString"] = "%#I%p";
                   break;
                 case "1w":
                   kwHistory["kwDuration"] = "w";
                   kwHistory["tickInterval"] = "1 day";
                   kwHistory["formatString"] = "%d %b";
                   break;
                 case "1m":
                   kwHistory["kwDuration"] = "M";
                   kwHistory["tickInterval"] = "1 day";
                   kwHistory["formatString"] = "%d";
                   break;
                 default:
                   break
               }
    });

}

function printKwPlot(currentKw) {
   var now = new moment();
   if (currentKw == 0)
     kwHistory["data"].unshift([now.format("YYYY-MM-DD HH:mm:ss"), 0]); /// add a zero to the current point temporarily

   var max = now.format("YYYY-MM-DD H:mm:ss");
   if (kwHistory["kwDuration"] == "h")
     max = now.add(1, "m").format("YYYY-MM-DD H:mm:ss")
   if (kwHistory["kwDuration"] == "d")
     max = now.add(1, "h").format("YYYY-MM-DD H:mm:ss")

   if ((windowActive == true) && (typeof kwHistory["plot"].replot !== "undefined")) 
     kwHistory["plot"].replot({data: [kwHistory["data"]], axes:{xaxis:{tickInterval: kwHistory["tickInterval"], tickOptions:{formatString:kwHistory["formatString"]}, max:now.format("YYYY-MM-DD H:mm:ss"), min:now.add(-1, kwHistory["kwDuration"]).format("YYYY-MM-DD H:mm:ss")}}});

   if (currentKw == 0)
     kwHistory["data"].shift();  /// remove the zero again

   if (kwHistory["data"].length > 2500)
     GetkWHistory();
}

//*****************************************************************************
// DisplayStatusUpdate - updates the status page at every interval
//*****************************************************************************
function DisplayStatusUpdate()
{
    var url = baseurl.concat("status_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        $("#statusText").html(json2html(result, "", "root"));
        // json2updates(result, "root");
    }});

}

function json2updates(json, parentkey) {
    if ((typeof json === 'string') && ($("#"+parentkey.replace(/ /g, '_')).html() != json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'))) {
      $("#"+parentkey.replace(/ /g, '_')).html(json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
      // $("#"+parentkey.replace(/ /g, '_')).css("color", "red");
    } else if ((typeof json === 'number') && ($("#"+parentkey.replace(/ /g, '_')).html() != json)) {
      $("#"+parentkey.replace(/ /g, '_')).html(json);
    } else if ((typeof json === 'boolean') && ($("#"+parentkey.replace(/ /g, '_')).html() != json)) {
      $("#"+parentkey.replace(/ /g, '_')).html(json);
    } else if ((json === null) && ($("#"+parentkey.replace(/ /g, '_')).html() != "null")) {
      $("#"+parentkey.replace(/ /g, '_')).html('null');
    }
    else if (json instanceof Array) {
      if (json.length > 0) {
        for (var i = 0; i < json.length; ++i) {
          json2updates(json[i], parentkey+"_"+i);
        }
      }
    }
    else if (typeof json === 'object') {
      var key_count = Object.keys(json).length;
      if (key_count > 0) {
        for (var key in json) {
          if (json.hasOwnProperty(key)) {
            json2updates(json[key], key);
          }
        }
      }
    }
}


//*****************************************************************************
// Display the Maintenance Tab
//*****************************************************************************
function DisplayMaintenance(){

    var url = baseurl.concat("maint_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        outstr = '<div style="clear:both" id="maintText">' + json2html(result, "", "root") + '</div>';

        outstr += "<br>Generator Exercise Time:<br><br>";

        //Create array of options to be added
        if (myGenerator['EnhancedExerciseEnabled'] == true) {
           outstr += '&nbsp;&nbsp;&nbsp;&nbsp;<select id="ExerciseFrequency" onChange="setExerciseSelection()">';
           outstr += '<option value="Weekly" ' + (myGenerator['ExerciseFrequency'] == "Weekly"  ? ' selected="selected" ' : '') + '>Weekly</option>';
           outstr += '<option value="Biweekly" ' + (myGenerator['ExerciseFrequency'] == "Biweekly"  ? ' selected="selected" ' : '') + '>Biweekly</option>';
           outstr += '<option value="Monthly" ' + (myGenerator['ExerciseFrequency'] == "Monthly"  ? ' selected="selected" ' : '') + '>Monthly</option>';
           outstr += '</select>';
        }

        //Create and append the options, days
        outstr += '&nbsp;<select id="days"></select> , ';
        //Create and append the options, hours
        outstr += '<select id="hours">';
        for (var i = 0; i < 24; i++) {
            outstr += '<option value="' + i.pad() + '">' + i.pad() + '</option>';
        }
        outstr += '</select> : ';

        //Create and append the options, minute
        outstr += '<select id="minutes">';
        for (var i = 0; i < 60; i++) {
            outstr += '<option value="' + i.pad() + '">' + i.pad() + '</option>';
        }
        outstr += '</select>';

        //Create and append select list
        outstr += '&nbsp;&nbsp;<select id="quietmode">';
        outstr += '<option value="On" ' + (myGenerator['QuietMode'] == "On"  ? ' selected="selected" ' : '') + '>Quiet Mode On </option>';
        outstr += '<option value="Off"' + (myGenerator['QuietMode'] == "Off" ? ' selected="selected" ' : '') + '>Quiet Mode Off</option>';
        outstr += '</select><br><br>';

        outstr += '&nbsp;&nbsp;<button id="setexercisebutton" onClick="saveMaintenance();">Set Exercise Time</button>';

        outstr += '<br><br>Generator Time:<br><br>';
        outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetTimeClick();">Set Generator Time</button>';

        outstr += '<br><br>Remote Commands:<br><br>';

        outstr += '&nbsp;&nbsp;&nbsp;&nbsp;<button class="tripleButtonLeft" id="remotestop" onClick="SetStopClick();">Stop Generator</button>';
        outstr += '<button class="tripleButtonCenter" id="remotestart" onClick="SetStartClick();">Start Generator</button>';
        outstr += '<button class="tripleButtonRight"  id="remotetransfer" onClick="SetTransferClick();">Start Generator and Transfer</button><br><br>';

        $("#mydisplay").html(outstr);


        setExerciseSelection();

        $("#days").val(myGenerator['ExerciseDay']);
        $("#hours").val(myGenerator['ExerciseHour']);
        $("#minutes").val(myGenerator['ExerciseMinute']);

        startStartStopButtonsState();

        myGenerator["OldExerciseParameters"] = [myGenerator['ExerciseDay'], myGenerator['ExerciseHour'], myGenerator['ExerciseMinute'], myGenerator['QuietMode'], myGenerator['ExerciseFrequency'], myGenerator['EnhancedExerciseEnabled']];

   }});
}

//*****************************************************************************
// called when Monthly is clicked
//*****************************************************************************
function setExerciseSelection(freq){
   if ((myGenerator['EnhancedExerciseEnabled'] == true) && ($("#ExerciseFrequency").val() == "Monthly")) {
      MonthlyExerciseSelection();
   } else {
      WeekdayExerciseSelection();
   }
}

//*****************************************************************************
// called when Monthly is clicked
//*****************************************************************************
function MonthlyExerciseSelection(){
    if (($('#days option')).lenghth != 28) {
       $("#days").find('option').remove();
       for (var i = 1; i <= 28; i++) {
           $("#days").append('<option value="' + i.pad() + '">' + i.pad() + '</option>');
       }
    }
    $("#days").val(myGenerator['ExerciseDay']);
}
//*****************************************************************************
// called when Monthly is clicked
//*****************************************************************************
function WeekdayExerciseSelection(){
    if ($('#days option').lenghth != 7) {
       $("#days").find('option').remove();
       for (var i = 0; i < DaysOfWeekArray.length; i++) {
           $("#days").append('<option value="' + DaysOfWeekArray[i]+ '">' + DaysOfWeekArray[i]+ '</option>');
       }
    }
    $("#days").val(myGenerator['ExerciseDay']);
}

//*****************************************************************************
// called when Set Remote Stop is clicked
//*****************************************************************************
function SetStopClick(){

    vex.dialog.confirm({
        unsafeMessage: 'Stop generator?<br><span class="confirmSmall">Note: If the generator is powering a load the transfer switch will be deactivated and there will be a cool down period of a few minutes.</span>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                SetRemoteCommand("stop")
             }
        }
    });
}

//*****************************************************************************
// called when Set Remote Start is clicked
//*****************************************************************************
function SetStartClick(){

    vex.dialog.confirm({
        unsafeMessage: 'Start generator?<br><span class="confirmSmall">Generator will start, warm up and run idle (without activating the transfer switch).</span>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                SetRemoteCommand("start")
             }
        }
    });
}

//*****************************************************************************
// called when Set Remote Tansfer is clicked
//*****************************************************************************
function SetTransferClick(){

    vex.dialog.confirm({
        unsafeMessage: 'Start generator and activate transfer switch?<br><span class="confirmSmall">Generator will start, warm up, then activate the transfer switch.</span>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                SetRemoteCommand("starttransfer")
             }
        }
    });
}

//*****************************************************************************
// called when Set Time is clicked
//*****************************************************************************
function SetTimeClick(){

    vex.dialog.confirm({
        unsafeMessage: 'Set generator time to monitor time?<br><span class="confirmSmall">Note: This operation may take up to one minute to complete.</span>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                // set exercise time
                var url = baseurl.concat("settime");
                $.getJSON(  url,
                   {settime: " "},
                   function(result){});
             }
        }
    });
}

//*****************************************************************************
// Display the Maintenance Tab
//*****************************************************************************
function DisplayMaintenanceUpdate(){

    $("#Exercise_Time").html(myGenerator['ExerciseFrequency'] + ' ' +
                             myGenerator['ExerciseDay'] + ' ' + myGenerator['ExerciseHour'] + ':' + myGenerator['ExerciseMinute'] +
                             ' Quiet Mode ' + myGenerator['QuietMode']);

    if ((myGenerator['EnhancedExerciseEnabled'] == true) && (myGenerator['ExerciseFrequency'] != myGenerator['OldExerciseParameters'][4])) {
        $("#ExerciseFrequency").val(myGenerator['ExerciseFrequency']);
        setExerciseSelection();
    }

    if (myGenerator['ExerciseDay'] !=  myGenerator['OldExerciseParameters'][0])
       $("#days").val(myGenerator['ExerciseDay']);
    if (myGenerator['ExerciseHour'] !=  myGenerator['OldExerciseParameters'][1])
       $("#hours").val(myGenerator['ExerciseHour']);
    if (myGenerator['ExerciseMinute'] !=  myGenerator['OldExerciseParameters'][2])
       $("#minutes").val(myGenerator['ExerciseMinute']);
    if (myGenerator['QuietMode'] !=  myGenerator['OldExerciseParameters'][3])
       $("#quietmode").val(myGenerator['QuietMode']);

    startStartStopButtonsState();

    myGenerator["OldExerciseParameters"] = [myGenerator['ExerciseDay'], myGenerator['ExerciseHour'], myGenerator['ExerciseMinute'], myGenerator['QuietMode'], myGenerator['ExerciseFrequency'], myGenerator['EnhancedExerciseEnabled']];

    var url = baseurl.concat("maint_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        $("#maintText").html(json2html(result, "", "root"));
        // $("#Next_Service_Scheduled").html(result["Maintenance"]["Service"]["Next Service Scheduled"]);
        // $("#Total_Run_Hours").html(result["Maintenance"]["Service"]["Total Run Hours"]);
    }});

}

function startStartStopButtonsState(){
   if((baseState === "EXERCISING") || (baseState === "RUNNING")) {
     $("#remotestop").prop("disabled",false);
     $("#remotestart").prop("disabled",true);
     $("#remotetransfer").prop("disabled",true);
   } else {
     $("#remotestop").prop("disabled",true);
     $("#remotestart").prop("disabled",false);
     $("#remotetransfer").prop("disabled",false);
   }

   $("#remotestop").css("background", "#bbbbbb");
   $("#remotestart").css("background", "#bbbbbb");
   $("#remotetransfer").css("background", "#bbbbbb");
   switch (baseState) {
    case "EXERCISING" :
        $("#remotestart").css("background", "#4CAF50");
        $("#remotestop").css("background", "#bbbbbb");
        $("#remotetransfer").css("background", "#bbbbbb");
        break;
    case "RUNNING":
        $("#remotetransfer").css("background", "#4CAF50");
        $("#remotestop").css("background", "#bbbbbb");
        $("#remotestart").css("background", "#bbbbbb");
        break;
     default:
        $("#remotestop").css("background", "#4CAF50");
        $("#remotestart").css("background", "#bbbbbb");
        $("#remotetransfer").css("background", "#bbbbbb");
        break;
   }
}

//*****************************************************************************
// called when Set Exercise is clicked
//*****************************************************************************
function saveMaintenance(){

    try {
        var strDays         = $("#days").val();
        var strHours        = $("#hours").val();
        var strMinutes      = $("#minutes").val();
        var strQuiet        = $("#quietmode").val();
        var strChoice       = ((myGenerator['EnhancedExerciseEnabled'] == true) ? $("#ExerciseFrequency").val() : "Weekly");
        var strExerciseTime = strDays + "," + strHours + ":" + strMinutes + "," + strChoice;

        vex.dialog.confirm({
            unsafeMessage: "Set exercise time to<br>" + strExerciseTime + ", " + strQuiet + "?",
            overlayClosesOnClick: false,
            callback: function (value) {
                 if (value == false) {
                    return;
                 } else {
                    // set exercise time
                    var url = baseurl.concat("setexercise");
                    $.getJSON(  url,
                                {setexercise: strExerciseTime},
                                function(result){});

                    // set quite mode
                    var url = baseurl.concat("setquiet");
                    $.getJSON(  url,
                                {setquiet: strQuiet},
                                function(result){});
                 }
            }
        });
    }
    catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}

//*****************************************************************************
// Display the Logs Tab
//*****************************************************************************
function DisplayLogs(){

    var url = baseurl.concat("logs");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result) {
        processAjaxSuccess();

        var outstr = '<center><div id="annualCalendar"></div></center>';
        outstr += replaceAll(replaceAll(result,'\n','<br/>'),' ','&nbsp');  // replace space with html friendly &nbsp

        $("#mydisplay").html(outstr);

        var date = new Date();
        var data_helper = {};
        var months = 1;
        var loglines = result.split('\n');
        var severity = 0;
        for(var i = 0;i < loglines.length;i++){
            if (loglines[i].indexOf("Alarm Log :") >= 0) {
               severity = 3;
            } else if (loglines[i].indexOf("Service Log :") >= 0) {
               severity = 2;
            } else if (loglines[i].indexOf("Start Stop Log :") >= 0) {
               severity = 1;
            } else {
               var matches = loglines[i].match(/^\s*(\d+)\/(\d+)\/(\d+) (\d+:\d+:\d+) (.*)$/i)
               if ((matches != undefined) && (matches.length == 6)) {
                  if ((12*matches[3]+1*matches[1]+12) <  (12*(date.getYear()-100) + date.getMonth() + 1)) {
                  } else if (data_helper[matches.slice(1,3).join("/")] == undefined) {
                      data_helper[matches.slice(1,3).join("/")] = {count: severity, date: '20'+matches[3]+'-'+matches[1]+'-'+matches[2], dateFormatted: matches[2]+' '+MonthsOfYearArray[(matches[1] -1)]+' 20'+matches[3], title: matches[5].trim()};
                      if (((12*(date.getYear()-100) + date.getMonth() + 1)-(12*matches[3]+1*matches[1])) > months) {
                          months = (12*(date.getYear()-100) + date.getMonth() + 1)-(12*matches[3]+1*matches[1])
                      }
                  } else {
                      data_helper[matches.slice(1,3).join("/")]["title"] = data_helper[matches.slice(1,3).join("/")]["title"] + "<br>" + matches[5].trim();
                      if (data_helper[matches.slice(1,3).join("/")]["count"] < severity)
                         data_helper[matches.slice(1,3).join("/")]["count"] = severity;
                  }
               }
            }
        }
        var data = Object.keys(data_helper).map(function(itm) { return data_helper[itm]; });
        // var data = Object.keys(data_helper).map(itm => data_helper[itm]);
        // var data = Object.values(data_helper);
        // console.log(data);
        var options = {coloring: 'genmon', months: months, labels: { days: true, months: true, custom: {monthLabels: "MMM 'YY"}}, tooltips: { show: true, options: {}}, legend: { show: false}};
        $("#annualCalendar").CalendarHeatmap(data, options);
   }});
}

//*****************************************************************************
// Display the Monitor Tab
//*****************************************************************************
function DisplayMonitor(){

    var url = baseurl.concat("monitor_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result) {
        processAjaxSuccess();

        var outstr = json2html(result, "", "root");
        outstr += '<br><br>Update Generator Monitor Software:<br><div id="updateNeeded"><br></div>';
        outstr += '&nbsp;&nbsp;<button id="checkNewVersion" onClick="checkNewVersion();">Upgrade to latest version</button>';
        outstr += '<br><br>Submit Registers to Developers:<br><br>';
        outstr += '&nbsp;&nbsp;<button id="submitRegisters" onClick="submitRegisters();">Submit Registers</button>';

        $("#mydisplay").html(outstr);

        if ($("#CPU_Temperature").length > 0) {
           temp_img = "temp1";
           switch (true) {
              case (parseInt(prevStatusValues["PlatformStats"]["CPU Temperature"].replace(/C/g, '').trim()) > 85):
                  temp_img = "temp4";
                  break;
              case (parseInt(prevStatusValues["PlatformStats"]["CPU Temperature"].replace(/C/g, '').trim()) > 75):
                  temp_img = "temp3";
                  break;
              case (parseInt(prevStatusValues["PlatformStats"]["CPU Temperature"].replace(/C/g, '').trim()) > 50):
                  temp_img = "temp2";
                  break;
           }
           $("#CPU_Temperature").html('<div style="display: inline-block; position: relative;">'+result["Monitor"]["Platform Stats"]["CPU Temperature"] + '<img style="position: absolute;top:-10px;left:75px" class="'+ temp_img +'" src="images/transparent.png"></div>');
        }

        if ($("#WLAN_Signal_Level").length > 0) {
           wifi_img = "wifi1";
           switch (true) {
              case (parseInt(prevStatusValues["PlatformStats"]["WLAN Signal Level"].replace(/dBm/g, '').trim()) > -67):
                  wifi_img = "wifi4";
                  break;
              case (parseInt(prevStatusValues["PlatformStats"]["WLAN Signal Level"].replace(/dBm/g, '').trim()) > -70):
                  wifi_img = "wifi3";
                  break;
              case (parseInt(prevStatusValues["PlatformStats"]["WLAN Signal Level"].replace(/dBm/g, '').trim()) > -80):
                  wifi_img = "wifi2";
                  break;
           }
           $("#WLAN_Signal_Level").html('<div style="display: inline-block; position: relative;">'+result["Monitor"]["Platform Stats"]["WLAN Signal Level"] + '<img style="position: absolute;top:-10px;left:110px" class="'+ wifi_img +'" src="images/transparent.png"></div>');
        }
        if ($("#Conditions").length > 0) {
           $("#Conditions").html('<div style="display: inline-block; position: relative;">'+result["Monitor"]["Weather"]["Conditions"] + '<img class="greyscale" style="position: absolute;top:-30px;left:160px" src="http://openweathermap.org/img/w/' + prevStatusValues["Weather"]["icon"] + '.png"></div>');
        }

        if (latestVersion == "") {
          // var url = "https://api.github.com/repos/jgyates/genmon/releases";
          var url = "https://raw.githubusercontent.com/jgyates/genmon/master/genmon.py";
          $.ajax({dataType: "html", url: url, timeout: 4000, error: function(result) {
             console.log("got an error when looking up latest version");
             latestVersion == "unknown";
          }, success: function(result) {
             latestVersion = replaceAll((jQuery.grep(result.split("\n"), function( a ) { return (a.indexOf("GENMON_VERSION") >= 0); }))[0].split(" ")[2], '"', '');
             if (latestVersion != myGenerator["version"]) {
                $('#updateNeeded').hide().html("<br>&nbsp;&nbsp;&nbsp;&nbsp;You are not running the latest version.<br>&nbsp;&nbsp;&nbsp;&nbsp;Current Version: " + myGenerator["version"] +"<br>&nbsp;&nbsp;&nbsp;&nbsp;New Version: " + latestVersion+"<br><br>").fadeIn(1000);
             }
          }});
        } else if ((latestVersion != "unknown") && (latestVersion != myGenerator["version"])) {
          $('#updateNeeded').html("<br>&nbsp;&nbsp;&nbsp;&nbsp;You are not running the latest version.<br>&nbsp;&nbsp;&nbsp;&nbsp;Current Version: " + myGenerator["version"] +"<br>&nbsp;&nbsp;&nbsp;&nbsp;New Version: " + latestVersion+"<br><br>");
        }
   }});
}

function checkNewVersion(){
    var DisplayStr = 'Checking for latest version...<br><br><div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
    $('.vex-dialog-buttons').html(DisplayStr);
    $('.progress-bar-fill').queue(function () {
        $(this).css('width', '100%')
    });
    var DisplayStrButtons = {
        NO: {
          text: 'Cancel',
          type: 'button',
          className: 'vex-dialog-button-secondary',
          click: function yesClick () { this.close() }
        },
        YES: {
          text: 'Upgrade',
          type: 'submit',
          className: 'vex-dialog-button-primary',
          click: function yesClick () { }
        }
    }

    var myDialog = vex.dialog.open({
        unsafeMessage: DisplayStr,
        overlayClosesOnClick: false,
        buttons: [
           DisplayStrButtons.NO,
           DisplayStrButtons.YES
        ],
        onSubmit: function(e) {
             e.preventDefault();
             updateSoftware();
             var DisplayStr1 = 'Downloading latest version...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
        }
    });

    if (latestVersion != myGenerator["version"]) {
          // $('.vex-dialog-message').html("A new version is available.<br>Current Version: " + myGenerator["version"] + "<br>New Version: " + latestVersion);
          $('.vex-dialog-message').html("Are you sure you want to update to the latest version?");
    } else {
          $('.vex-dialog-message').html("Are you sure you want to upgrade?");
    }
}

//*****************************************************************************
// called when requesting upgrade
//*****************************************************************************
function updateSoftware(){

    // set remote command
    var url = baseurl.concat("updatesoftware");
    $.ajax({
       type: "GET",
       url: url,
       dataType: "json",
       timeout: 0,
       success: function(results){
             /// THIS IS NOT AN EXPECTED RESPONSE!!! genserv.py is expected to restart on it's own before returning a valid value;
             vex.closeAll();
             GenmonAlert("An unexepected outcome occured. Genmon might not have been updated. Please verify manually or try again!");
       },
       error: function(XMLHttpRequest, textStatus, errorThrown){
             var DisplayStr1 = 'Restarting...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){ vex.closeAll(); location.reload();  }, 10000);
       }


    });
}

function submitRegisters(){
    vex.dialog.confirm({
        unsafeMessage: 'Send the contents of your generator registers to the developer for compatibility testing?<br>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                var url = baseurl.concat("sendregisters");
                $.getJSON(  url,
                   {},
                   function(result){});
             }
        }
    });
}

//*****************************************************************************
// Display the Notification Tab
//*****************************************************************************

// Additional Carriers are listed here: https://teamunify.uservoice.com/knowledgebase/articles/57460-communication-email-to-sms-gateway-list

function DisplayNotifications(){
    var url = baseurl.concat("notifications");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        var  outstr = 'Notification Recepients:<br><br>';
        outstr += '<form id="formNotifications">';
        outstr += '<table id="allnotifications" border="0"><tbody>';

        outstr += '<tr><td></td><td></td><td align="center">Email Address:</td><td align="center">Notifications:</td></tr>';

        $.each(Object.keys(result), function(i, key) {

            var displayText = key;
            var displayKey = "s01_email";
            outstr += renderNotificationLine(i, displayKey, displayText, result[key][1]);
        });
        outstr += '</tbody></table></form><br>';
        outstr += '<button value="+Add" id="addRow">+Add</button>&nbsp;&nbsp;&nbsp;&nbsp;<button id="setnotificationsbutton" onClick="saveNotifications()">Save</button>';

        $("#mydisplay").html(outstr);

        $('.notificationTypes').selectize({
            plugins: ['remove_button'],
            delimiter: ','
        });

        var rowcount = Object.keys(result).length;

        $(document).ready(function() {
           $("#addRow").click(function () {
              $("#allnotifications").each(function () {
                  var outstr = renderNotificationLine(rowcount, "", "", "")
                  if ($('tbody', this).length > 0) {
                      $('tbody', this).append(outstr);
                  } else {
                      $(this).append(outstr);
                  }
                  $("#notif_"+rowcount).selectize({
                      plugins: ['remove_button'],
                      delimiter: ','
                    });

                  rowcount++;
                  $(".removeRow").on('click', function(){
                     $('table#allnotifications tr#row_'+$(this).attr("rowcount")).remove();
                  });
              });
           });

           $(".removeRow").on('click', function(){
              $('table#allnotifications tr#row_'+$(this).attr("rowcount")).remove();
           });
        });
   }});
}

function renderNotificationLine(rowcount, line_type, line_text, line_perms) {

   var outstr = '<tr id="row_' + rowcount + '"><td nowrap><div rowcount="' + rowcount + '" class="removeRow"><img class="remove_bin" src="images/transparent.png" height="24px" width="24px"></div></td>';
   outstr += '<td nowrap><input type="hidden" name="type_' + rowcount + '" value="s01_email">';
   outstr += '<td nowrap><input id="email_' + rowcount + '" class="notificationEmail" name="email_' + rowcount + '" type="text" value="'+line_text+'" '+ ((line_type != "s01_email") ? 'class="dataMask"' : '') +' ></td>';

   outstr += '<td width="300px" nowrap><select multiple style="width:290px" class="notificationTypes" name="notif_' + rowcount + '" id="notif_' + rowcount + '" oldValue="'+line_perms+'" placeholder="Select types of notifications...">';
   outstr += ["outage", "error", "warn", "info"].map(function(key) { return '<option value="'+key+'" '+(((line_perms == undefined) || (line_perms.indexOf(key) != -1) || (line_perms == "")) ? ' selected ' : '')+'>'+key+'</option>'; }).join();
   outstr += '</select></td>';

   return outstr;
}


function setNotificationFieldValidation(rowcount) {
    if ($("#type_"+rowcount).val() == "s01_email") {
       $("#email_"+rowcount).unmask();
    } else {
       $("#email_"+rowcount).mask('(000) 000-0000', {placeholder: "(___) ___-____"});
    }
}

//*****************************************************************************
// called when Save Notifications is clicked
//*****************************************************************************
function saveNotifications(){

    var DisplayStr = "Save notifications? Are you sure?";
    var DisplayStrAnswer = false;
    var DisplayStrButtons = {
        NO: {
          text: 'Cancel',
          type: 'button',
          className: 'vex-dialog-button-secondary',
          click: function noClick () {
            DisplayStrAnswer = false
            this.close()
          }
        },
        YES: {
          text: 'OK',
          type: 'submit',
          className: 'vex-dialog-button-primary',
          click: function yesClick () {
            DisplayStrAnswer = true
          }
        }
    }


    var blankEmails = 0;
    $.each($("input[name^='email_']"), function( index, type ){
        if ($(this).val().trim() == "") {
           blankEmails++
        }
    });
    if (blankEmails > 0) {
       GenmonAlert("Recepients cannot be blank.<br>You have "+blankEmails+" blank lines.");
       return
    }

    vex.dialog.open({
        unsafeMessage: DisplayStr,
        overlayClosesOnClick: false,
        buttons: [
           DisplayStrButtons.NO,
           DisplayStrButtons.YES
        ],
        onSubmit: function(e) {
           if (DisplayStrAnswer) {
             DisplayStrAnswer = false; // Prevent recursive calls.
             e.preventDefault();
             saveNotificationsJSON();
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){ vex.closeAll();}, 10000);
           }
        }
    })
}

function saveNotificationsJSON(){
    try {
        var fields = {};

        $("input[name^='email_']").each(function() {
            var thisRow = ($(this).attr('id').split("_"))[1];
            var thisType  = $('#type_'+thisRow).val();
            var thisEmail = $(this).val();
            var thisVal   = (($('#notif_'+thisRow).val().length == 4) ? "" : $('#notif_'+thisRow).val().join(","));
            fields[thisEmail] = thisVal;
        });
        // console.log(fields);

        // save settings
        var url = baseurl.concat("setnotifications");
        $.getJSON(  url,
                    {setnotifications: $.param(fields)},
                    function(result){
        });

    } catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}

//*****************************************************************************
// Display the Settings Tab
//*****************************************************************************
function DisplaySettings(){

    var url = baseurl.concat("settings");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        var outstr = '<form class="idealforms" novalidate  id="formSettings">';
        var settings =  getSortedKeys(result, 2);
        for (var index = 0; index < settings.length; ++index) {
            var key = settings[index];
            if (key == "sitename") {
              outstr += '</table></fieldset><br>General Settings:<fieldset id="generalSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "nominalfrequency") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap>Generator Model Specific Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="modelSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "usehttps") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, result[key][3], "", "", "usehttpsChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Webserver Security Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="securitySettings"><table id="allsettings" border="0">';
            } else if (key == "disableemail") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += '<input id="' + key + '" name="' + key + '" type="hidden"' +
                         (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toString() == "true")) ? ' value="true" ' : ' value="false" ') +
                         (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toString() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') + '>';
              outstr += printSettingsField("boolean", "outboundemail", (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toString() == "true")) ? false : true), "", "", "outboundEmailChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Outbound Email Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="outboundEmailSettings"><table id="allsettings" border="0">';
            } else if (key == "imap_server") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px:>';
              outstr += printSettingsField("boolean", "inboundemail", ((result[key][3] != "") ? true : false), "", "", "inboundemailChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Inbound Email Commands Processing&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="inboundEmailSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "useselfsignedcert") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "useselfsignedcertChange(true);") + '</td></tr>';
              outstr += '</table><fieldset id="selfsignedSettings"><table id="allsettings" border="0">';
            } else if (key == "http_user") {
              outstr += '</table></fieldset><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "useselfsignedcertChange(true);") + '</td></tr>';
            } else if (key == "http_port") {
              outstr += '</table></fieldset><fieldset id="noneSecuritySettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "useselfsignedcertChange(true);") + '</td></tr>';
            } else if (key == "favicon") {
              outstr += '</table></fieldset><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "useselfsignedcertChange(true);") + '</td></tr>';
            } else if ((key == "autofeedback") && (myGenerator['UnsentFeedback'] == true)) {
              outstr += '<tr><td width="25px">&nbsp;</td><td bgcolor="#ffcccc" width="300px">' + result[key][1] + '</td><td bgcolor="#ffcccc">' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "weatherkey") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px:>';
              outstr += printSettingsField("boolean", "weather", ((result[key][3] != "") ? true : false), "", "", "weatherChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Display Current Weather&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="weatherSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            }
        }
        outstr += '</table></fieldset></form><br>';
        outstr += '<button id="setsettingsbutton" onClick="saveSettings()">Save</button>';

        $("#mydisplay").html(outstr);
        $('input').lc_switch();
        $.extend($.idealforms.rules, {
           // InternetAddress: /^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,5}(\/.*)?$/g, /// Warning - this does nto seem to work well.
           // The rule is added as "ruleFunction:arg1:arg2"
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,5}(\/.*)?$", 'g');
             return regex.test(value);
           },
           UnixFile: function(input, value, arg1, arg2) {
             var regex = RegExp("^(\/[^\/]+)+$", 'g');
             return regex.test(value);
           },
           UnixDir: function(input, value, arg1, arg2) {
             var regex = RegExp("^(\/[^\/]+)+\/$", 'g');
             return regex.test(value);
           },
           UnixDevice: function(input, value, arg1, arg2) {
             var regex = RegExp("^\/dev(\/[^\/]+)+$", 'g');
             return regex.test(value);
           }
        });
        $.extend($.idealforms.errors, {
            InternetAddress: 'Must be a valid address from an internet server, eg. mail.google.com',
            UnixFile: 'Must be a valid UNIX file',
            UnixDir: 'Must be a valid UNIX path',
            UnixDevice: 'Must be a valid UNIX file path starting with /dev/'
        });
        $('form.idealforms').idealforms({
           tooltip: '.tooltip',
           silentLoad: true,
        });

        usehttpsChange(false);
        outboundEmailChange(false);
        inboundemailChange(false);
        useselfsignedcertChange(false);
   }});

}

function usehttpsChange(animation) {
   if ($("#usehttps").is(":checked")) {
      $("#noneSecuritySettings").hide((animation ? 300 : 0));
      $("#securitySettings").show((animation ? 300 : 0));

      if (!$("#useselfsignedcert").is(":checked")) {
         $("#selfsignedSettings").show((animation ? 300 : 0));
      }
   } else {
      $("#securitySettings").hide((animation ? 300 : 0));
      $("#noneSecuritySettings").show((animation ? 300 : 0));
   }
}

function useselfsignedcertChange(animation) {
   if ($("#useselfsignedcert").is(":checked")) {
      $("#selfsignedSettings").hide((animation ? 300 : 0));
   } else {
      $("#selfsignedSettings").show((animation ? 300 : 0));
   };
}

function outboundEmailChange(animation) {
   if($("#outboundemail").is(":checked")) {
      $("#outboundEmailSettings").show((animation ? 300 : 0));
      $("#disableemail").val("false");
   } else {
      $("#outboundEmailSettings").hide((animation ? 300 : 0));
      $("#disableemail").val("true");
   }
}

function inboundemailChange(animation) {
   if($("#inboundemail").is(":checked")) {
      $("#inboundEmailSettings").show((animation ? 300 : 0));
   } else {
      $("#inboundEmailSettings").hide((animation ? 300 : 0));
   }
}

function weatherChange(animation) {
   if($("#weather").is(":checked")) {
      $("#weatherSettings").show((animation ? 300 : 0));
   } else {
      $("#weatherSettings").hide((animation ? 300 : 0));
   }
}

function printSettingsField(type, key, value, tooltip, validation, callback) {
   var outstr = "";
   switch (type) {
     case "string":
     case "password":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + '" style="width: 300px;" name="' + key + '" type="' + ((type == "password") ? "password" : "text") + '" ' +
                  (typeof value === 'undefined' ? '' : 'value="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (typeof validation === 'undefined' ? '' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>') +
                 '</div>';
       break;
     case "int":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + '" style="width: 150px;" name="' + key + '" type="text" ' +
                  (typeof value === 'undefined' ? '' : 'value="' + value.toString() + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + value.toString() + '" ') +
                  (typeof validation === 'undefined' ? '' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>') +
                 '</div>';
       break;
     case "boolean":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<input id="' + key + '" name="' + key + '" type="checkbox" ' +
                  ((callback != "") ? ' data-callback="' + callback + ';" ' : "") +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' checked ' : '') +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') + '>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span><i class="icon"></i>') +
                 '</div>';
       break;
     case "list":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<select id="' + key + '" style="width: 300px;" name="' + key + '" ' +
                  (typeof value === 'undefined' ? '' : 'value="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + replaceAll(value, '"', '&quot;') + '" ') + '>' +
                 $.map(validation.split(","), function( val, i ) { return '<option class="optionClass" name="'+val+'" '+((val==value) ? 'selected' : '')+'>'+val+'</option>'}).join() +
                 '</select>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span><i class="icon"></i>') +
                 '</div>';
       break;
     default:
       break;
   }
   return outstr;
}

function showIdealformTooltip(obj) {
    obj.find(".tooltip").show()
}

function hideIdealformTooltip(obj) {
    obj.find(".tooltip").hide()
}

function getSortedKeys(obj, index) {
    var keys = []; for (var key in obj) keys.push(key);
    return keys.sort(function(a,b){return obj[a][index]-obj[b][index]});
}

//*****************************************************************************
// called when Save Settings is clicked
//*****************************************************************************
function saveSettings(){

    var DisplayStr = "Save settings? Are you sure?";
    var DisplayStrAnswer = false;
    var DisplayStrButtons = {
        NO: {
          text: 'Cancel',
          type: 'button',
          className: 'vex-dialog-button-secondary',
          click: function noClick () {
            DisplayStrAnswer = false
            this.close()
          }
        },
        YES: {
          text: 'OK',
          type: 'submit',
          className: 'vex-dialog-button-primary',
          click: function yesClick () {
            DisplayStrAnswer = true
          }
        }
    }

    vex.dialog.open({
        unsafeMessage: DisplayStr,
        overlayClosesOnClick: false,
        buttons: [
           DisplayStrButtons.NO,
           DisplayStrButtons.YES
        ],
        onSubmit: function(e) {
           if (DisplayStrAnswer) {
             DisplayStrAnswer = false; // Prevent recursive calls.
             e.preventDefault();
             saveSettingsJSON();
             var DisplayStr1 = 'Saving...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){
                vex.closeAll();
                if ($('#sitename').val() != $('#sitename').attr('oldValue')) { myGenerator["sitename"] = $('#sitename').val(); SetHeaderValues(); }
                if ($('#nominalRPM').val() != $('#nominalRPM').attr('oldValue')) { myGenerator["nominalRPM"] = $('#nominalRPM').val(); }
                if ($('#nominalfrequency').val() != $('#nominalfrequency').attr('oldValue')) { myGenerator["nominalfrequency"] = $('#sitename').val(); }
                if ($('#nominalKW').val() != $('#nominalKW').attr('oldValue')) { myGenerator["nominalKW"] = $('#nominalKW').val(); }
                if ($('#fueltype').val() != $('#fueltype').attr('oldValue')) { myGenerator["fueltype"] = $('#fueltype').val(); }
                if ($('#favicon').val() != $('#favicon').attr('oldValue')) { changeFavicon($('#favicon').val()); }
                if (($('#enhancedexercise').prop('checked')  === true ? "true" : "false") != $('#enhancedexercise').attr('oldValue')) { myGenerator['EnhancedExerciseEnabled'] = ($('#enhancedexercise').prop('checked')  === true ? "true" : "false") }
             }, 10000);
           }
        }
    })
}

function saveSettingsJSON() {
    try {
        var fields = {};

        $('#formSettings input').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = (($(this).attr('type') == "checkbox") ? ($(this).prop('checked') === true ? "true" : "false") : $(this).val());
            if (oldValue != currentValue) {
               fields[$(this).attr('name')] = currentValue;
               $(this).attr('oldValue', currentValue);
            }
        });
        $('#formSettings select').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = $(this).val();
            if (oldValue != currentValue) {
               fields[$(this).attr('name')] = currentValue;
               $(this).attr('oldValue', currentValue);
            }
        });

        // save settings
        var url = baseurl.concat("setsettings");
        $.getJSON(  url,
                    {setsettings: $.param(fields)},
                    function(result){
        });

    } catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}

//*****************************************************************************
// DisplayRegisters - Shows the raw register data.
//*****************************************************************************
var fadeOffTime = 60;
function DisplayRegistersFull()
{
    var outstr = 'Live Register View:<br><br>';
    outstr += '<center><table width="80%" border="0"><tr>';

    $.each(Object.keys(regHistory["updateTime"]).sort(), function(i, reg_key) {
        if ((i % 4) == 0){
        outstr += '</tr><tr>';
        }

        var reg_val = regHistory["_10m"][reg_key][0];

        outstr += '<td width="25%" class="registerTD">';
        outstr +=     '<table width="100%" heigth="100%" id="val_'+reg_key+'">';
        outstr +=     '<tr><td align="center" class="registerTDtitle">' + BaseRegistersDescription[reg_key] + '</td></tr>';
        outstr +=     '<tr><td align="center" class="registerTDsubtitle">(' + reg_key + ')</td></tr>';
        outstr +=     '<tr><td align="center" class="tooltip registerChart" id="content_'+reg_key+'">';
        outstr +=        ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
        outstr +=        ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+parseInt(reg_val.substring(0,2), 16)+':'+parseInt(reg_val.substring(2,4), 16)+'</span>');
        outstr +=     '</td></tr>';
        outstr +=     '</table>';
        outstr += '</td>';
    });
    if ((regHistory["_10m"].length % 4) > 0) {
      for (var i = (regHistory["_10m"].length % 4); i < 4; i++) {
         outstr += '<td width="25%" class="registerTD"></td>';
      }
    }
    outstr += '</tr></table>';
    outstr += '<br><img id="print10" class="print10 printButton" onClick="printRegisters(10)" src="images/transparent.png" width="36px" height="36px">&nbsp;&nbsp;&nbsp;';
    outstr += '<img id="print60" class="print60 printButton" onClick="printRegisters(60)" src="images/transparent.png" width="36px" height="36px">&nbsp;&nbsp;&nbsp;';
    outstr += '<img id="print24" class="print24 printButton" onClick="printRegisters(24)" src="images/transparent.png" width="36px" height="36px"><br>';
    outstr += '</center>';

    $("#mydisplay").html(outstr);
    UpdateRegistersColor();
    $('.registerChart').tooltipster({
        minWidth: '280px',
        maxWidth: '280px',
        animation: 'fade',
        updateAnimation: 'fade',
        contentAsHTML: 'true',
        delay: 100,
        animationDuration: 200,
        interactive: true,
        content: '<div class="regHistoryCanvas"></div>',
        side: ['top', 'left'],
        functionReady: function(instance, helper) {
            var regId = $(helper.origin).attr('id').replace(/content_/g, '');
            instance.content('<div class="regHistoryCanvas"><table><tr><td class="regHistoryCanvasTop">' +
                             '  <div id="'+regId+'_graph1" class="regHistoryPlot"></div>' +
                             '  <div id="'+regId+'_graph2" class="regHistoryPlot"></div>' +
                             '  <div id="'+regId+'_graph3" class="regHistoryPlot"></div>' +
                             '</td></tr><tr><td class="regHistoryCanvasBottom"><center>' +
                             '  <div class="regHistory selection" onClick="$(\'.regHistory\').removeClass(\'selection\');$(this).addClass(\'selection\');$(\'#'+regId+'_graph1\').css(\'display\', \'block\');$(\'#'+regId+'_graph2\').css(\'display\', \'none\');$(\'#'+regId+'_graph3\').css(\'display\', \'none\');">10 min</div> | ' +
                             '  <div class="regHistory" onClick="$(\'.regHistory\').removeClass(\'selection\');$(this).addClass(\'selection\');$(\'#'+regId+'_graph1\').css(\'display\', \'none\');$(\'#'+regId+'_graph2\').css(\'display\', \'block\');$(\'#'+regId+'_graph3\').css(\'display\', \'none\');">1 hr</div> | ' +
                             '  <div class="regHistory" onClick="$(\'.regHistory\').removeClass(\'selection\');$(this).addClass(\'selection\');$(\'#'+regId+'_graph1\').css(\'display\', \'none\');$(\'#'+regId+'_graph2\').css(\'display\', \'none\');$(\'#'+regId+'_graph3\').css(\'display\', \'block\');">24 hr</div>' +
                             '</center></td></tr></table></div>');
            var plot_data1 = [];
            var plot_data2 = [];
            var plot_data3 = [];
            for (var i = 120; i >= 0; --i) {
               if (regHistory["_10m"][regId].length > i)
                   plot_data1.push([-i/12, parseInt(regHistory["_10m"][regId][i], 16)]);
               if (regHistory["_60m"][regId].length > i)
                   plot_data2.push([-i/2, parseInt(regHistory["_60m"][regId][i], 16)]);
               if (regHistory["_24h"][regId].length > i)
                   plot_data3.push([-i/5, parseInt(regHistory["_24h"][regId][i], 16)]);
            }
            var plot1 = $.jqplot(regId+'_graph1', [plot_data1], {
                               axesDefaults: { tickOptions: { textColor: '#999999', fontSize: '8pt' }},
                               axes: { xaxis: { label: "Time (Minutes ago)", labelOptions: { fontFamily: 'Arial', textColor: '#AAAAAA', fontSize: '9pt' }, min:-10, max:0 } }
                             });
            var plot2 = $.jqplot(regId+'_graph2', [plot_data2], {
                               axesDefaults: { tickOptions: { textColor: '#999999', fontSize: '8pt' }},
                               axes: { xaxis: { label: "Time (Minutes ago)", labelOptions: { fontFamily: 'Arial', textColor: '#AAAAAA', fontSize: '9pt' }, min:-60, max:0 } }
                             });
            var plot3 = $.jqplot(regId+'_graph3', [plot_data3], {
                               axesDefaults: { tickOptions: { textColor: '#999999', fontSize: '8pt' }},
                               axes: { xaxis: { label: "Time (Hours ago)", labelOptions: { fontFamily: 'Arial', textColor: '#AAAAAA', fontSize: '9pt' }, min:-24, max:0 } }
                             });
            $('#'+regId+'_graph2').css('display', 'none');
            $('#'+regId+'_graph3').css('display', 'none');
        }
    });

}

function UpdateRegisters(init, printToScreen)
{
    if (init) {
      var now = new moment();
      regHistory["historySince"] = now.format("D MMMM YYYY H:mm:ss");
      regHistory["count_60m"] = 0;
      regHistory["count_24h"] = 0;
    }

    var url = baseurl.concat("registers_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(RegData){
        processAjaxSuccess();

        $.each(RegData.Registers["Base Registers"], function(i, item) {
            var reg_key = Object.keys(item)[0]
            var reg_val = item[Object.keys(item)[0]];

            if ((init) || (regHistory["_10m"][reg_key] == undefined)) {
                regHistory["updateTime"][reg_key] = 0;
                regHistory["_10m"][reg_key] = [reg_val];
                regHistory["_60m"][reg_key] = [reg_val, reg_val];
                regHistory["_24h"][reg_key] = [reg_val, reg_val];
            } else {
               if (reg_val != regHistory["_10m"][reg_key][0]) {
                  regHistory["updateTime"][reg_key] = new Date().getTime();

                  if (printToScreen) {
                    var outstr  = ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
                        outstr += ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+parseInt(reg_val.substring(0,2), 16)+':'+parseInt(reg_val.substring(2,4), 16)+'</span>');
                    $("#content_"+reg_key).html(outstr);
                  }
               }
            }
            regHistory["_10m"][reg_key].unshift(reg_val);
            if  (regHistory["_10m"][reg_key].length > 120) {
               regHistory["_10m"][reg_key].pop  // remove the last element
            }

            if (regHistory["count_60m"] >= 12) {
               var min = 0;
               var max = 0;
               for (var i = 1; i <12; i++) {
                   if (regHistory["_10m"][reg_key][i] > regHistory["_10m"][reg_key][max])
                      max = i;
                   if (regHistory["_10m"][reg_key][i] < regHistory["_10m"][reg_key][min])
                      min = i;
               }
               regHistory["_60m"][reg_key].unshift(regHistory["_10m"][reg_key][((min > max) ? min : max)], regHistory["_10m"][reg_key][((min > max) ? max : min)]);

               if  (regHistory["_60m"][reg_key].length > 120)
                 regHistory["_60m"][reg_key].splice(-2, 2);  // remove the last 2 element
            }

            if (regHistory["count_24h"] >= 288) {
               var min = 0;
               var max = 0;
               for (var i = 1; i <24; i++) {
                   if (regHistory["_60m"][reg_key][i] > regHistory["_60m"][reg_key][max])
                      max = i;
                   if (regHistory["_60m"][reg_key][i] < regHistory["_60m"][reg_key][min])
                      min = i;
               }
               regHistory["_24h"][reg_key].unshift(regHistory["_60m"][reg_key][((min > max) ? min : max)], regHistory["_60m"][reg_key][((min > max) ? max : min)]);

               if  (regHistory["_24h"][reg_key].length > 120)
                 regHistory["_24h"][reg_key].splice(-2, 2);  // remove the last 2 element
            }
        });
        regHistory["count_60m"] = ((regHistory["count_60m"] >= 12) ? 0 : regHistory["count_60m"]+1);
        regHistory["count_24h"] = ((regHistory["count_24h"] >= 288) ? 0 : regHistory["count_24h"]+1);

        if (printToScreen)
           UpdateRegistersColor();
    }});
}

function UpdateRegistersColor() {
    var CurrentTime = new Date().getTime();
    $.each(regHistory["updateTime"], function( reg_key, update_time ){
        var difference = CurrentTime - update_time;
        var secondsDifference = Math.floor(difference/1000);
        if ((update_time > 0) && (secondsDifference >= fadeOffTime)) {
           $("#content_"+reg_key).css("background-color", "#AAAAAA");
           $("#content_"+reg_key).css("color", "red");
        } else if ((update_time > 0) && (secondsDifference <= fadeOffTime)) {
           var hexShadeR = toHex(255-Math.floor(secondsDifference*85/fadeOffTime));
           var hexShadeG = toHex(Math.floor(secondsDifference*170/fadeOffTime));
           var hexShadeB = toHex(Math.floor(secondsDifference*170/fadeOffTime));
           $("#content_"+reg_key).css("background-color", "#"+hexShadeR+hexShadeG+hexShadeB);
           $("#content_"+reg_key).css("color", "black");
        }
    });
}

function printRegisters (type) {
    var plots = [];
    var data, labelMin, labelText, labelTitle;
    var pageHeight = 20;
    var rowHeight = 15;
    var dataDivider;

    if (type == 10) {
      data = regHistory["_10m"];
      labelTitle = "last 10 minutes";
      labelMin = -10;
      labelText = "Time (Minutes ago)";
      dataDivider = 12;
    } else if (type == 60) {
      labelTitle = "last 1 hour";
      data = regHistory["_60m"];
      labelMin = -60;
      labelText = "Time (Minutes ago)";
      dataDivider = 2;
    } else if (type == 24) {
     labelTitle = "last 24 hours";
      data = regHistory["_24h"];
      labelMin = -24;
      labelText = "Time (hours ago)";
      dataDivider = 5;
    }


    $('<div id="printRegisterFrame" style="width:1000px"></div>').appendTo("#mydisplay");

    var now = new moment();
    var outstr = '<br><center><h1>Generator Registers for '+labelTitle+'</h1><br>';
    outstr += '<h2>As of: '+now.format("D MMMM YYYY H:mm:ss")+'<br><small>(data avilable since: '+regHistory["historySince"]+')</small></h2><br>';
    outstr += '<table width="1000px" border="0"><tr>';

    $.each(Object.keys(data).sort(), function(i, reg_key) {
        var max=data[reg_key][0];
        var min=data[reg_key][0];
        for (var j = 120; j >= 0; --j) {
           if (data[reg_key][j] > max)
              max = data[reg_key][j];
           if (data[reg_key][j] < min)
              min = data[reg_key][j];
        }

        if ((i % 3) == 0){
          pageHeight += rowHeight;
          if (pageHeight < 100) {
             outstr += '</tr><tr>';
          } else {
             outstr += '</tr></table><div class="pagebreak"> </div><table width="1000px" border="0"><tr>';
             pageHeight = 0;
          }
          rowHeight = 15;
        }

        var reg_val = data[reg_key][0];

        outstr += '<td width="33%" class="printRegisterTD">';
        outstr +=     '<table width="333px" heigth="100%" id="val_'+reg_key+'">';
        outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">' + reg_key + '</td></tr>';
        outstr +=     '<tr><td align="center" class="printRegisterTDtitle">' + BaseRegistersDescription[reg_key] + '</td></tr>';
        outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">Current Value: ' + regHistory["_10m"][reg_key][0] + '</td></tr>';
        if (min != max) {
          outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">Minimum Value: '+min+'<br>Maximum Value: '+max+'</td></tr>';
          outstr +=     '<tr><td align="center" class="regHistoryPlotCell"><div id="printPlot_'+reg_key+'"></div></td></tr>';
          plots.push(reg_key);
          rowHeight = 45;
        } else {
          outstr +=     '<tr><td align="center" class="printRegisterTDvalMedium">no change</td></tr>';
        }
        outstr +=     '</table>';
        outstr += '</td>';
    });
    if ((Object.keys(data).length % 3) > 0) {
      for (var i = (Object.keys(data).length % 3); i < 3; i++) {
          outstr += '<td width="333px" class="printRegisterTD"></td>';
       }
    }
    outstr += '</tr></table></center>';
    $("#printRegisterFrame").html(outstr);


    for (var i = 0; i < plots.length; i++) {
        var reg_key = plots[i];
        var plot_data = [];
        for (var j = 120; j >= 0; --j) {
           if (data[reg_key].length > j)
              plot_data.push([-j/dataDivider, parseInt(data[reg_key][j], 16)]);
        }
        var plot = $.jqplot('printPlot_'+reg_key, [plot_data], {
                               axesDefaults: { tickOptions: { textColor: '#000000', fontSize: '8pt' }},
                               axes: { xaxis: { label: labelText, labelOptions: { fontFamily: 'Arial', textColor: '#000000', fontSize: '9pt' }, min: labelMin, max:0 } }
                             });
    }

    $("#printRegisterFrame").printThis({canvas: true, importCSS: false, loadCSS: "css/print.css", pageTitle:"Genmon Registers", removeScripts: true});
    setTimeout(function(){ $("#printRegisterFrame").remove(); }, 1000);
}

function toHex(d) {
    return  ("0"+(Number(d).toString(16))).slice(-2).toUpperCase()
}

//*****************************************************************************
//  called when menu is clicked
//*****************************************************************************
function MenuClick(target)
{

        RemoveClass();  // remove class from menu items
        // add class active to the clicked item
        target.find("a").addClass(GetCurrentClass());
        // update the display
        menuElement = target.attr("id");
        window.scrollTo(0,0);
        switch (menuElement) {
            case "outage":
                GetDisplayValues(menuElement);
                break;
            case "monitor":
                DisplayMonitor();
                break;
            case "logs":
                DisplayLogs();
                break;
            case "status":
                DisplayStatusFull();
                break;
            case "maint":
                DisplayMaintenance();
                break;
            case "notifications":
                DisplayNotifications();
                break;
            case "settings":
                DisplaySettings();
                break;
            case "registers":
                DisplayRegistersFull();
                break;
            default:
                break;
        }

}

//*****************************************************************************
// removes the current class from the menu anchor list
//*****************************************************************************
function RemoveClass() {
    $("li").find("a").removeClass(GetCurrentClass());
}

//*****************************************************************************
// returns current CSS class for menu
//*****************************************************************************
function GetCurrentClass() {
    return currentClass
}

//*****************************************************************************
// escapeRegExp - helper function for replaceAll
//*****************************************************************************
function escapeRegExp(str) {
    return str.replace(/([.*+?^=!:${}()|\[\]\/\\])/g, "\\$1");
}

//*****************************************************************************
// javascript implementation of java function replaceAll
//*****************************************************************************
function replaceAll(str, find, replace) {
    return str.replace(new RegExp(escapeRegExp(find), 'g'), replace);
}

//*****************************************************************************
// GetDisplayValues - updates display based on menu selection (command)
//*****************************************************************************
function GetDisplayValues(command)
{
    var url = baseurl.concat(command);
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        // replace /n with html friendly <br/>
        var outstr = replaceAll(result,'\n','<br/>')
        // replace space with html friendly &nbsp
        outstr = replaceAll(outstr,' ','&nbsp')
        $("#mydisplay").html(outstr);

   }});

    return;
}

//*****************************************************************************
// GetGeneratorModel - Get the current Generator Model and kW Rating
//*****************************************************************************
function GetGeneratorModel()
{
    url = baseurl.concat("start_info_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
      processAjaxSuccess();

      myGenerator = result;
      myGenerator["OldExerciseParameters"] = [-1,-1,-1,-1,-1,-1];
      SetHeaderValues();
    }});
}

//*****************************************************************************
// SetHeaderValues - updates header to display site name
//*****************************************************************************
function SetHeaderValues()
{
   var HeaderStr = '<table border="0" width="100%" height="30px"><tr><td width="30px"></td><td width="90%">Generator Monitor at ' + myGenerator["sitename"] + '</td><td width="30px"><img id="registers" class="registers" src="images/transparent.png" width="20px" height="20px"></td></tr></table>';
   $("#myheader").html(HeaderStr);
   $("#registers").on('click',  function() {  MenuClick($(this));});
}


//*****************************************************************************
// Set Favicon
//*****************************************************************************

document.head = document.head || document.getElementsByTagName('head')[0];

function changeFavicon(src) {
   var link = document.createElement('link'),
       oldLink = document.getElementById('dynamic-favicon');
   link.id = 'dynamic-favicon';
   link.rel = 'shortcut icon';
   link.href = src;
   if (oldLink) {
       document.head.removeChild(oldLink);
   }
   document.head.appendChild(link);
}

function SetFavIcon()
{
    url = baseurl.concat("getfavicon");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        changeFavicon(result);
    }});
    return
}

//*****************************************************************************
// GetkWHistory - Get the history of the kW generation
//*****************************************************************************
function GetkWHistory()
{
    url = baseurl.concat("power_log_json");
    $.ajax({dataType: "json", url: url, timeout: 20000, error: processAjaxError, data: "power_log_json: 10000", success: function(result){
        processAjaxSuccess();
        kwHistory["data"] = result.map(function(itm) { return [moment(itm[0], 'MM/DD/YY HH:mm:ss').format('YYYY-MM-DD HH:mm:ss'), parseFloat(itm[1])]; }).sort().reverse();
    }});
}

//*****************************************************************************
// GetRegisterNames - Get the current Generator Model and kW Rating
//*****************************************************************************
function GetRegisterNames()
{
    url = baseurl.concat("getreglabels");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
      processAjaxSuccess();

      BaseRegistersDescription = result;
    }});
}

//*****************************************************************************
// Show nice Alert Box (modal)
//*****************************************************************************
function GenmonAlert(msg)
{
       vex.closeAll();
       vex.dialog.alert({ unsafeMessage: '<table><tr><td valign="middle" width="200px" align="center"><img class="alert_large" src="images/transparent.png" width="64px" height="64px"></td><td valign="middle" width="70%">'+msg+'</td></tr></table>'});
}

//*****************************************************************************
// UpdateDisplay
//*****************************************************************************
function UpdateDisplay()
{
    if (menuElement == "registers") {
        UpdateRegisters(false, true);
    } else if (menuElement == "status") {
        DisplayStatusUpdate();
    } else if (menuElement == "maint") {
        DisplayMaintenanceUpdate();
    } else if (menuElement == "logs") {
        DisplayLogs();
    } else if (menuElement == "monitor") {
        DisplayMonitor();
    } else if ((menuElement != "settings") && (menuElement != "notifications")) {
        GetDisplayValues(menuElement);
    }

    if (menuElement != "registers") {  // refresh the registers every time to keep history
        UpdateRegisters(false, false);
    }
}

//*****************************************************************************
// GetBaseStatus - updates menu background color based on the state of the generator
//*****************************************************************************
function GetBaseStatus()
{
    url = baseurl.concat("gui_status_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        myGenerator['ExerciseDay'] = result['ExerciseInfo']['Day'];
        myGenerator['ExerciseHour'] = result['ExerciseInfo']['Hour'];
        myGenerator['ExerciseMinute'] = result['ExerciseInfo']['Minute'];
        myGenerator['QuietMode'] = result['ExerciseInfo']['QuietMode'];
        myGenerator['ExerciseFrequency'] = result['ExerciseInfo']['Frequency'];
        myGenerator['EnhancedExerciseEnabled'] = ((result['ExerciseInfo']['EnhancedExerciseMode'] === "False") ? false : true);

        if ((menuElement == "status") && (gauge.length > 0)) {
           for (var i = 0; i < result.tiles.length; ++i) {
             switch (myGenerator["tiles"][i].type) {
                case "gauge":
                   gauge[i].set(result.tiles[i].value); 
                   $("#text"+i).html(result.tiles[i].text);
                   break;
                case "graph":
                   if (kwHistory["data"].length > 0) { /// Otherwise initialization has not finished

                      if ((result.tiles[i].value != 0) && (kwHistory["data"][0][1] == 0)) {
                         // make sure we add a 0 before the graph goes up, to ensure the interpolation works
                         kwHistory["data"].unshift([(new moment()).add(-2, "s").format("YYYY-MM-DD HH:mm:ss"), 0]);
                      }
  
                      if ((result.tiles[i].value != 0) || (kwHistory["data"][0][1] != 0)) {
                         kwHistory["data"].unshift([(new moment()).format("YYYY-MM-DD HH:mm:ss"), result.tiles[i].value]);
                      }
                      if  (kwHistory["data"].length > 10000) {
                         kwHistory["data"].pop  // remove the last element
                      }

                      if ((menuElement == "status") && (myGenerator["PowerGraph"] == true)) {
                         printKwPlot(result.tiles[i].value);
                      }
                   }
                   break;
             }
           }
        }

        if (result['SystemHealth'].toUpperCase() != "OK") {
          myGenerator['SystemHealth'] = true;
          var tempMsg = '<b><span style="font-size:14px">GENMON SYSTEM WARNING</span></b><br>'+result['SystemHealth'];
          $("#footer").addClass("alert");
          $("#ajaxWarning").show(400);
          $('#ajaxWarning').tooltipster('content', tempMsg);
        } else if (result['UnsentFeedback'].toLowerCase() == "true") {
          myGenerator['UnsentFeedback'] = true;
          var tempMsg = '<b><span style="font-size:14px">UNKNOWN ERROR OCCURED</span></b><br>The software had encountered unknown status from<br>your generator.<br>This status could be used to improve the software.<br>To send the contents of your generator registers to<br>the software developer please enable "Auto Feedback"<br>on the Settings page.';
          $("#footer").addClass("alert");
          $("#ajaxWarning").show(400);
          $('#ajaxWarning').tooltipster('content', tempMsg);
        } else { // Note - this claus only get's executed if the ajax connection worked. Hence no need to check ajaxErrors["errorCount"]
          myGenerator['UnsentFeedback'] = false;
          myGenerator['SystemHealth'] = false;
          $("#footer").removeClass("alert");
          $("#ajaxWarning").hide(400);
        }

        baseState = result['basestatus'];
        // active, activealarm, activeexercise
        if (baseState != currentbaseState) {

            // it changed so remove the old class
            RemoveClass();

            if(baseState === "READY")
                currentClass = "active";
            if(baseState === "ALARM")
                currentClass = "activealarm";
            if(baseState === "EXERCISING")
                currentClass = "activeexercise";
            if(baseState === "RUNNING")
                currentClass = "activerun";
            if(baseState === "RUNNING-MANUAL")
                currentClass = "activerunmanual";
            if(baseState === "SERVICEDUE")
                currentClass = "activeservice";
            if(baseState === "OFF")
                currentClass = "activeoff";
            if(baseState === "MANUAL")
                currentClass = "activemanual";

            currentbaseState = baseState;
            // Added active to selected class
            $("#"+menuElement).find("a").addClass(GetCurrentClass());
        }

        prevStatusValues = result;
        return
   }});
   
   return
}
