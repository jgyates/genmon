
// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var switchState = "Auto";        // updated on a time
var currentClass = "active";    // CSS class for menu color
var menuElement = "status";
var ajaxErrors = {errorCount: 0, lastSuccessTime: moment(), log: ""};
var windowActive = true;
var latestVersion = "";
var lowbandwidth = false;
var resizeTimeout;

var myGenerator = {sitename: "", nominalRPM: 3600, nominalfrequency: 60, Controller: "", model: "", nominalKW: 22, fueltype: "", UnsentFeedback: false, SystemHealth: false, EnhancedExerciseEnabled: false, LoginActive: false, OldExerciseParameters:[-1,-1,-1,-1,-1,-1]};
var regHistory = {updateTime: {}, _10m: {}, _60m: {}, _24h: {}, historySince: "", count_60m: 0, count_24h: 0};
var kwHistory = {data: [], plot:"", kwDuration: "h", tickInterval: "10 minutes", formatString: "%H:%M", defaultPlotWidth: 4, oldDefaultPlotWidth: 4};
var prevStatusValues = {};
var pathname = window.location.href.split("/")[0].split("?")[0];
var baseurl = pathname.concat("cmd/");
var DaysOfWeekArray = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];
var MonthsOfYearArray = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
var BaseRegistersDescription = {};
var QR_Code_URL = "";

vex.defaultOptions.className = 'vex-theme-os'


//*****************************************************************************
var UAbrowser = (function(){
  var test = function(regexp) { return regexp.test(window.navigator.userAgent);}
  switch(true){
    case test(/edge/i): return "edge";
    case test(/opr/i) && (!!window.opr || !!window.opera): return "opera";
    case test(/chrome/i) && !!window.chrome: return "chrome";
    case test(/trident/i) : return "ie";
    case test(/firefox/i) : return "firefox";
    case test(/safari/i): return "safari";
    default: return "other";
  }
})();

//*****************************************************************************
function isMobileBrowser() {
 if( navigator.userAgent.match(/Android/i)
 || navigator.userAgent.match(/webOS/i)
 || navigator.userAgent.match(/iPhone/i)
 || navigator.userAgent.match(/iPad/i)
 || navigator.userAgent.match(/iPod/i)
 || navigator.userAgent.match(/BlackBerry/i)
 || navigator.userAgent.match(/Windows Phone/i)
 ){
    return true;
  }
 else {
    return false;
  }
}
// console.log(UAbrowser)

//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
var script_tag = document.getElementById('genmon.js');
if (script_tag != undefined && script_tag.getAttribute("data-type") == "lowbandwidth") {
  lowbandwidth = true;
}
GetStartupInfo();
GetBaseStatus();
SetFavIcon();
GetkWHistory();
GetRegisterNames();
$(document).ready(function() {
    UpdateRegisters(true, false);
    setInterval(GetBaseStatus, 3000);       // Called every 3 sec
    setInterval(UpdateDisplay, 5000);       // Called every 5 sec
    CreateMenuWhenReady();
    resizeDiv();
});

//*****************************************************************************
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

//*****************************************************************************
function processAjaxError(xhr, ajaxOptions, thrownError) {
    // alert(xhr.status);
    // alert(thrownError);
    ajaxErrors["errorCount"]++;
    if (ajaxErrors["errorCount"]>5) {
      var lastSuccessTime = "N/A"
      if (ajaxErrors["lastSuccessTime"] != undefined) {
         lastSuccessTime = ajaxErrors["lastSuccessTime"].format("H:mm:ss")
      }
      var tempMsg = '<b><span style="font-size:14px">Disconnected from server</span></b><br>'+ajaxErrors["errorCount"]+' messages missed since '+lastSuccessTime+"</b><br><br>"+((ajaxErrors["log"].length>500) ? ajaxErrors["log"].substring(0, 500)+"<br>[...]" : ajaxErrors["log"]);
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

     if ((menuElement == "status") && ($('.packery').length > 0) && (lowbandwidth == false)) {
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
//*****************************************************************************
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
//  Read QueryString Parameter
//*****************************************************************************
function GetQueryStringParams(sParam) {
    var sPageURL = window.location.search.substring(1);
    var sURLVariables = sPageURL.split('&');
    for (var i = 0; i < sURLVariables.length; i++) {
      var sParameterName = sURLVariables[i].split('=');
      if (sParameterName[0] == sParam)
        return sParameterName[1];
        }
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
// Create Main Menu
//*****************************************************************************

function CreateMenuWhenReady() {
    if(myGenerator["pages"] == undefined) {//we want it to match
        setTimeout(CreateMenuWhenReady, 50);//wait 50 millisecnds then recheck
        return false;
    }
    CreateMenu();
    return true;
}

//*****************************************************************************
function CreateMenu() {
    var outstr = '';

    SetHeaderValues();
    $("#footer").html('<table border="0" width="100%" height="30px"><tr><td width="5%"><img class="tooltip alert_small" id="ajaxWarning" src="images/transparent.png" height="28px" width="28px" style="display: none;"></td><td width="90%"><a href="https://github.com/jgyates/genmon" target="_blank">GenMon Project on GitHub</a></td><td width="5%"></td></tr></table>');
    $('#ajaxWarning').tooltipster({minWidth: '280px', maxWidth: '480px', animation: 'fade', updateAnimation: 'null', contentAsHTML: 'true', delay: 100, animationDuration: 200, side: ['top', 'left'], content: "No Communication Errors occured"});

    if (myGenerator["pages"]["status"] == true)
       outstr += '<li id="status"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="status" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Status</td></tr></table></a></li>';
    if (myGenerator["pages"]["maint"] == true)
       outstr += '<li id="maint"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="maintenance" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Maintenance</td></tr></table></a></li>';
    if (myGenerator["pages"]["outage"] == true)
       outstr += '<li id="outage"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="outage" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Outage</td></tr></table></a></li>';
    if (myGenerator["pages"]["logs"] == true)
       outstr += '<li id="logs"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="log" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Logs</td></tr></table></a></li>';
    if (myGenerator["pages"]["monitor"] == true)
       outstr += '<li id="monitor"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="monitor" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Monitor</td></tr></table></a></li>';
    if (myGenerator["pages"]["notifications"] == true)
       outstr += '<li id="notifications"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="notifications" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Notifications</td></tr></table></a></li>';
    if (myGenerator["pages"]["maintlog"] == true)
       outstr += '<li id="journal"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="journal" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Service Journal</td></tr></table></a></li>';
    if (myGenerator["pages"]["settings"] == true)
       outstr += '<li id="settings"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="settings" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Settings</td></tr></table></a></li>';
    if (myGenerator["pages"]["addons"] == true)
       outstr += '<li id="addons"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="addon" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Add-Ons</td></tr></table></a></li>';
    if (myGenerator["pages"]["about"] == true)
       outstr += '<li id="about"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img class="about" src="images/transparent.png" width="20px" height="20px"></td><td valign="middle">&nbsp;About</td></tr></table></a></li>';

    $("#navMenu").html('<ul>' + outstr + '</ul>');
    $("li").on('click',  function() {  MenuClick($(this).attr("id"));});

    var page = GetQueryStringParams('page');

    MenuClick(((page != undefined) && (jQuery.inArray( page, ["status", "maint", "outage", "logs", "monitor", "notifications", "journal", "settings", "addons", "about"] ))) ? page : "status");

    $(".loader").removeClass("is-active");
}

//*****************************************************************************
// DisplayStatusFull - show the status page at the beginning or when switching
// from another page
//*****************************************************************************
var gauge = [];

function DisplayStatusFull() {
    var vpw = $(window).width();
    var gridWidth = Math.round((vpw-240)/190);
        gridWidth = (gridWidth < 1) ? 1 : gridWidth;
    kwHistory["defaultPlotWidth"] = ((gridWidth > 4) ? 4 : (gridWidth < 1) ? 1 : gridWidth);
    kwHistory["oldDefaultPlotWidth"] = kwHistory["defaultPlotWidth"];

    // This is a hack to work around mobile safari issue that makes the gauge text
    // display incorrectly on redraw
    var outstr = '<br>';
    var CRstr = '<br>';
    if ((UAbrowser == "safari") && (isMobileBrowser()) && (gauge.length != 0)) {
      CRstr = '';
    }

    if (lowbandwidth == false) {
      outstr += '<center><div class="packery">';
      for (var i = 0; i < myGenerator["tiles"].length; ++i) {
         switch (myGenerator["tiles"][i].type) {
           case "gauge":
             if (myGenerator["tiles"][i].subtype == "fuel") {
               outstr += '<div id="fuelField_'+i+'" class="grid-item gaugeField">'+CRstr+myGenerator["tiles"][i].title+'<br><div style="display: inline-block; width:100%; height:65%; position: relative;"><canvas class="gaugeCanvas" id="gauge'+i+'_bg" style="height: 100%; position: absolute; left: 0; top: 0; z-index: 1;"></canvas><canvas class="gaugeCanvas" id="gauge'+i+'" style="height: 100%; position: absolute; left: 0; top: 0; z-index: 0;"></canvas></div><br><div id="text'+i+'" class="gaugeDiv"></div></div>';
             } else {
               outstr += '<div id="gaugeField_'+i+'" class="grid-item gaugeField">'+CRstr+myGenerator["tiles"][i].title+'<br><canvas class="gaugeCanvas" id="gauge'+i+'"></canvas><br><div id="text'+i+'" class="gaugeDiv"></div></div>';
             }
             break;
           case "graph":
             outstr += '<div id="plotField" class="grid-item plotField"><br>'+myGenerator["tiles"][i].title+'<br><div id="plotkW" class="kwPlotCanvas"></div><span class="kwPlotText">Time (<div class="kwPlotSelection selection" id="1h">1 hour</div> | <div class="kwPlotSelection" id="1d">1 day</div> | <div class="kwPlotSelection" id="1w">1 week</div> | <div class="kwPlotSelection" id="1m">1 month</div>)</span></div>';
             break;
         }
      }
      outstr += '</div></center><br>';
    }
    $("#mydisplay").html(outstr + '<div style="clear:both" id="statusText"></div>');

    if (lowbandwidth == false) {
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
                  gauge[curr_i] = createFuel($("#gauge"+curr_i), $("#text"+curr_i), $("#gauge"+curr_i+"_bg"), myGenerator["tiles"][curr_i].maximum);
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
             if (myGenerator["tiles"][i].subtype == "fuel") {
                gauge[i] = createFuel($("#gauge"+i), $("#text"+i), $("#gauge"+i+"_bg"), myGenerator["tiles"][i].maximum);
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
    }

    var url = baseurl.concat("status_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        $("#statusText").html(json2html(result, "", "root"));
    }});
    return;
}
//*****************************************************************************
function getItem(json, parentkey)  {

  var outstr = '';
  if (typeof json === 'string') {
    outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div><br>';
  } else if (typeof json === 'number') {
    outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json + '</div><br>';
  } else if (typeof json === 'boolean') {
    outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">' + json + '</div><br>';
  } else if (json === null) {
    outstr += '<div class="jsonVal" id="'+parentkey.replace(/ /g, '_')+'">null</div><br>';
  } else {
    console.log("unexpected type in getItem: " + (typeof json));
  }
  return outstr
}
//*****************************************************************************
function json2html(json, indent, parentkey) {

    if ((typeof json === 'string') || (typeof json === 'number') || (typeof json === 'boolean') || (typeof json === null)) {
        console.log("unexpected type in json2html (1): " + (typeof json));
        return ""
    }
    var outstr = '';
    if (typeof json === 'object') {
      var key_count = Object.keys(json).length;
      if (key_count <= 0) {
        console.log("key count invalid in json2html: " + key_count);
        return outstr
      }
      for (var key in json) {
        if (json.hasOwnProperty(key) == false) {
          console.log("no property of key in json2html: " + key);
          return outstr
        }
        if (json[key] === null) {
          outstr += indent + key + ' : ' + getItem(json[key], key); //parentkey);
        } else if (json[key].constructor === Array) {
            if (json[key].length > 0) {
              outstr += "<br>" + indent + key + ' :<br>';   // + json2html(json[key], indent, key);
              for (var i = 0; i < json[key].length; ++i) {
                if (typeof json[key][i] === 'object') {
                  outstr +=  json2html(json[key][i], indent + "&nbsp;&nbsp;&nbsp;&nbsp;", parentkey+"_"+i);
                } else {
                  outstr += indent + "&nbsp;&nbsp;&nbsp;&nbsp;" +  getItem(json[key][i], key);
                }
              }
            }
        } else if (typeof json[key] === 'object') {
           outstr += "<br>" + indent + key + ' :<br>' + json2html(json[key], indent + "&nbsp;&nbsp;&nbsp;&nbsp;", key);
        } else if ((typeof json[key] === 'string') || (typeof json[key] === 'number') || (typeof json[key] === 'boolean') || (typeof json[key] === null)) {
           outstr += indent + key + ' : ' + getItem(json[key], key); //parentkey);
        } else {
          console.log("unexpected type in json2html (2): " + parentkey + " : "+  json[key] + " : "+ (typeof json[key]));
        }
      }
    }

    return outstr;
}
//*****************************************************************************
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
    gauge.animationSpeed = 255; // set animation speed (32 is default value)

    return gauge;
}

//*****************************************************************************
function createFuel(pCanvas, pText, pFG, tanksize) {
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
    gauge.maxValue = tanksize; // set max gauge value
    // gauge.setTextField(pText, pTextPrecision);
    gauge.animationSpeed = 32; // set animation speed (32 is default value)

    var w = gauge.canvas.width / 2;
    var r = gauge.radius * 0.7 ;
    var h = (gauge.canvas.height * gauge.paddingTop + gauge.availableHeight) - ((gauge.radius + gauge.lineWidth / 2) * gauge.extraPadding);

    pFG[0].width = gauge.canvas.width;
    pFG[0].height = gauge.canvas.height;
    var ctx = pFG[0].getContext('2d');
    // var ctx = gauge.canvas.getContext('2d');

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
//*****************************************************************************
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
//*****************************************************************************
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
//*****************************************************************************
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

        if (myGenerator["write_access"] == true) {
            if (myGenerator['ExerciseControls'] == true) {

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

               if (myGenerator['WriteQuietMode'] == true) {
                 //Create and append select list
                 outstr += '&nbsp;&nbsp;<select id="quietmode">';
                 outstr += '<option value="On" ' + (myGenerator['QuietMode'] == "On"  ? ' selected="selected" ' : '') + '>Quiet Mode On </option>';
                 outstr += '<option value="Off"' + (myGenerator['QuietMode'] == "Off" ? ' selected="selected" ' : '') + '>Quiet Mode Off</option>';
                 outstr += '</select>';
               }

               outstr += '<br><br>'
               outstr += '&nbsp;&nbsp;<button id="setexercisebutton" onClick="saveMaintenance();">Set Exercise Time</button>';
            }

            outstr += '<br><br>Generator Time:<br><br>';
            outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetTimeClick();">Set Generator Time</button>';

            if (myGenerator['RemoteCommands'] == true) {
               outstr += '<br><br>Remote Commands:<br><br>';
               outstr += '&nbsp;&nbsp;&nbsp;&nbsp;<button class="tripleButtonLeft" id="remotestop" onClick="SetClick(\'stop\');">Stop Generator</button>';
               outstr += '<button class="tripleButtonCenter" id="remotestart" onClick="SetClick(\'start\');">Start Generator</button>';
               if (myGenerator['RemoteTransfer'] == true) {
                 outstr += '<button class="tripleButtonRight"  id="remotetransfer" onClick="SetClick(\'starttransfer\');">Start Generator and Transfer</button>';
               }

            }

            if (myGenerator['ResetAlarms'] == true || myGenerator['AckAlarms'] == true){
               outstr += '<br><br>Alarm Condition:<br><br>';
               if (myGenerator['ResetAlarms'] == true) {
                  outstr += '&nbsp;&nbsp;<button id="resetalarm" onClick="SetClick(\'resetalarm\');">Reset Alarm</button><br>';
               }
               if (myGenerator['AckAlarms'] == true) {
                  outstr += '&nbsp;&nbsp;<button id="ackalarm" onClick="SetClick(\'ackalarm\');">Acknowledge Alarm</button><br>';
               }
            }

            if (myGenerator['RemoteButtons'] == true) {
               outstr += '<br>Switch Position:<br><br>';
               outstr += '&nbsp;&nbsp;&nbsp;&nbsp;<button class="tripleButtonLeft" id="switchoff" onClick="SetClick(\'off\');">Off</button>';
               outstr += '<button class="tripleButtonCenter" id="switchauto" onClick="SetClick(\'auto\');">Auto</button>';
               outstr += '<button class="tripleButtonRight"  id="switchmanual" onClick="SetClick(\'manual\');">Manual</button><br>';
            }

            if (myGenerator['PowerGraph'] == true) {
               outstr += '<br>Reset:<br><br>';
               outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetPowerLogReset();">Reset Power Log & Fuel Estimate</button>';
            }

        }

            $("#mydisplay").html(outstr);

        if (myGenerator["write_access"] == true) {

            setExerciseSelection();

            $("#days").val(myGenerator['ExerciseDay']);
            $("#hours").val(myGenerator['ExerciseHour']);
            $("#minutes").val(myGenerator['ExerciseMinute']);

            setStartStopButtonsState();

            myGenerator["OldExerciseParameters"] = [myGenerator['ExerciseDay'], myGenerator['ExerciseHour'], myGenerator['ExerciseMinute'], myGenerator['QuietMode'], myGenerator['ExerciseFrequency'], myGenerator['EnhancedExerciseEnabled']];
        }

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
function SetClick(cmd){
    var msg = "";

    switch (cmd) {
       case "stop":
          msg = 'Stop generator?<br><span class="confirmSmall">Note: If the generator is powering a load the transfer switch will be deactivated and there will be a cool down period of a few minutes.</span>';
          break;
       case "start":
          msg = 'Start generator?<br><span class="confirmSmall">Generator will start, warm up and run idle (without activating the transfer switch).</span>';
          break;
       case "starttransfer":
          msg = 'Start generator and activate transfer switch?<br><span class="confirmSmall">Generator will start, warm up, then activate the transfer switch.</span>';
          break;
       case "off":
          msg = 'Turn off the Generator?<br><span class="confirmSmall">Generator will NOT start automatically in case of a power outage.</span>';
          break;
       case "auto":
          msg = 'Set generator to Auto?<br><span class="confirmSmall">Generator will automatically start and transfer in case of a power outage.</span>';
          break;
       case "manual":
          msg = 'Set generator to Manual?<br><span class="confirmSmall">Generator will start, warm up and run idle (without activating the transfer switch).</span>';
          break;
       case "resetalarm":
          msg = 'Reset generator alarm?<br><span class="confirmSmall">Are you sure you want to reset the alarm condition on your generator?</span>';
          break;
       case "ackalarm":
          msg = 'Acknowledge generator alarm?<br><span class="confirmSmall">Are you sure you want to acknowledge the alarm condition on your generator?</span>';
          break;
    }

    vex.dialog.confirm({
        unsafeMessage: msg,
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                SetRemoteCommand(cmd)
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
// called when reset Power Log / Fuel Estimate clicked
//*****************************************************************************
function SetPowerLogReset(){

    vex.dialog.confirm({
        unsafeMessage: 'Reset Power Log & Reset Full Estimate?<br><span class="confirmSmall">Note: This will delete the contents of the power log. This needs to be used when your tank is filled to make sure that the fuel estimate is reset.</span>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                // set exercise time
                var url = baseurl.concat("power_log_clear");
                $.getJSON(  url,
                   {power_log_clear: " "},
                   function(result){});
             }
        }
    });
}


//*****************************************************************************
// Display the Maintenance Tab
//*****************************************************************************
function DisplayMaintenanceUpdate(){

    if (myGenerator["write_access"] == true) {
        /*
        // This code has been removed as it update the UI incorrectly
        $("#Exercise_Time").html(myGenerator['ExerciseFrequency'] + ' ' +
                                 myGenerator['ExerciseDay'] + ' ' + myGenerator['ExerciseHour'] + ':' + myGenerator['ExerciseMinute'] +
                                 ' Quiet Mode ' + myGenerator['QuietMode']);
        */
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

        setStartStopButtonsState();

        myGenerator["OldExerciseParameters"] = [myGenerator['ExerciseDay'], myGenerator['ExerciseHour'], myGenerator['ExerciseMinute'], myGenerator['QuietMode'], myGenerator['ExerciseFrequency'], myGenerator['EnhancedExerciseEnabled']];
    }

    var url = baseurl.concat("maint_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        $("#maintText").html(json2html(result, "", "root"));
        // $("#Next_Service_Scheduled").html(result["Maintenance"]["Service"]["Next Service Scheduled"]);
        // $("#Total_Run_Hours").html(result["Maintenance"]["Service"]["Total Run Hours"]);
    }});

}

//*****************************************************************************
function setStartStopButtonsState(){
   $("#remotestop").css("background", "#bbbbbb");
   $("#remotestart").css("background", "#bbbbbb");
   $("#remotetransfer").css("background", "#bbbbbb");
   switch (baseState) {
     case "EXERCISING" :
        $("#remotestop").prop("disabled",false);
        $("#remotestart").prop("disabled",true);
        $("#remotetransfer").prop("disabled",true);
        $("#remotestart").css("background", "#4CAF50");
        break;
     case "RUNNING":
        $("#remotestop").prop("disabled",false);
        $("#remotestart").prop("disabled",true);
        $("#remotetransfer").prop("disabled",true);
        $("#remotestart").css("background", "#4CAF50");
        $("#remotetransfer").css("background", "#4CAF50");
        break;
    case "ALARM":
        $("#remotestop").prop("disabled",false);
        $("#remotestart").prop("disabled",false);
        $("#remotetransfer").prop("disabled",false);
        break;
    case "SERVICEDUE":
        $("#remotestop").prop("disabled",false);
        $("#remotestart").prop("disabled",false);
        $("#remotetransfer").prop("disabled",false);
        break;
     default:
        $("#remotestop").prop("disabled",true);
        $("#remotestart").prop("disabled",false);
        $("#remotetransfer").prop("disabled",false);
        $("#remotestop").css("background", "#4CAF50");
        break;
   }

   $("#switchoff").css("background", "#bbbbbb");
   $("#switchauto").css("background", "#bbbbbb");
   $("#switchmanual").css("background", "#bbbbbb");
   switch (switchState) {
     case "Auto" :
        $("#switchoff").prop("disabled",false);
        $("#switchauto").prop("disabled",true);
        $("#switchmanual").prop("disabled",false);
        $("#switchauto").css("background", "#4CAF50");
        break;
     case "Off" :
        $("#switchoff").prop("disabled",true);
        $("#switchauto").prop("disabled",false);
        $("#switchmanual").prop("disabled",false);
        $("#switchoff").css("background", "#4CAF50");
        break;
     case "Manual" :
        $("#switchoff").prop("disabled",false);
        $("#switchauto").prop("disabled",false);
        $("#switchmanual").prop("disabled",true);
        $("#switchmanual").css("background", "#4CAF50");
        break;
     default:
        $("#switchoff").prop("disabled",false);
        $("#switchauto").prop("disabled",false);
        $("#switchmanual").prop("disabled",false);
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
                    if (myGenerator['WriteQuietMode'] == true) {
                      var url = baseurl.concat("setquiet");
                      $.getJSON(  url,
                                  {setquiet: strQuiet},
                                  function(result){});
                    }

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

        if (lowbandwidth == false) {
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
            } else if (loglines[i].indexOf("Run Log :") >= 0) {
               severity = 1;
            } else {
               var matches = loglines[i].match(/^\s*(\d+)\/(\d+)\/(\d+) (\d+:\d+:\d+) (.*)$/i)
               if ((matches != undefined) && (matches.length == 6)) {
                  if ((12*matches[3]+1*matches[1]+12) <= (12*(date.getYear()-100) + date.getMonth() + 1)) {
                  } else if (data_helper[matches.slice(1,3).join("/")] == undefined) {
                      data_helper[matches.slice(1,3).join("/")] = {count: severity, date: '20'+matches[3]+'-'+matches[1]+'-'+matches[2], dateFormatted: matches[2]+' '+MonthsOfYearArray[(matches[1] -1)]+' 20'+matches[3], title: matches[5].trim()};
                      if (((12*(date.getYear()-100) + date.getMonth() + 1)-(12*matches[3]+1*matches[1])+1) > months) {
                          months = (12*(date.getYear()-100) + date.getMonth() + 1)-(12*matches[3]+1*matches[1])+1
                      }
                  } else {
                      data_helper[matches.slice(1,3).join("/")]["title"] = data_helper[matches.slice(1,3).join("/")]["title"] + "<br>" + matches[5].trim();
                      if (data_helper[matches.slice(1,3).join("/")]["count"] < severity)
                         data_helper[matches.slice(1,3).join("/")]["count"] = severity;
                  }
               }
            }

          }
          var data = Object.keys(data_helper).sort().map(function(itm) { return data_helper[itm]; });
          // var data = Object.keys(data_helper).map(itm => data_helper[itm]);
          // var data = Object.values(data_helper);
          // console.log(data);
          var options = {coloring: 'genmon', start: new Date((date.getMonth()-12 < 0) ? date.getYear() - 1 + 1900 : date.getYear() + 1900, (date.getMonth()-12 < 0) ? date.getMonth()+1 : date.getMonth()-12, 1), end: new Date(date.getYear() + 1900, date.getMonth(), date.getDate()), months: months, labels: { days: true, months: true, custom: {monthLabels: "MMM 'YY"}}, tooltips: { show: true, options: {}}, legend: { show: false}};
          $("#annualCalendar").CalendarHeatmap(data, options);
        }
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

        $("#mydisplay").html(outstr);

        if ($("#CPU_Temperature").length > 0) {
           temp_img = "temp1";
           cpu_temp = $("#CPU_Temperature").text();
           cpu_temp_num = parseInt(cpu_temp.replace(/C/g, '').trim());
           if (cpu_temp.indexOf("F") > 0 ) {
              cpu_temp_num = Math.round((parseInt(cpu_temp.replace(/F/g, '').trim()) - 32) * 5 / 9);
           }
           switch (true) {
              case (cpu_temp_num > 85):
                  temp_img = "temp4";
                  break;
              case (cpu_temp_num > 75):
                  temp_img = "temp3";
                  break;
              case (cpu_temp_num > 50):
                  temp_img = "temp2";
                  break;
           }
           $("#CPU_Temperature").html('<div style="display: inline-block; position: relative;">' + cpu_temp + '<img style="position: absolute;top:-10px;left:75px" class="'+ temp_img +'" src="images/transparent.png"></div>');
        }

        if ($("#WLAN_Signal_Level").length > 0) {
           wifi_img = "wifi1";
           wifi_level = $("#WLAN_Signal_Level").text();
           switch (true) {
              case (parseInt(wifi_level.replace(/dBm/g, '').trim()) > -67):
                  wifi_img = "wifi4";
                  break;
              case (parseInt(wifi_level.replace(/dBm/g, '').trim()) > -70):
                  wifi_img = "wifi3";
                  break;
              case (parseInt(wifi_level.replace(/dBm/g, '').trim()) > -80):
                  wifi_img = "wifi2";
                  break;
           }
           $("#WLAN_Signal_Level").html('<div style="display: inline-block; position: relative;">' + wifi_level + '<img style="position: absolute;top:-10px;left:110px" class="'+ wifi_img +'" src="images/transparent.png"></div>');
        }
        if ($("#Conditions").length > 0) {
           weatherCondition = $("#Conditions").text()
           weatherIcon = "unknown.png"
           jQuery.each(prevStatusValues["Weather"], function( i, val ) {
             if (Object.keys(val)[0] == "icon") {
               weatherIcon = val["icon"];
             }
           });
           $("#Conditions").html('<div style="display: inline-block; position: relative;">' + weatherCondition + '<img class="greyscale" style="position: absolute;top:-30px;left:160px" src="https://openweathermap.org/img/w/' + weatherIcon + '.png"></div>');
        }

   }});
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
//*****************************************************************************
function renderNotificationLine(rowcount, line_type, line_text, line_perms) {

   var outstr = '<tr id="row_' + rowcount + '"><td nowrap><div rowcount="' + rowcount + '" class="removeRow"><img class="remove_bin" src="images/transparent.png" height="24px" width="24px"></div></td>';
   outstr += '<td nowrap><input type="hidden" name="type_' + rowcount + '" value="s01_email">';
   outstr += '<td nowrap><input id="email_' + rowcount + '" class="notificationEmail" name="email_' + rowcount + '" type="text" value="'+line_text+'" '+ ((line_type != "s01_email") ? 'class="dataMask"' : '') +' ></td>';

   outstr += '<td width="300px" nowrap><select multiple style="width:290px" class="notificationTypes" name="notif_' + rowcount + '" id="notif_' + rowcount + '" oldValue="'+line_perms+'" placeholder="Select types of notifications...">';
   outstr += ["outage", "error", "warn", "info"].map(function(key) { return '<option value="'+key+'" '+(((line_perms == undefined) || (line_perms.indexOf(key) != -1) || (line_perms == "")) ? ' selected ' : '')+'>'+key+'</option>'; }).join();
   outstr += '</select></td>';

   return outstr;
}

//*****************************************************************************
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
             setTimeout(function(){ vex.closeAll();gotoLogin();}, 10000);
           }
        }
    })
}

//*****************************************************************************
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
// Display the Journal Tab
//*****************************************************************************

function DisplayJournal(){
    var url = baseurl.concat("get_maint_log_json");
    var allJournalEntries
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();
        allJournalEntries = result

        var  outstr = 'Journal Entries:<br><br>';
        outstr += '<table id="alljournal" border="0" style="border-collapse: separate; border-spacing: 10px;" width="100%"><tbody>';

        $.each(Object.keys(result), function(i, key) {
            outstr += renderJournalLine(i, result[i]["date"], result[i]["type"], result[i]["hours"], result[i]["comment"]);
        });
        outstr += '</tbody></table><br>';
        outstr += '<button value="+Add" id="addJournalRow">+Add</button>';
        outstr += '<br><br><button value="Clear" id="clearJournal">Clear Journal</button>';

        $("#mydisplay").html(outstr);

        $(".edit#editJournalRow").on('click', function() {
           id = $(this).attr("row");
           var outstr = emptyJournalLine("amend", id, allJournalEntries[id]["date"], allJournalEntries[id]["type"], allJournalEntries[id]["hours"], allJournalEntries[id]["comment"])
           $("#row_"+id).replaceWith(outstr);
           $("input[name^='time_"+id+"']").timepicker({ 'timeFormat': 'H:i' });
           $("input[name^='date_"+id+"']").datepicker({ dateFormat: 'mm/dd/yy' })
        });

        $(".remove_bin#deleteJournalRow").on('click', function() {
           id = $(this).attr("row");
           DeleteJournalRow(id);
        });

        $(document).ready(function() {
           $("#addJournalRow").click(function () {
                  id = $("#alljournal").length
                  var outstr = emptyJournalLine("add", id, myGenerator['MonitorTime'], "", isNaN(parseFloat(myGenerator['RunHours'])) ? "" : parseFloat(myGenerator['RunHours']), "")
                  if ($("#alljournal").length > 0) {
                      $("#alljournal").append(outstr);
                  } else {
                      $("#alljournal").append(outstr);
                  }
                  $("input[name^='time_"+id+"']").timepicker({ 'timeFormat': 'H:i' });
                  $("input[name^='date_"+id+"']").datepicker({ dateFormat: 'mm/dd/yy' })
           });

           $("#clearJournal").click(function () {
              ClearJournal();
           });

        });
   }});
}
//*****************************************************************************
function renderJournalLine(rowcount, date, type, hours, comment) {

   var outstr = '<tr id="row_' + rowcount + '"><td align="center">';
   outstr += '  <div class="card" style="width:80%;align:center;" name="journal_' + rowcount + '">';
   outstr += '     <div style="width:100%; background-color:#e1e1e1; border-radius: 6px 6px 0px 0px; float:left; padding-top:10px; padding-bottom:10px;">';
   outstr += '         <table width="90%"><tr><td width="30%">Date: '+date+'</td><td width="30%">Type: '+type+'</td><td width="30%">Service Hours: '+hours+'</td><td width="10%" align="right"><img id="editJournalRow" row="'+ rowcount +'" class="edit" src="images/transparent.png" width="24px" height="24px">&nbsp<img id="deleteJournalRow" row="'+ rowcount +'" class="remove_bin" src="images/transparent.png" width="24px" height="24px"></td></table>';
   outstr += '     </div>';
   outstr += '     <div style="clear: both;"></div>';
   outstr += '     <div style="margin:10px;font-size: 15px;">'+comment+'</center></div>';
   outstr += '     <div style="clear: both;"></div><br>';
   outstr += '  </div>';
   outstr += '</td>';

   return outstr;
}

function emptyJournalLine(rowtype, rowcount, date, type, hours, comment) {
   if (comment == undefined) {
     comment = ""
   }
   var outstr = '<tr id="row_' + rowcount + '"><td align="center">';
   outstr += '<form id="formNotifications">';
   outstr += '  <div class="card" style="width:80%;align:center;" name="journal_' + rowcount + '">';
   outstr += '     <div style="width:100%; background-color:#e1e1e1; border-radius: 6px 6px 0px 0px; float:left; padding-top:10px; padding-bottom:10px;">';
   outstr += '         <center><table width="80%">';
   outstr += '           <tr><td align="right" style="padding:3px">Date: &nbsp;&nbsp;&nbsp;</td><td style="padding:3px"><input id="date_' + rowcount + '" name="date_' + rowcount + '" type="text" value="'+date.split(" ")[0]+'">&nbsp;<input id="time_' + rowcount + '" name="time_' + rowcount + '" type="text" value="'+date.split(" ")[1]+'"></td></tr>';
   outstr += '           <tr><td align="right" style="padding:3px">Type: &nbsp;&nbsp;&nbsp;</td><td style="padding:3px"><select id="type_' + rowcount + '" name="type_' + rowcount + '" ><option value="Repair">Repair</option><option value="Check">Check</option><option value="Observation">Observation</option><option value="Maintenance">Maintenance</option></select></td></tr>';
   outstr += '           <tr><td align="right" style="padding:3px">Service Hours: &nbsp;&nbsp;&nbsp;</td><td style="padding:3px"><input id="hours_' + rowcount + '" name="hours_' + rowcount + '" type="text" value="'+hours+'"></td></tr>';
   outstr += '         </table></center>';
   outstr += '     </div>';
   outstr += '     <div style="clear: both;"></div>';
   outstr += '     <div style="margin:15px;font-size: 15px;"><textarea id="comment_' + rowcount + '" name="comment_' + rowcount + '" rows="4" style="width:100%;">'+comment+'</textarea></center></div>';
   outstr += '     <div style="clear: both;"></div>';
   outstr += '     <button id="setjournalbutton" onClick="saveJournals(\'' + rowtype + '\', ' + rowcount + '); return false;">Save</button>';
   outstr += '     <div style="clear: both;"></div><br>';
   outstr += '  </div>';
   outstr += '</form>';
   outstr += '</td>';

   return outstr;

}


//*****************************************************************************
// called when Save Journals is clicked
//*****************************************************************************
function saveJournals(rowtype, rowcount){

    var DisplayStr = "Save journal? Are you sure?";
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

    validationResult = ValidateJournalEntry($("input[name^='date_"+rowcount+"']").val(), $("input[name^='time_"+rowcount+"']").val(), $("select[name^='type_"+rowcount+"']").val(), $("input[name^='hours_"+rowcount+"']").val(), $("textarea[name^='comment_"+rowcount+"']").val());
    if (validationResult != "OK") {
       GenmonAlert("Data value not correct.<br>"+validationResult);
       return false;
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
             var DisplayStr1 = "Saving Journal..."
             DisplayStrAnswer = false; // Prevent recursive calls.
             e.preventDefault();
             saveJournalsJSON(rowtype, rowcount);
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){ vex.closeAll();}, 2000);
           }
        }
    })
}

//*****************************************************************************
function saveJournalsJSON(rowtype, rowcount){
    try {
        var fields = {};

        var entry = {
            date: $("input[name^='date_"+rowcount+"']").val()+" "+$("input[name^='time_"+rowcount+"']").val(),   // Format is text string:  MM/DD/YYYY
            type: $("select[name^='type_"+rowcount+"']").val(),                                                  // Values are string: "Repair", "Maintenance", "Check" or "Observation"
            hours: parseFloat($("input[name^='hours_"+rowcount+"']").val()),                                       // Must be a number (integer or floating point)
            comment: $("textarea[name^='comment_"+rowcount+"']").val()                                           // Text string
            };

        // send command
        if (rowtype == "add") {
           var url = baseurl.concat("add_maint_log");
           var input =  JSON.stringify(entry)
           $.getJSON(  url,
                 {add_maint_log: input},
                 function(result){
                    outstr = renderJournalLine(rowcount, entry["date"], entry["type"], entry["hours"], entry["comment"]);
                    $("#row_"+rowcount).replaceWith(outstr);
           });
        } else if (rowtype == "amend") {
           var url = baseurl.concat("edit_row_maint_log");
           var input =  JSON.stringify(entry)
           $.getJSON(  url,
                 {edit_row_maint_log: "{\""+rowcount+"\": "+input+"}"},
                 function(result){
                    // The following 2 lines don't update the ".on('click'"... Probably a jquery issue.
                    // outstr = renderJournalLine(rowcount, entry["date"], entry["type"], entry["hours"], entry["comment"]);
                    // $("#row_"+rowcount).replaceWith(outstr);
                    DisplayJournal();
           });
        }

    } catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}

//*****************************************************************************
// called when adding an  entry to the maint log
//*****************************************************************************
function ValidateJournalEntry(date, time, type, hours, comment){

  if ((typeof date != 'string') || (typeof time != 'string') || (typeof type != 'string') || (typeof hours != 'string') || (typeof comment != "string")){
    return "Invalid type for Maint Log Entry "
  }

  hoursFloat = parseFloat(hours)
  if ((typeof hoursFloat != "number") || isNaN(hoursFloat) || (hoursFloat == 0)){
    return "Service Hours is not a number or 0"
  }

  // check type
  if ((type.toLowerCase() !== 'repair') &&
      (type.toLowerCase() !== 'check') &&
      (type.toLowerCase() !== 'observation') &&
      (type.toLowerCase() !== 'maintenance')) {
          return "Invalid value for Type"
  }

  if (comment.trim() == "") {
     return "Comment field must not be blank";
  }

  // check date
  var date_regex = /^(0[1-9]|1[0-2])\/(0[1-9]|1\d|2\d|3[01])\/(19|20)\d{2}$/ ;
  if(!(date_regex.test(date)))
  {
      return "Invalid date format, expecting MM/DD/YYYY: " + date;
  }

  var time_regex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/ ;
  if(!(time_regex.test(time)))
  {
      return "Invalid time format, expecting HH:MM " + time;
  }

  return "OK"
}

//*****************************************************************************
// called when adding an  entry to the maint log
//*****************************************************************************
function ClearJournal(){

    vex.dialog.confirm({
        unsafeMessage: 'Clear the Service Journal? This action cannot be undone.<br>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                var url = baseurl.concat("clear_maint_log");
                $.getJSON(  url,
                   {},
                   function(result){
                     $("#alljournal").empty();
                   });
             }
        }
    });
}

function DeleteJournalRow(id){

    vex.dialog.confirm({
        unsafeMessage: 'Delete the Journal Entry '+id+'? This action cannot be undone.<br>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                var url = baseurl.concat("delete_row_maint_log");
                // var input =  JSON.stringify({id: id})
                $.getJSON(  url,
                   {delete_row_maint_log: id},
                   function(result){
                     // $("#row_"+id).empty();
                     DisplayJournal();
                   });
             }
        }
    });
}


//*****************************************************************************
// test email
//*****************************************************************************
function TestEmailSettingsWrapper(){
    GenmonPrompt("Sending Test Email", "recepient:", $("#email_account").val());
}

function TestEmailSettingsWrapperSubmit(email){
    $('.vex-dialog-message').html("<h4>Sending...</h4>");
    $('.vex-dialog-buttons').hide();
    TestEmailSettings($("#smtp_server").val(), $("#smtp_port").val(), $("#email_account").val(),
      $("#sender_account").val(),$("#sender_name").val(), email, $("#email_pw").val(),
      ($("#ssl_enabled").prop('checked')  === true ? "true" : "false"),
      ($("#tls_disable").prop('checked') === true ? "true" : "false"),
       ($("#smtpauth_disable").prop('checked') === true ? "true" : "false"));
}

function TestEmailSettings(smtp_server, smtp_port,email_account,sender_account,sender_name,recipient, password, use_ssl, tls_disable, smtpauth_disable){

    var parameters = {};
    parameters['smtp_server'] = smtp_server;
    parameters['smtp_port'] = smtp_port;
    parameters['email_account'] = email_account;
    parameters['sender_account'] = sender_account;
    parameters['sender_name'] = sender_name;
    parameters['recipient'] = recipient;
    parameters['password'] = password;
    parameters['use_ssl'] = use_ssl;
    parameters['tls_disable'] = tls_disable;
    parameters['smtpauth_disable'] = smtpauth_disable;

      // test email settings
      var url = baseurl.concat("test_email");
      $.get(  url,
                  {test_email: JSON.stringify(parameters)},
                  function (result, status) {
                    if ((status == "success") && (result == "Success")) {
                       vex.dialog.buttons.YES.text = 'OK';
                       $('.vex-dialog-message').html("Test email sent successfully. Please verify that you received the email.");
                       $('.vex-dialog-button-primary').text("OK");
                       $('.vex-dialog-button-secondary').hide();
                       $('.vex-dialog-buttons').show();
                    } else {
                       vex.dialog.buttons.YES.text = 'Close';
                       GenmonAlert("An error occurred: <br>"+result+"<br><br>Please try again.");
                       $('.vex-dialog-button-primary').text("Close");
                    }
      });
}
//*****************************************************************************
// Display the Settings Tab
//*****************************************************************************
function DisplaySettings(){

    var url = baseurl.concat("settings");
    $.ajax({dataType: "json", url: url, timeout: 12000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        var outstr = '<form class="idealforms" novalidate  id="formSettings">';
        var settings =  getSortedKeys(result, 2);
        var usehttps = false;
        for (var index = 0; index < settings.length; ++index) {
            var key = settings[index];
            if (key == "sitename") {
              outstr += '<br>General Settings:<fieldset id="generalSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "nominalfrequency") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap>Generator Model Specific Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="modelSettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "usehttps") {
              usehttps = result[key][3];
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, result[key][3], "", "", "usehttpsChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Webserver Security Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr><tr><td colspan="3"><div id="newURLnotify"><font color="red">NOTE: After saving, your new URL will be: <div style="display: inline-block;" id="newURL"></div></font></div></td></tr></table>';
              outstr += '<fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "use_serial_tcp") {
              outstr += '</table></fieldset><table width="100%" border="0"><tr><td width="25px">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</td><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, result[key][3], "", "", "useSerialTCPChange(true);");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Enable Serial over TCP/IP&nbsp;&nbsp;</td><td width="80%">&nbsp;</td></tr></table>';
              outstr += '<fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "disablesmtp") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, !result[key][3], "", "", "toggleSectionInverse(true, '"+key+"');");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Outbound Email Settings&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "disableimap") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px" colspan="2"><button type="button" style="margin-left: 0px; background: #bbbbbb; cursor:pointer; padding: .5em .5em; border: 0; border-radius: 3.01px; font-family: inherit;" '+
                        ' id="testsettingsbutton" onClick="TestEmailSettingsWrapper();return false;">Test Email Settings</button></td></tr>';
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, !result[key][3], "", "", "toggleSectionInverse(true, '"+key+"');");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Inbound Email Commands Processing&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "disableweather") {
              outstr += '</table></fieldset><br><br><table width="100%" border="0"><tr><td nowrap width="90px">';
              outstr += printSettingsField(result[key][0], key, !result[key][3], "", "", "toggleSectionInverse(true, '"+key+"');");
              outstr += '</td><td nowrap>&nbsp;&nbsp;Optional - Display Current Weather&nbsp;&nbsp;</td><td width="80%"><hr></td></tr></table>';
              outstr += '<fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "fueltype") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5],  "useFullTank(true)") + '</td></tr>';
            } else if (key == "tanksize") {
              outstr += '</table></fieldset><fieldset id="'+key+'Section"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
              outstr += '</table></fieldset><fieldset><table id="allsettings" border="0">';
            } else if (key == "useselfsignedcert") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
              outstr += '</table><fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "http_user") {
              outstr += '</table></fieldset><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
            } else if (key == "http_port") {
              outstr += '</table></fieldset><fieldset id="noneSecuritySettings"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert'); usehttpsChange(true);") + '</td></tr>';
            } else if (key == "port") {
              outstr += '</table></fieldset><fieldset id="serialDirect"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
            } else if (key == "serial_tcp_address") {
              outstr += '</table></fieldset><fieldset id="serialTCP"><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
            } else if (key == "serial_tcp_port") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
              outstr += '</table></fieldset><table id="allsettings" border="0">';
            } else if (key == "favicon") {
              outstr += '</table></fieldset><table id="allsettings" border="0">';
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSection(true, 'useselfsignedcert');") + '</td></tr>';
            } else if ((key == "autofeedback") && (myGenerator['UnsentFeedback'] == true)) {
              outstr += '<tr><td width="25px">&nbsp;</td><td bgcolor="#ffcccc" width="300px">' + result[key][1] + '</td><td bgcolor="#ffcccc">' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            } else if (key == "weatherlocation") {
              outstr += '<tr><td width="25px">&nbsp;</td><td valign="top" width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]);
              if (httpsUsed() == true) {
                outstr += '<br><button type="button" id="weathercityname" onclick="lookupLocation()">Look Up</button>';
              }
              outstr += '</td></tr>';
            } else if (key == "usemfa") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5], "toggleSectionInverse(true, 'usemfa');") + '</td></tr>';
              outstr += '</table></fieldset><fieldset id="'+key+'Section"><table id="allsettings" border="0">';
            } else if (key == "mfa_url") {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td><div id="qrcode"></div></td></tr>'
              QR_Code_URL = result[key][3];
            } else {
              outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
            }
        }
        outstr += '</table></fieldset></form><br>';
        outstr += '<button id="setsettingsbutton" onClick="saveSettings()">Save</button>';

        $("#mydisplay").html(outstr);
        $('input').lc_switch();
        if (QR_Code_URL != "") {
          $("#qrcode").qrcode({width: 164,height: 164,text: QR_Code_URL});
        }
        $.extend($.idealforms.rules, {
           // The rule is added as "ruleFunction:arg1:arg2"
           HTTPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^((([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))|((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^(\\+(\\d{1,3}))?((\\(\\d{1,4}\\))|(\\d{1,3}))?(\\s|\-)?(\\d+(\\s?|\-?))+$', 'g');
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
            HTTPAddress: 'Must be a valid address from an internet server, eg. http://mail.google.com',
            InternetAddress: 'Must be a valid address from an internet server, eg. mail.google.com',
            IPAddress: 'Must be a valid IP address, eg. 192.168.1.100',
            InternationalPhone: 'Must be a valid Phone Number, eg. +1 123 456 7890',
            UnixFile: 'Must be a valid UNIX file',
            UnixDir: 'Must be a valid UNIX path',
            UnixDevice: 'Must be a valid UNIX file path starting with /dev/'
        });
        $('form.idealforms').idealforms({
           tooltip: '.tooltip',
           silentLoad: true,
        });

        usehttpsChange(false);
        useSerialTCPChange(false);
        useFullTank(false);
        toggleSection(false, "useselfsignedcert");
        toggleSectionInverse(false, "usemfa");
        toggleSectionInverse(false, "disablesmtp");
        toggleSectionInverse(false, "disableimap");
        toggleSectionInverse(false, "disableweather");
   }});

}

//*****************************************************************************
function useFullTank(animation) {
   if ($("#fueltype").val() == "Natural Gas") {
      $("#tanksizeSection").hide((animation ? 300 : 0));
   } else {
      $("#tanksizeSection").show((animation ? 300 : 0));
   }
}
//*****************************************************************************
function usehttpsChange(animation) {
   if ($("#usehttps").is(":checked")) {
      $("#noneSecuritySettings").hide((animation ? 300 : 0));
      $("#usehttpsSection").show((animation ? 300 : 0));
      if ($("#usemfa").is(":checked")) {
        $("#usemfaSection").show((animation ? 300 : 0));
      }

      if (!$("#useselfsignedcert").is(":checked")) {
         $("#useselfsignedcertSettings").show((animation ? 300 : 0));
      }
   } else {
      $("#usehttpsSection").hide((animation ? 300 : 0));
      $("#noneSecuritySettings").show((animation ? 300 : 0));
      $("#usemfaSection").hide((animation ? 300 : 0));
   }
   if (($('#http_port').val() == $('#http_port').attr('oldValue')) && ($("#usehttps").attr('oldValue') == ($("#usehttps").prop('checked') === true ? "true" : "false"))){
      $("#newURLnotify").hide((animation ? 300 : 0));
   } else {
      $("#newURL").html((($("#usehttps").is(":checked"))?"https":"http")+"://"+$(location).attr('hostname')+(((!$("#usehttps").is(":checked")) && ($('#http_port').val() != "80"))?":"+$('#http_port').val():"")+$(location).attr('pathname'));
      $("#newURLnotify").show((animation ? 300 : 0));
   }

}
//*****************************************************************************
function useSerialTCPChange(animation) {
   if ($("#use_serial_tcp").is(":checked")) {
      $("#serialDirect").hide((animation ? 300 : 0));
      $("#serialTCP").show((animation ? 300 : 0));
   } else {
      $("#serialTCP").hide((animation ? 300 : 0));
      $("#serialDirect").show((animation ? 300 : 0));
   }
}
//*****************************************************************************
function toggleSection(animation, section) {
   if ($("#"+section).is(":checked")) {
      $("#"+section+"Section").hide((animation ? 300 : 0));
   } else {
      $("#"+section+"Section").show((animation ? 300 : 0));
   };
}
//*****************************************************************************
function toggleSectionInverse(animation, section) {
   if ($("#"+section).is(":checked")) {
      $("#"+section+"Section").show((animation ? 300 : 0));
   } else {
      $("#"+section+"Section").hide((animation ? 300 : 0));
   };
}
//*****************************************************************************
function lookupLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(locationSuccess, locationError, {timeout:10000});
    } else {
        GenmonAlert("Your browser does not support Geolocation!");
    }
}
//*****************************************************************************
function locationError(error) {
    switch (error.code) {
    case error.TIMEOUT:
        GenmonAlert("A timeout occured! Please try again!");
        break;
    case error.POSITION_UNAVAILABLE:
        GenmonAlert('We can\'t detect your location. Sorry!');
        break;
    case error.PERMISSION_DENIED:
        GenmonAlert('Please allow geolocation access for this to work.');
        break;
    case error.UNKNOWN_ERROR:
        GenmonAlert('An unknown error occured!');
        break;
    }
}

//*****************************************************************************
function locationSuccess(position) {
    try {
            if ($('#weatherkey').val().length < 1 ) {
              GenmonAlert("API key is required for city lookup.");
              return;
            }

            var weatherAPI = '//api.openweathermap.org/data/2.5/forecast?lat=' + position.coords.latitude + '&lon=' + position.coords.longitude + '&lang=en&APPID='+$('#weatherkey').val();
            $.getJSON(weatherAPI, function (response) {
                $('#weatherlocation').val(response.city.id);
                // $('form.idealforms').idealforms('is:valid', "weatherlocation");
                $('#weathercityname').replaceWith("  ("+response.city.name+")");
            });
    } catch (e) {
        GenmonAlert("We can't find information about your city!");
        window.console && console.error(e);
    }
}

//*****************************************************************************
function printSettingsField(type, key, value, tooltip, validation, callback) {
   var outstr = "";
   switch (type) {
     case "string":
     case "password":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + '" style="width: 300px;" name="' + key + '" type="' + ((type == "password") ? "password" : "text") + '" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' onChange="' + callback + ';" ' : "") +
                  (typeof value === 'undefined' ? '' : 'value="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (((typeof validation === 'undefined') || (validation==0)) ? 'onFocus="$(\'#'+key+'_tooltip\').show();" onBlur="$(\'#'+key+'_tooltip\').hide();" ' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip !== 'undefined' ) && (tooltip.trim() != "")) ? '<span id="' + key + '_tooltip" class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>' : "") +
                 '</div>';
       break;
     case "float":
     case "int":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + '" style="width: 150px;" name="' + key + '" type="text" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' onChange="' + callback + ';" ' : "") +
                  (typeof value === 'undefined' ? '' : 'value="' + value.toString() + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + value.toString() + '" ') +
                  (((typeof validation === 'undefined') || (validation==0)) ? 'onFocus="$(\'#'+key+'_tooltip\').show();" onBlur="$(\'#'+key+'_tooltip\').hide();" ' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip !== 'undefined' ) && (tooltip.trim() != "")) ? '<span id="' + key + '_tooltip" class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>' : "") +
                 '</div>';
       break;
     case "boolean":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<input id="' + key + '" name="' + key + '" type="checkbox" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' data-callback="' + callback + ';" ' : "") +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' checked ' : '') +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') + '>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span><i class="icon"></i>') +
                 '</div>';
       break;
     case "list":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<select id="' + key + '" style="width: 300px;" name="' + key + '" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' onChange="' + callback + ';" ' : "") +
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
//*****************************************************************************
function showIdealformTooltip(obj) {
    obj.find(".tooltip").show()
}
//*****************************************************************************
function hideIdealformTooltip(obj) {
    obj.find(".tooltip").hide()
}
//*****************************************************************************
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
                gotoLogin();
             }, 10000);
           }
        }
    })
}
//*****************************************************************************
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

        jQuery.each( ["disablesmtp", "disableimap", "disableweather"], function( i, val ) {
          if (fields[val] != undefined)
             fields[val] = (fields[val] == "true" ? "false" : "true");
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
// Display the Addons Tab
//*****************************************************************************

function DisplayAddons(){
    var url = baseurl.concat("get_add_on_settings");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        var vpw = $(window).width();
        var gridWidth = Math.floor((vpw-240)/380);
            gridWidth = (gridWidth < 1) ? 1 : gridWidth;
        var currentGrid = 1;

        var  outstr = 'Available Add-ons:<br><br>';
        outstr += '<table border="0" style="border-collapse: separate; border-spacing: 20px;" width="100%"><tbody><tr><td valign="top">';

        $.each(Object.keys(result), function(i, addon) {
            var thisEnabled = ((typeof result[addon]["enable"] !== 'undefined' ) && (result[addon]["enable"].toString() == "true")) ? true : false;
            var thisIcon = result[addon]["icon"];
            outstr += '  <div class="card">';
            outstr += '    <form class="idealforms" style="border-spacing: 0px;" novalidate  id="' + addon + '_form">';
            outstr += '        <div id="' + addon + '_bg" align="center" style="width:360px; background-color:#e1e1e1; border-radius: 6px 6px 0px 0px; float:left;"><img id="' + addon + '_image" width="252px" class="'+thisIcon+'" src="images/transparent.png"></div>';
            outstr += '        <div id="' + addon + '_title" style="display: inline-block; float:center; margin-left:10px; margin-top: 5px; margin-bottom: 5px; width:265px" >'+result[addon]["title"]+'</div>';
            outstr += '        <div style="display: inline-block; clear:right; float:right; margin-top:5px; margin-right:10px; width:75px" class="field idealforms-field">' +
                      '          <input id="' + addon + '" name="' + addon + '" type="checkbox" style="margin:0px;padding:0px" data-callback="toggleCard(true,\'' + addon + '\',\'' + thisIcon + '\')"' +
                                 (thisEnabled ? ' checked ' : '') +
                                 (thisEnabled ? ' oldValue="true" ' : ' oldValue="false" ') + '>' +
                      '        </div>';
            outstr += '      <div style="clear: both;"></div>';
            outstr += '      <div id="' + addon + '_overview" style="margin:10px;font-size: 15px;">'+result[addon]["description"]+'<br><br><center><a target="_blank" href="'+result[addon]["url"]+'">Click for more information</a></center></div>';
            outstr += '      <div id="' + addon + '_settings" style="margin:10px;font-size: 15px;">';
            if ((result[addon]["parameters"] == null) || (Object.keys(result[addon]["parameters"]).length == 0)) {
               outstr += "No settings required for this addon";
            } else {
               $.each(Object.keys(result[addon]["parameters"]), function(j, param) {
                   var par = result[addon]["parameters"][param];
                   outstr += par["display_name"] + '<br>';
                   outstr += printSettingsField(par["type"], param, par["value"], par["description"], par["bounds"], "changedCard(true, '"+addon+"')") + '<div style="clear: both;"></div>';
               });
            }
            outstr += '      </div>';
            outstr += '    </form>';
            outstr += '    <center><button id="' + addon + '_save" onClick="saveAddon(\'' + addon + '\', \'' + result[addon]["title"] + '\')" style="align:center;">Save</button></center><br>';
            outstr += '  </div>';
            if (((i+1)/Object.keys(result).length) > (currentGrid/gridWidth)) {
               outstr += '</td><td valign="top">';
               currentGrid++;
            }
        });
        outstr += '</td></tr></tbody></table></form><br>';

        $("#mydisplay").html(outstr);
        $('input').lc_switch();
        $.extend($.idealforms.rules, {
           // The rule is added as "ruleFunction:arg1:arg2"
           HTTPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^(\\+(\\d{1,3}))?((\\(\\d{1,4}\\))|(\\d{1,3}))?(\\s|\-)?(\\d+(\\s?|\-?))+$', 'g');
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
            HTTPAddress: 'Must be a valid address from an internet server, eg. http://mail.google.com',
            InternetAddress: 'Must be a valid address from an internet server, eg. mail.google.com',
            IPAddress: 'Must be a valid IP address, eg. 192.168.1.100',
            InternationalPhone: 'Must be a valid Phone Number, eg. +1 123 456 7890',
            UnixFile: 'Must be a valid UNIX file',
            UnixDir: 'Must be a valid UNIX path',
            UnixDevice: 'Must be a valid UNIX file path starting with /dev/'
        });
        $('form.idealforms').idealforms({
           tooltip: '.tooltip',
           silentLoad: true,
        });

        $.each(Object.keys(result), function(i, addon) {
            var thisIcon = result[addon]["icon"];
            toggleCard(0, addon, thisIcon);
            $("#"+addon+"_save").hide(0);
        });

    }});
}
//*****************************************************************************
function toggleCard(animation, addon, icon) {
   if ($("#"+addon).is(":checked")) {
      $("#"+addon+"_bg").animate({backgroundColor: '#ffffff', width: '50px',  margin:'7px', padding: '0px', borderTopLeftRadius: 0, borderTopRightRadius: 0}, (animation ? 300 : 0));
      $("#"+addon+"_image").animate({backgroundColor: '#ffffff', width: '50px'}, 0);
      $("#"+addon+"_title").animate({width: '195px'}, 0);
      $("#"+addon+"_image").removeClass(icon);
      $("#"+addon+"_image").addClass(icon+"_small");
      $("#"+addon+"_overview").hide((animation ? 300 : 0));
      $("#"+addon+"_settings").show((animation ? 300 : 0));
   } else {
      $("#"+addon+"_bg").animate({backgroundColor: '#e1e1e1', width: '360px', margin:'0px', padding: '10px', borderTopLeftRadius: 6, borderTopRightRadius: 6}, (animation ? 300 : 0));
      $("#"+addon+"_image").animate({backgroundColor: '#e1e1e1', width: '252px'}, 0);
      $("#"+addon+"_title").animate({width: '265px'}, 0);
      $("#"+addon+"_image").removeClass(icon+"_small");
      $("#"+addon+"_image").addClass(icon);
      $("#"+addon+"_overview").show((animation ? 300 : 0));
      $("#"+addon+"_settings").hide((animation ? 300 : 0));
   }
   changedCard(animation, addon);
}
//*****************************************************************************
function changedCard(animation, addon) {
   var fields = {};

   $('#' + addon + '_form input').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = (($(this).attr('type') == "checkbox") ? ($(this).prop('checked') === true ? "true" : "false") : $(this).val());
            if (oldValue != currentValue) {
               fields[$(this).attr('name')] = currentValue;
            }
   });
   $('#' + addon + '_form select').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = $(this).val();
            if (oldValue != currentValue) {
               fields[$(this).attr('name')] = currentValue;
            }
   });

   if (Object.keys(fields).length > 0) {
      $("#"+addon+"_save").show((animation ? 300 : 0));
   } else {
      $("#"+addon+"_save").hide((animation ? 300 : 0))
   }
}
//*****************************************************************************
function saveAddon(addon, addonTitle){

    var DisplayStr = "Save settings for "+addonTitle+"? Are you sure?";
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
             saveAddonJSON(addon);
             var DisplayStr1 = 'Saving '+addonTitle+'...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){
                vex.closeAll();
                gotoLogin();
             }, 10000);

           }
        }
    })
}

//*****************************************************************************
function httpsUsed() {

    var url = window.location.href;
    return url.includes("https:")
}

//*****************************************************************************
function gotoLogin() {

    var url = window.location.href.split("/")[0].split("?")[0];
    window.location.href = url.concat("/logout");
}
//*****************************************************************************
function saveAddonJSON(addon) {
    try {
        var result = {};
             result[addon] = {};
             result[addon]["parameters"] = {};

        $('#' + addon + '_form input').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = (($(this).attr('type') == "checkbox") ? ($(this).prop('checked') === true ? "true" : "false") : $(this).val());
            if (oldValue != currentValue) {
               if ($(this).attr('name') == addon) {
                  result[addon]["enable"] = currentValue;
               } else {
                  result[addon]["parameters"][$(this).attr('name')] = currentValue;
               }
               $(this).attr('oldValue', currentValue);
            }
        });
        $('#' + addon + '_form select').each(function() {
            var oldValue = $(this).attr('oldValue');
            var currentValue = $(this).val();
            if (oldValue != currentValue) {
               result[addon]["parameters"][$(this).attr('name')] = currentValue;
               $(this).attr('oldValue', currentValue);
            }
        });

        // save settings
        var url = baseurl.concat("set_add_on_settings");
        $.getJSON(  url,
                    {set_add_on_settings: JSON.stringify(result)},
                    function(result){
        });

    } catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}

//*****************************************************************************
// Display the About Tab
//*****************************************************************************

function DisplayAbout(){
    var outstr = '<br><br><br><center><img src="images/GenmonLogo.png" width="60%"><br>';
    outstr += '<div class="aboutInfo"><br>Genmon<br>Version '+myGenerator["version"]+'<br><br><br>Developed by <a target="_blank" href="https://github.com/jgyates/">@jgyates</a>.<br><br>Published under the <a target="_blank" href="https://raw.githubusercontent.com/jgyates/genmon/master/LICENSE">GNU General Public License v2.0</a>.<br><br>Source: <a target="_blank" href="https://github.com/jgyates/genmon">Github</a><br><br>Built using Python & Javascript.<br>&nbsp;<br></center></div>';

    if (myGenerator["write_access"] == true) {
      // Update software
      outstr += '<center>Update Generator Monitor Software:<br><div id="updateNeeded" style="font-size:16px; margin:2px;"><br></div>';
      outstr += '&nbsp;&nbsp;<button id="checkNewVersion" onClick="checkNewVersion();">Upgrade to latest version</button><br>';
      outstr += '&nbsp;&nbsp;<a href="javascript:showChangeLog();" style="font-style:normal; font-size:14px; text-decoration:underline;">Change Log</a>';
      // Submit registers and logs
      outstr += '<br><br>Submit Information to Developers:<br><br>';
      outstr += '&nbsp;&nbsp;<button id="submitRegisters" onClick="submitRegisters();">Submit Registers</button>';
      outstr += '&nbsp;&nbsp;<button id="submitLogs" onClick="submitLogs();">Submit Logs</button>';
      //Backup
      outstr += '<br><br>Download Backup Files:<br><br>';
      outstr += '&nbsp;&nbsp;<button id="backupFiles" onClick="backupFiles();">Backup</button></center>';
    }

    $("#mydisplay").html(outstr);

    if (myGenerator["write_access"] == true) {
       if (latestVersion == "") {
         // var url = "https://api.github.com/repos/jgyates/genmon/releases";
         var url = "https://raw.githubusercontent.com/jgyates/genmon/master/genmonlib/program_defaults.py";
         $.ajax({dataType: "html", url: url, timeout: 4000, error: function(result) {
               console.log("got an error when looking up latest version");
               latestVersion = "unknown";
         }, success: function(result) {
               latestVersion = replaceAll((jQuery.grep(result.split("\n"), function( a ) { return (a.indexOf("GENMON_VERSION") >= 0); }))[0].split("=")[1], '"', '');
               latestVersion = latestVersion.trim()
               if (latestVersion != myGenerator["version"]) {
                     $('#updateNeeded').hide().html("<br>&nbsp;&nbsp;&nbsp;&nbsp;You are not running the latest version.<br>&nbsp;&nbsp;&nbsp;&nbsp;Current Version: " + myGenerator["version"] +"<br>&nbsp;&nbsp;&nbsp;&nbsp;New Version: " + latestVersion+"<br><br>").fadeIn(1000);
               }
         }});
       } else if ((latestVersion != "unknown") && (latestVersion != myGenerator["version"])) {
         $('#updateNeeded').html("<br>&nbsp;&nbsp;&nbsp;&nbsp;You are not running the latest version.<br>&nbsp;&nbsp;&nbsp;&nbsp;Current Version: " + myGenerator["version"] +"<br>&nbsp;&nbsp;&nbsp;&nbsp;New Version: " + latestVersion+"<br><br>");
       }
    }
}
//*****************************************************************************
function showChangeLog() {
    var DisplayStr = '<div id="changeLogText">Change Log<br><br>Loading...</div>';
    $('.vex-dialog-buttons').html(DisplayStr);
    var DisplayStrButtons = {
        CLOSE: {
          text: 'Close',
          type: 'button',
          className: 'vex-dialog-button-primary',
          click: function yesClick () { this.close() }
        },
    }

    var myDialog = vex.dialog.open({
        unsafeMessage: DisplayStr,
        overlayClosesOnClick: true,
        buttons: [
           DisplayStrButtons.CLOSE
        ],
    });

    var url = "https://raw.githubusercontent.com/jgyates/genmon/master/changelog.md";
    $.ajax({dataType: "html", url: url, timeout: 4000, error: function(result) {
       console.log("got an error when looking up latest version");
       latestVersion = "unknown";
    }, success: function(result) {
       vpw = $(window).width();
       vph = $(window).height();
       changeLog = replaceAll(result, '\n', '<br>\n');
       changeLog = changeLog.replace(/##(.*?)<br>/g, "<h2 style='font-size:14px'>$1</h2>")
       changeLog = changeLog.replace(/#(.*?)<br>/g, "<h1 style='font-size:18px; font-style:normal;'>$1</h1>")
       changeLog = changeLog.replace(/\n- (.*?)<br>/g, "\n<ul style='list-style-type: disc; list-style-position: outside; margin-left: 10px;'><li>$1</li></ul>")
       $('.vex-content').width(vpw-350).fadeIn(1000);
       $('.vex-content').height(vph-350).fadeIn(1000);
       $('#changeLogText').html("<div style='font-size:10px; line-height: normal; overflow-y: scroll; height:"+($('.vex-content').height() - 50)+"px'>"+changeLog+"</div>").fadeIn(1000);
    }});


}
//*****************************************************************************
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
       headers: {
          "Cache-Control": "no-cache"
        },
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
             // location.reload();
             setTimeout(function(){ vex.closeAll(); window.location.href = window.location.pathname+"?page=about"; }, 10000);
       }


    });
}
//*****************************************************************************
function backupFiles(){

    var link=document.createElement("a");
    link.id = 'backupLink'; //give it an ID
    link.href=baseurl.concat("backup");

    //use the following instead of link.click() so it will work on more browsers
    var clickEvent = new MouseEvent("click", {
      "view": window,
      "bubbles": true,
      "cancelable": false
    });
    link.dispatchEvent(clickEvent);


}
//*****************************************************************************
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
function submitLogs(){
    vex.dialog.confirm({
        unsafeMessage: 'Send the contents of your log files to the developer?<br>',
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                var url = baseurl.concat("sendlogfiles");
                $.getJSON(  url,
                   {},
                   function(result){});
             }
        }
    });
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
    if (lowbandwidth == false) {

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
}
//*****************************************************************************
function UpdateRegisters(init, printToScreen)
{
    if (init) {
      var now = new moment();
      regHistory["historySince"] = now.format("D MMMM YYYY H:mm:ss");
      regHistory["count_60m"] = 0;
      regHistory["count_24h"] = 0;
    } else if ((lowbandwidth == true) && (printToScreen == false)) {
      return
    }

    var url = baseurl.concat("registers_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(RegData){
        processAjaxSuccess();

        try{
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
                   var removed = regHistory["_10m"][reg_key].pop  // remove the last element
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
          }
          catch(err){
              console.log("Error in UpdateRegisters" + err)
          }
    }});
}
//*****************************************************************************
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
//*****************************************************************************
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

    if (lowbandwidth == false) {
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
    }

    $("#printRegisterFrame").printThis({canvas: true, importCSS: false, loadCSS: "css/print.css", pageTitle:"Genmon Registers", removeScripts: true});
    setTimeout(function(){ $("#printRegisterFrame").remove(); }, 1000);
}
//*****************************************************************************
function toHex(d) {
    return  ("0"+(Number(d).toString(16))).slice(-2).toUpperCase()
}

//*****************************************************************************
// Display the ADVANCED Settings Tab
//*****************************************************************************
function DisplayAdvancedSettings(){

    var url = baseurl.concat("get_advanced_settings");
    $.ajax({dataType: "json", url: url, timeout: 12000, error: processAjaxError, success: function(result){
        processAjaxSuccess();

        var outstr = '<form class="idealforms" novalidate  id="formSettings">ADVANCED Settings:<br><br><font color="red">Warning: These settings are intended for debugging and advanced users. Please proceed with caution.</font><br><br><fieldset id="generalSettings"><table id="allsettings" border="0">';
        var settings =  getSortedKeys(result, 2);
        for (var index = 0; index < settings.length; ++index) {
            var key = settings[index];
            outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">' + result[key][1] + '</td><td>' + printSettingsField(result[key][0], key, result[key][3], result[key][4], result[key][5]) + '</td></tr>';
        }
        outstr += '</table></fieldset></form><br>';
        outstr += '<button id="setadvancedsettingsbutton" onClick="saveAdvancedSettings()">Save</button>';

        $("#mydisplay").html(outstr);
        $('input').lc_switch();
        $.extend($.idealforms.rules, {
           // The rule is added as "ruleFunction:arg1:arg2"
           HTTPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(([a-z0-9]+([\-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^(\\+(\\d{1,3}))?((\\(\\d{1,4}\\))|(\\d{1,3}))?(\\s|\-)?(\\d+(\\s?|\-?))+$', 'g');
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
            HTTPAddress: 'Must be a valid address from an internet server, eg. http://mail.google.com',
            InternetAddress: 'Must be a valid address from an internet server, eg. mail.google.com',
            IPAddress: 'Must be a valid IP address, eg. 192.168.1.100',
            InternationalPhone: 'Must be a valid Phone Number, eg. +1 123 456 7890',
            UnixFile: 'Must be a valid UNIX file',
            UnixDir: 'Must be a valid UNIX path',
            UnixDevice: 'Must be a valid UNIX file path starting with /dev/'
        });
        $('form.idealforms').idealforms({
           tooltip: '.tooltip',
           silentLoad: true,
        });
   }});

}

//*****************************************************************************
// called when Save Settings is clicked
//*****************************************************************************
function saveAdvancedSettings(){

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
             saveAdvancedSettingsJSON();
             var DisplayStr1 = 'Saving...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){
                vex.closeAll();
             }, 10000);
           }
        }
    })
}
//*****************************************************************************
function saveAdvancedSettingsJSON() {
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

        jQuery.each( ["disablesmtp", "disableimap", "disableweather"], function( i, val ) {
          if (fields[val] != undefined)
             fields[val] = (fields[val] == "true" ? "false" : "true");
        });

        // save settings
        var url = baseurl.concat("set_advanced_settings");
        $.getJSON(  url,
                    {set_advanced_settings: $.param(fields)},
                    function(result){
        });

    } catch(err) {
        GenmonAlert("Error: invalid selection");
    }
}


//*****************************************************************************
//  called when menu is clicked
//*****************************************************************************
function MenuClick(page)
{
        oldMenuElement = menuElement;
        menuElement = page;
        RemoveClass();  // remove class from menu items
        // add class active to the clicked item
        $("#"+menuElement).find("a").addClass(GetCurrentClass());
        window.scrollTo(0,0);
        $("#registers").removeClass("settings");
        $("#registers").addClass("registers");
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
            case "journal":
                DisplayJournal();
                break;
            case "settings":
                DisplaySettings();
                break;
            case "addons":
                DisplayAddons();
                break;
            case "about":
                DisplayAbout();
                break;
            case "registers":
                if (oldMenuElement == "registers") {
                   menuElement = "adv_settings";
                   DisplayAdvancedSettings();
                } else {
                   $("#registers").addClass("settings");
                   $("#registers").removeClass("registers");
                   DisplayRegistersFull();
                }
                break;
            case "logout":
                var getUrl = window.location;
                var baseUrl = getUrl.protocol + "//" + getUrl.host;
                window.location.href = baseUrl.concat("/logout");
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
// GetStartupInfo - Get the current Generator Model and kW Rating
//*****************************************************************************
function GetStartupInfo()
{
    url = baseurl.concat("start_info_json");
    $.ajax({dataType: "json", url: url, timeout: 30000, error: processAjaxError, success: function(result){
      processAjaxSuccess();

      myGenerator = result;
      myGenerator["OldExerciseParameters"] = [-1,-1,-1,-1,-1,-1];
    }});
}

//*****************************************************************************
// SetHeaderValues - updates header to display site name
//*****************************************************************************
function SetHeaderValues()
{
   var HeaderStr = '<table border="0" width="100%" height="30px"><tr><td width="30px"></td><td width="90%">Generator Monitor at ' + myGenerator["sitename"] + '</td><td width="30px"><img id="logout" src="images/transparent.png" width="20px" height="20px">&nbsp;<img id="registers" class="registers" src="images/transparent.png" width="20px" height="20px"></td></tr></table>';
   $("#myheader").html(HeaderStr);
   $("#registers").on('click',  function() {  MenuClick("registers");});
   if (myGenerator["LoginActive"] == true) {
       $("#logout").addClass("logout");
       $("#logout").on('click',  function() {  MenuClick("logout");});
   }
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
//*****************************************************************************
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

function GenmonPrompt(title, msg, placeholder)
{
       vex.closeAll();
       vex.dialog.buttons.YES.text = 'Send';
       vex.dialog.open({ onSubmit: function(e) {
           e.preventDefault();
           if (vex.dialog.buttons.YES.text == "Send") {
             TestEmailSettingsWrapperSubmit($("#promptField").val())
           } else {
             vex.closeAll();
           }
        },
        unsafeMessage:  [title, "<br>",
        '<style>',
            '.vex-custom-field-wrapper {',
                'margin: 1em 0;',
            '}',
            '.vex-custom-field-wrapper > label {',
                'display: inline-block;',
                'margin-bottom: .2em;',
            '}',
        '</style>',
        '<div class="vex-custom-field-wrapper">',
            '<label for="date">'+msg+'</label>',
            '<div class="vex-custom-input-wrapper">',
                '<input name="promptField" style="width:100%" id="promptField" type="text" value="' + placeholder + '" />',
            '</div>',
        '</div>'].join(''), overlayClosesOnClick: false});
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
    } else if ((menuElement != "settings") && (menuElement != "notifications") && (menuElement != "journal") && (menuElement != "addons") && (menuElement != "about") && (menuElement != "adv_settings")) {
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

        try {
          myGenerator['ExerciseDay'] = result['ExerciseInfo']['Day'];
          myGenerator['ExerciseHour'] = result['ExerciseInfo']['Hour'];
          myGenerator['ExerciseMinute'] = result['ExerciseInfo']['Minute'];
          myGenerator['QuietMode'] = result['ExerciseInfo']['QuietMode'];
          myGenerator['ExerciseFrequency'] = result['ExerciseInfo']['Frequency'];
          myGenerator['EnhancedExerciseEnabled'] = ((result['ExerciseInfo']['EnhancedExerciseMode'] === "False") ? false : true);

          myGenerator['MonitorTime'] = result['MonitorTime'];
          myGenerator['RunHours'] = result['RunHours'];


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
                           var removed = kwHistory["data"].pop  // remove the last element
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

          switchState = result['switchstate'];
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
    }
    catch(err){
      console.log("Error in GetBaseStatus: " + err);
    }
   }});

   return
}
