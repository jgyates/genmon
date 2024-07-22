
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
    $("#footer").html('<table border="0" width="100%" height="30px"><tr><td width="5%"><img class="tooltip alert_small" id="ajaxWarning" src="images/transparent.png" height="28px" width="28px" style="display: none;"></td><td width="90%"><a href="https://github.com/jgyates/genmon" target="_blank">GenMon Project on GitHub</a></td><td width="5%" id="footerWeather" valign="middle" nowrap></td></tr></table>');
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
              // Added for better formatting 
              if (json[key].length > 1){
                outstr+= "<br>"
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
        useIdealFormsOnMaintPage = false;
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

            if (myGenerator['SetGenTime'] == true) {
              outstr += '<br><br>Generator Time:<br><br>';
              outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetTimeClick();">Set Generator Time</button>';
            }
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
               outstr += '<br><br>Reset:<br><br>';
               outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetPowerLogReset();">Reset Power Log & Fuel Estimate</button>';
            }
            try{
              if (("buttons" in myGenerator) && !(myGenerator['buttons'].length === 0)) {
                outstr += '<br><br>Generator Functions:<br><br>';
                for (let index in myGenerator['buttons']) {
                  button = myGenerator['buttons'][index];
                  button_command = button["onewordcommand"];
                  button_title = button["title"];
                  command_sequence = button["command_sequence"];
                  
                  if ((command_sequence.length >= 1) && (command_sequence[0].hasOwnProperty("input_title"))){
                    // this button has an input
                    outstr += setupCommandButton(button);
                    useIdealFormsOnMaintPage = true;
                  } else {
                    // This is just a button, no input from the user.
                    outstr += '&nbsp;&nbsp;<button id=' + button_command + ' onClick="SetClick(\'' + button_command + '\');">' + button_title + '</button><br><br>';
                  }
                }
              }
            } catch(err){
              console.log("Error parsing buttons: " + err)
            }
            
        }
            $("#mydisplay").html(outstr);
            if (useIdealFormsOnMaintPage){
              // if we had any buttons using tooltips then do this
              $('form.idealforms').idealforms({
                tooltip: '.tooltip',
                silentLoad: true,
              });

            }

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
// called to setup button for a command_sequence
//*****************************************************************************
function setupCommandButton(button){
  try{
    var outstr = "";
    var button_command = button["onewordcommand"];
    var button_title = button["title"];
    var command_sequence = button["command_sequence"];
    var button_id = 'button_' + button_command;
    var clickCallback = "onCommandButtonClick(\'" + button_command + "\')";

    
    outstr += '<form class="idealforms" novalidate  autocomplete="off" id="formButtons">';
    outstr += '<table>';
    
    // loop thru the list of commands in command_sequence
    for (let cmdidx in command_sequence){
      // cycle through each command in command_sequence
      outstr += '<tr>'
      
      if (cmdidx == 0){
        outstr += '<td>';
        outstr += '&nbsp;&nbsp;';
        // NOTE: type="button" is required or the ideal forms code will crash
        outstr += '<button class="button" type="button" id="' + button_id + '" style="background:#bbbbbb;color:#000000;float:none" onclick="' + clickCallback + ';" > ' + button_title + '</button>';
        outstr += '</td>';
      }
      else{
        outstr += '<td></td>';  // empty table cell
      }
      outstr += '<td>';
      // div for ideamfrom must go in table data element
      outstr += '<div class="field idealforms-field idesforms-text-field style="clear:both">';
      command = command_sequence[cmdidx]
      if ((command.hasOwnProperty("input_title")) && (command.hasOwnProperty("type"))) {
        title = command["input_title"];
        type = command["type"];
        tooltip = ""
        bounds = ""
        if (command.hasOwnProperty("bounds_regex")){
          bounds = command["bounds_regex"];
        }
        if (command.hasOwnProperty("tooltip")){
          tooltip = command["tooltip"];
        }
        var default_value = 0;
        outstr += setupInputBoxForButton(cmdidx, button_command, type, title, default_value, tooltip, bounds );
      }
      else{
        console.log("Error: button command_sequence does not have both 'input_title' and 'type'.");
      }
      outstr += '</div>';
      outstr += '</td>';
      outstr += '</tr>'
    }

    // if we added a control then go to the next line
    outstr += '</table>';
    outstr += '</form>'
    outstr += '<br>';
    
    return outstr;
  }
  catch(err){
    console.log("Error in setupCommandButton: " + err);
    return "";
  }
}
//*****************************************************************************
// called to setup input button
//*****************************************************************************
function setupInputBoxForButton(identifier, parent, type, title, default_value, tooltip, bounds_regex ) {

  var outstr = ""
  try {

    if (!(type === "int")){
      // at the moment only "int" is supported
      console.log("Error in setupInputBoxForButton: only type 'int' supported at the moment.")
      return outstr;
    }
    var id = parent + "_" + identifier
    var input_id = "input_"+ id;
    // used for forms
    var changeCallback = "validateInputButton(\'change\', \'" + identifier + "\', \'" + parent + "\', \'" + bounds_regex + "\')";
    var rulename = input_id + '_rule'
    var validation = rulename;

    outstr += '&nbsp;&nbsp;';
    outstr += '<input id="' + input_id +  '" style="width: 150px;clear:both;float:none" autocomplete="off" name="' + input_id + '" type="text" ';
    outstr += ' onChange="' + changeCallback + ';" ';
    outstr += (((typeof validation === 'undefined') || (validation==0)) ? 'onFocus="$(\'#'+input_id+'_tooltip\').show();" onBlur="$(\'#'+input_id+'_tooltip\').hide();" ' : 'data-idealforms-rules="' + validation + '" ') ;

    outstr += '>';  // end input box
    outstr += '&nbsp; ' + title;

    outstr += '<span class="error" style="display: none;"></span>';
    outstr += (((typeof tooltip !== 'undefined' ) && (tooltip.trim() != "")) ? '<span id="' + input_id + '_tooltip" class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>' : "");

    //add the regex as a rule for idealforms
    $.extend($.idealforms.rules, {
      [rulename]:  function(input, value, arg1, arg2) {
        var regex = RegExp(bounds_regex, 'g');
        return regex.test(value);
      }
    });
    $.extend($.idealforms.errors, {
      [rulename]: tooltip
    });

    outstr += '<br>';
    return outstr;
  }
  catch(err) {
    console.log("Error in setupInputBoxForButton: " + err);
  }
  return outstr;
}

//*****************************************************************************
// given a button one word command, retrieve the containing button object
//*****************************************************************************
function getButtonFromCommand(onewordcommand){

    if (("buttons" in myGenerator) && !(myGenerator['buttons'].length === 0)) {
      // cycle thru the buttons in our list
      for (let index in myGenerator['buttons']) {
        button = myGenerator['buttons'][index];
        button_command = button["onewordcommand"];
        if (onewordcommand == button_command){
          return button;
        }
      }
    }
    // did not find the button requested
    console.log("Error in getButtonCommand: button not found: " + onewordcommand)
    return null;
}
//*****************************************************************************
// called when sending button input to genmon
//*****************************************************************************
function sendButtonCommand(button_object)
{
  try{
      if ((!(button_object.hasOwnProperty("onewordcommand"))) || 
          (!(button_object.hasOwnProperty("title"))) ||
          (!(button_object.hasOwnProperty("command_sequence"))))
      {
        console.log("Error: invalid  of button object.");
        return false;
      }
      // set button command
      // the button_object is one of the button elemnts in the list
      // the input to set_button_command is a list of button objects
      // only send the buttons in the list that you want to the commands
      // to be sent.
      // myGenerator['buttons'] list with the 'value' property added 
      // to the command_sequence, 
      // e.g. myGenerator['buttons'][0]['command_sequence][0]['value'] = user defined input
      var error_occured = false;
      var input =  JSON.stringify([button_object]);
      var url = baseurl.concat("set_button_command");
      $.getJSON(  url,
                  {set_button_command: input},
                  function(result){
          // result should be either "OK" or error string.
          if (result !== "OK"){
            console.log("Error: failure sending set_button_command: " + result);
            error_occured = true;
            return false;
          }
      });
      return (error_occured == false);
  }
  catch (err){
    console.log("Error in setButonCommand: " + err);
    return false;
  }
}

//*****************************************************************************
//
//*****************************************************************************
function onCommandButtonClick(onewordcommand){

    try{
      
      var button = getButtonFromCommand(onewordcommand);
      if (button == null){
        console.log("Error in onCommandButtonClick: button object not found.");
        return false;
      }
      var button_title = button["title"];

      if (!validateButtonCommand(onewordcommand)){
        return false;
      }

      
      DisplayStrAnswer = false;
      msg = 'Issue generator command: ' + button_title + '?<br><span class="confirmSmall">Are you sure you want to isssue this command?</span>';

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
      unsafeMessage: msg,
      overlayClosesOnClick: false,
      buttons: [
        DisplayStrButtons.YES,
        DisplayStrButtons.NO
      ],
      onSubmit: function(e) {
        if (DisplayStrAnswer) {
          DisplayStrAnswer = false; // Prevent recursive calls.
          e.preventDefault();
          issueButtonCommand(onewordcommand);
          var DisplayStr1 = 'Sending Command '+button_title +'...';
          var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
          $('.vex-dialog-message').html(DisplayStr1);
          $('.vex-dialog-buttons').html(DisplayStr2);
          $('.progress-bar-fill').queue(function () {
                $(this).css('width', '100%')
          });
          setTimeout(function(){
              vex.closeAll();
              //gotoLogin();
          }, 5000);
          }
        }
      });
      return true;
    }

    catch(err){
      console.log("Error in onCommandButton: " + err);
      return false;
    }
}
//*****************************************************************************
//
//*****************************************************************************
function validateButtonCommand(onewordcommand){
  try{
    // here we want to loop thru the command_sequence arrary, getting the 
    // data for each input box it corrosponds to, validate the data with the
    // bounds_regex parameter, if it exists. 
    var button = getButtonFromCommand(onewordcommand);
    if (button == null){
      console.log("Error in validateButtonCommand: button object not found.");
      return false;
    }
    var button_title = button["title"];
    var command_sequence = button["command_sequence"];
    // loop thru the list of commands in command_sequence
    for (let cmdidx in command_sequence){
      // cycle through each command in command_sequence
      command = command_sequence[cmdidx];
      if ((command.hasOwnProperty("input_title")) && (command.hasOwnProperty("type"))) {
        title = command["input_title"];
        bounds = ""
        if (command.hasOwnProperty("bounds_regex")){
          bounds = command["bounds_regex"];
        }
        var input_id = "input_"+ onewordcommand + "_" + cmdidx;
        var value = document.getElementById(input_id).value;
        if (!(validateRegEx(value, bounds, dialog_on_error = true))){
          return false;
        }
      }
      else{
        console.log("Error in validateButtonCommand: button command_sequence does not have both 'input'title' and 'type': " + button_title);
        return false;
      }
    }
    return true;
  }
  catch(err){
    console.log("Error in validateButtonCommand: " + err);
      return false;
  }
}
//*****************************************************************************
//
//*****************************************************************************
function issueButtonCommand(onewordcommand){
  try{
      // here we want to loop thru the command_sequence arrary, getting the 
      // data for each input box it corrosponds to, then write the value to the entry in 
      // the command_sequence and send the entire command_button object to genmon.
      var original_button = getButtonFromCommand(onewordcommand);
      if (original_button == null){
        console.log("Error in issueButtonCommand: button object not found.");
        return false;
      }
      let button = { ...original_button };    // clone the button object
      var button_title = button["title"];
      var command_sequence = button["command_sequence"];
      // loop thru the list of commands in command_sequence
      for (let cmdidx in command_sequence){
        // cycle through each command in command_sequence
        command = command_sequence[cmdidx];
        if ((command.hasOwnProperty("input_title")) && (command.hasOwnProperty("type"))) {
          title = command["input_title"];
          type = command["type"];

          var input_id = "input_"+ onewordcommand + "_" + cmdidx;
          var value = document.getElementById(input_id).value;
          if (type == "int"){
            // write the value to the object
            command['value'] = parseInt(value);
          }
          else {
            console.log("Error: unsupported type in issueButtonCommand: " + type + ", " + button_title);
            return false;
          }
        }
        else{
          console.log("Error in issueButtonCommand: button command_sequence does not have both 'input'title' and 'type': " + button_title);
          return false;
        }
      }
      // now send the button to genmon for writing 
      // for now we only send one button at a time. 
      sendButtonCommand(button);
  }
  catch(err){
      console.log("Error in issueButtonCommand: " + err);
      return false;
  }
}
//*****************************************************************************
// called when validating input button
// action is "validate", "click" or "change"
//  click - validate and send data
//  validate - check data and send mesage to user on invalid data
//  change - check the data, return true if data OK, otherwise false
// identifier is the index of the command_sequence in a given button object
// parent is the 'onewordcommand' of the parent
// bounds_regex is the regular expession string to bounds check the input 
//*****************************************************************************
function validateInputButton(action, identifier, parent, bounds_regex){

    //console.log("Input Validation called: " + action + ", " + identifier + ", " + parent)

    try{
      // TODO this only does one input now. need to read (and validate) all inputs 
      // and fill them into the command_sequence then send them to genmon
      // the function parameter bounds_regex should be changed as this will come from the 
      // button_object.command_sequence array entries 
      var button_object = getButtonFromCommand(parent);
      if (button_object == null){
        console.log("Error in validateInputButton: button object not found.");
        return false;
      }
      var button_title = button_object['title'];
      // get the input value for the corrosponding button
      var id = parent + "_" + identifier
      var input_id = "input_"+ id;
      var value = document.getElementById(input_id).value
      
      switch (action) {
        case "validate":
        case "change":
          return validateRegEx(value, bounds_regex, dialog_on_error = (action === "validate"));
        case "click":
          if (!(validateInputButton("validate", identifier, parent, bounds_regex))){
            return false;
          }
          // send data to genmon
          return true;
        default:
          console.log("Error: Invalid action in validateInputButton!");
          return false;
      }
    }
    catch(err){
      console.log("Error in validateInputButton: " + err);
      return false;
    }
    return false;
}
//*****************************************************************************
// validate a value with a regex string, return true or false
//*****************************************************************************
function validateRegEx(value, bounds_regex, dialog_on_error = true){
  try{
    var bounds = new RegExp(bounds_regex);
    if (!(bounds.test(value))){
      if (dialog_on_error){
        GenmonAlert("The input is invalid for this parameter.");
      }
      return false;
    }
    return true;
  }
  catch(err){
    console.log("Error in validateRegEx: " + bounds_regex + ": " + err);
    return false;
  }
}
//*****************************************************************************
// submit for button commands
//*****************************************************************************
function submitButton(ctlid, identifier, parent){
  try{
    console.log("ID:" + ctlid + ", Index: " + identifier+ ", Parent: " + parent )
    //console.log("value: " + document.getElementById(ctlid).value)
  }
  catch(err){
    console.log("Error in submitButton: " + err)
  }
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
       default:
          button = getButtonFromCommand(cmd);
          if (button == null){
            console.log("Error in SetClick: button object not found.");
            return;
          }
          button_title = button['title']
          msg = 'Issue generator command: ' + button_title + '?<br><span class="confirmSmall">Are you sure you want to isssue this command?</span>';
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

        var DisplayMsg = "Set exercise time to<br>" + strExerciseTime + ", " + strQuiet + "?";

        if (myGenerator['WriteQuietMode'] == false) {
            DisplayMsg = "Set exercise time to<br>" + strExerciseTime + "?";
        }
        vex.dialog.confirm({
            unsafeMessage: DisplayMsg,
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

                    // set quiet mode
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
// Display Logs
//*****************************************************************************
function DisplayLogs(){

    var url = baseurl.concat("logs_json");
    $.ajax({dataType: "json", url: url, timeout: 4000, error: processAjaxError, success: function(result) {
        processAjaxSuccess();
        try{
            var LogData = result;
            var outstr = '<center><div id="annualCalendar"></div></center>';
            outstr += json2html(result, "", "root");
            $("#mydisplay").html(outstr);
            if (!(lowbandwidth == false)){
              // don't display heat map
              return
            }
        }
        catch(err){
          console.log("Error in DisplayLogs (log display):" + err)
          return 
        }
        // check myGenerator[“AltDateformat”] == true to change date format from mm/dd/yyyy to dd/mm/yyyy
        // so heat map can parse the data correctly
        try{
          var severity = 0;
          var months = 1;
          var date = new Date();
          var data_helper = {};
          for (const [logname, logarray] of Object.entries(LogData["Logs"])) {
            //console.log(`${logname}: `);
            if (logname.toLowerCase().includes("alarm")){  // ALARM log
              severity = 3;
            } else if(logname.toLocaleLowerCase().includes("service")){ // service log
              severity = 2;
            } else if(logname.toLocaleLowerCase().includes("run")){   // run log
              severity = 1;
            };
              
            for (entry of logarray) {
              //console.log(entry);
              var matches = entry.match(/^\s*(\d+)\/(\d+)\/(\d+) (\d+:\d+:\d+) (.*)$/i);
              if ((matches == undefined) || (matches.length != 6)) {
                continue;
              }
              // e.g. matches =  ["07/17/23 08:58:25 Switched Off", "07", "17", "23", "08:58:25", "Switched Off"]

              var MM;
              var DD; 
              var YY;
              if (myGenerator["AltDateformat"] == true){
                // DD/MM/YYYY
                MM = matches[2]
                DD = matches[1]
                YY = matches[3]
              }
              else{
                // MM/DD/YYYY
                MM = matches[1]
                DD = matches[2]
                YY = matches[3]
              };
              var logtext = matches[5].trim()
              var entrydate = YY + '/' + MM + '/' + DD;
              if ((12 * YY + 1 * MM + 12) <= (12*(date.getYear()-100) + date.getMonth() + 1)) {
                // date before our cutoff
                continue;
              } 
              if(data_helper[entrydate] == undefined){
                // no entry for this date yet so add one
                MonthIndex = parseInt(MM) - 1
                formatteddate = DD+' ' + MonthsOfYearArray[MonthIndex] + ' 20'+YY
                data_helper[entrydate] = {count: severity, date: '20'+YY+'-'+MM+'-'+DD, dateFormatted: formatteddate, title: logtext};
                if (((12*(date.getYear()-100) + date.getMonth() + 1)-(12 * YY + 1 * MM) + 1) > months) {
                  months = (12 * (date.getYear()-100) + date.getMonth() + 1) - (12 * YY + 1 * MM) + 1;
                }
              }
              else{
                // already an entry for this date
                data_helper[entrydate]["title"] = data_helper[entrydate]["title"] + "<br>" + logtext;
                if (data_helper[entrydate]["count"] < severity)
                   data_helper[entrydate]["count"] = severity;
              }
            };
          };

          var data = Object.keys(data_helper).sort().map(function(itm) { return data_helper[itm]; });
          var options = {coloring: 'genmon',
                         start: new Date((date.getMonth()-12 < 0) ? date.getYear() - 1 + 1900 : date.getYear() + 1900, (date.getMonth()-12 < 0) ? date.getMonth()+1 : date.getMonth()-12, 1),
                         end: new Date(date.getYear() + 1900, date.getMonth(), date.getDate()) ,
                         months: months, lastMonth: date.getMonth()+1, lastYear: date.getYear() + 1900,
                         labels: { days: true, months: true, custom: {monthLabels: "MMM 'YY"}}, tooltips: { show: true, options: {}}, legend: { show: false}};
          $("#annualCalendar").CalendarHeatmap(data, options);
        }  // end try
        catch(err){
          console.log("Error in DisplayLogs (heatmap display):" + err)
          return
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

        var  outstr = 'Notification Recipients:<br><br>';
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
       GenmonAlert("Recipients cannot be blank.<br>You have "+blankEmails+" blank lines.");
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
             var DisplayStr1 = 'Saving...';
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-message').html(DisplayStr1);
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
        outstr += '<br><br><button value="Print" id="printJournal">Print Journal</button>';

        $("#mydisplay").html(outstr);

        $(".edit#editJournalRow").on('click', function() {
           id = $(this).attr("row");
           var outstr = emptyJournalLine("amend", id, allJournalEntries[id]["date"], allJournalEntries[id]["type"], allJournalEntries[id]["hours"], allJournalEntries[id]["comment"])
           $("#row_"+id).replaceWith(outstr);
           $("input[name^='time_"+id+"']").timepicker({ 'timeFormat': 'H:i' });
           $("input[name^='date_"+id+"']").datepicker({ dateFormat: 'mm/dd/yy' });
           $("#comment_"+id).val(allJournalEntries[id]["comment"].replace( /\<br\>/g, '\n' ));
        });

        $(".remove_bin#deleteJournalRow").on('click', function() {
           id = $(this).attr("row");
           DeleteJournalRow(id);
        });

        $(document).ready(function() {
           $("#addJournalRow").click(function () {
                  id = $("#alljournal").length+1
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

           $("#printJournal").click(function () {
              printJournal(result);
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
   outstr += '     <div style="margin:10px;font-size:15px;text-align:left;">'+comment+'</div>';
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
   outstr += '           <tr><td align="right" style="padding:3px">Type: &nbsp;&nbsp;&nbsp;</td><td style="padding:3px"><select id="type_' + rowcount + '" name="type_' + rowcount + '" >';
   outstr += '               <option value="Repair" ' + (type.toLowerCase() == "repair"  ? ' selected="selected" ' : '') + '>Repair</option>';
   outstr += '               <option value="Check" ' + (type.toLowerCase() == "check"  ? ' selected="selected" ' : '') + '>Check</option>';
   outstr += '               <option value="Observation" ' + (type.toLowerCase() == "observation"  ? ' selected="selected" ' : '') + '>Observation</option>';
   outstr += '               <option value="Maintenance" ' + (type.toLowerCase() == "maintenance"  ? ' selected="selected" ' : '') + '>Maintenance</option></select></td></tr>';
   outstr += '           <tr><td align="right" style="padding:3px">Service Hours: &nbsp;&nbsp;&nbsp;</td><td style="padding:3px"><input id="hours_' + rowcount + '" name="hours_' + rowcount + '" type="text" value="'+hours+'"></td></tr>';
   outstr += '         </table></center>';
   outstr += '     </div>';
   outstr += '     <div style="clear: both;"></div>';
   outstr += '     <div style="margin:15px;font-size: 15px;"><textarea id="comment_' + rowcount + '" name="comment_' + rowcount + '" rows="4" style="width:100%;">'+comment.replace( /\<br\>/g, '\n' )+'</textarea></center></div>';
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
             setTimeout(function(){ 
              vex.closeAll();
              gotoRoot();
            }, 2000); 
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
            hours: parseFloat($("input[name^='hours_"+rowcount+"']").val()),                                     // Must be a number (integer or floating point)
            comment: $("textarea[name^='comment_"+rowcount+"']").val().replace( /\n/g, '<br>' )               // Text string
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
function printJournal (data) {
    var pageHeight = 20;
    var rowHeight = 15;
    var dataDivider;

    dataDivider = 12;

    $('<div id="printJournalFrame" style="width:1000px"></div>').appendTo("#mydisplay");

    var now = new moment();
    var outstr = '<br><center><h1>Generator Journal for '+myGenerator["sitename"]+'</h1><br>';
    outstr += '<h2>As of: '+now.format("D MMMM YYYY H:mm:ss")+'</h2><br>';
    outstr += '<table width="1000px" border="0"><tr><td class="printRegisterTDtitle" nowrap>Type / Date / Service Hours</td><td class="printRegisterTDtitle">Comment</td></tr>';

    $.each(Object.keys(data), function(i, key) {

        pageHeight += rowHeight;
        if (pageHeight < 100) {
             outstr += '';
        } else {
             outstr += '</table><div class="pagebreak"> </div><table width="1000px" border="0"><tr><td class="printRegisterTDtitle" nowrap>Type / Date / Service Hours</td><td class="printRegisterTDtitle">Comment</td></tr>';
             pageHeight = 0;
        }
        rowHeight = Math.round(data[i]["comment"].length / 160)*15;

        var reg_val = data[key][0];

        outstr += '<tr><td width="40%" class="printRegisterTD" nowrap>' +  data[i]["type"] + '<br>on:' + data[i]["date"] + '<br>at: ' + data[i]["hours"] + ' hrs</td>';
        outstr += '<td width="60%" class="printRegisterTD"><br>' +  data[i]["comment"] + '</td></tr>';
    });
    outstr += '</table></center>';
    $("#printJournalFrame").html(outstr);

    $("#printJournalFrame").printThis({canvas: true, importCSS: false, loadCSS: "css/print.css", pageTitle:"Genmon Journal", removeScripts: true});
    setTimeout(function(){ $("#printJournalFrame").remove(); }, 1000);
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
            } else if (key == "modbus_tcp") {
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
             //var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             var regex = RegExp("^(?:https?:\/\/)(?!$)(?:www\.)?[a-zA-Z]*(?:\.[a-zA-Z]{2,6})?(?:(?:\d{1,3}\.){3}\d{1,3})?", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^((([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))|((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^[0-9\-().+\s]{10,20}$', 'g');
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
function printSettingsField(type, key, value, tooltip, validation, callback, parent = "", name = "") {
   var outstr = "";
   switch (type) {
     case "string":
     case "password":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + parent + '" style="width: 300px;" name="' + key + '" type="' + ((type == "password") ? "password" : "text") + '" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' onChange="' + callback + ';" ' : "") +
                  (typeof value === 'undefined' ? '' : 'value="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + replaceAll(value, '"', '&quot;') + '" ') +
                  (((typeof validation === 'undefined') || (validation==0)) ? 'onFocus="$(\'#'+key+parent+'_tooltip\').show();" onBlur="$(\'#'+key+parent+'_tooltip\').hide();" ' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip !== 'undefined' ) && (tooltip.trim() != "")) ? '<span id="' + key + parent + '_tooltip" class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>' : "") +
                 '</div>';
       break;
     case "float":
     case "int":
       outstr += '<div class="field idealforms-field">' +
                 '<input id="' + key + parent +  '" style="width: 150px;" name="' + key + '" type="text" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' onChange="' + callback + ';" ' : "") +
                  (typeof value === 'undefined' ? '' : 'value="' + value.toString() + '" ') +
                  (typeof value === 'undefined' ? '' : 'oldValue="' + value.toString() + '" ') +
                  (((typeof validation === 'undefined') || (validation==0)) ? 'onFocus="$(\'#'+key+parent+'_tooltip\').show();" onBlur="$(\'#'+key+parent+'_tooltip\').hide();" ' : 'data-idealforms-rules="' + validation + '" ') + '>' +
                 '<span class="error" style="display: none;"></span>' +
                  (((typeof tooltip !== 'undefined' ) && (tooltip.trim() != "")) ? '<span id="' + key + parent + '_tooltip" class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span>' : "") +
                 '</div>';
       break;
     case "boolean":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<input id="' + key + parent +  '" name="' + key + '" type="checkbox" ' +
                  (((typeof callback !== 'undefined' ) && (callback != "")) ? ' data-callback="' + callback + ';" ' : "") +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' checked ' : '') +
                  (((typeof value !== 'undefined' ) && (value.toString() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') + '>' +
                  (((typeof tooltip === 'undefined' ) || (tooltip.trim() == "")) ? '' : '<span class="tooltip" style="display: none;">' + replaceAll(tooltip, '"', '&quot;') + '</span><i class="icon"></i>') +
                 '</div>';
       break;
     case "list":
       outstr += '<div class="field idealforms-field" onmouseover="showIdealformTooltip($(this))" onmouseout="hideIdealformTooltip($(this))">' +
                 '<select id="' + key + parent +  '" style="width: 300px;" name="' + key + '" ' +
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
                   outstr += printSettingsField(par["type"], param, par["value"], par["description"], par["bounds"], "changedCard(true, '"+addon+"')", parent = addon, name = par["display_name"]) + '<div style="clear: both;"></div>';
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
             //var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             var regex = RegExp("^(?:https?:\/\/)(?!$)(?:www\.)?[a-zA-Z]*(?:\.[a-zA-Z]{2,6})?(?:(?:\d{1,3}\.){3}\d{1,3})?", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^[0-9\-().+\s]{10,20}$', 'g');
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
function gotoRoot() {

  var url = window.location.href.split("/")[0].split("?")[0];
  window.location.href = url;
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
    vpw = $(window).width();
 
    var outstr = '<br><br><br><center><img src="images/GenmonLogo.png" width="'+Math.round((vpw-200)*0.6)+'px" height="'+Math.round(((vpw-200)*0.6)*(242/1066))+'px"><br>';
    outstr += '<div class="aboutInfo"><br>Genmon<br>Version <span id="about_version">'+myGenerator["version"]+'</span><br><br><br>Developed by <a target="_blank" href="https://github.com/jgyates/">@jgyates</a>.<br><br>Published under the <a target="_blank" href="https://raw.githubusercontent.com/jgyates/genmon/master/LICENSE">GNU General Public License v2.0</a>.<br><br>Source: <a target="_blank" href="https://github.com/jgyates/genmon">Github</a><br><br>Built using Python & Javascript.<br>&nbsp;<br></center></div>';

    if (myGenerator["write_access"] == true) {
      // Update software
      outstr += '<center>Update Generator Monitor Software:<br><div id="updateNeeded" style="font-size:16px; margin:2px;"><br></div>';
      outstr += '&nbsp;&nbsp;<button id="checkNewVersion" onClick="checkNewVersion();">Upgrade to latest version</button><br>';
      outstr += '&nbsp;&nbsp;<a href="javascript:showChangeLog();" style="font-style:normal; font-size:14px; text-decoration:underline;">Change Log</a>';
      // Submit registers and logs
      outstr += '<br>Submit Information to Developers:<br>';
      outstr += 'NOTE: outbound email must be setup and working to submit logs or registers<br><br>';
      outstr += '&nbsp;&nbsp;<button id="submitRegisters" onClick="submitRegisters();">Submit Registers</button>';
      outstr += '&nbsp;&nbsp;<button id="submitLogs" onClick="submitLogs();">Submit Logs</button>';
      //Get Backup
      outstr += '<br><br>Download Backup Files:<br><br>';
      // TODO
      //outstr += '<br><br>Download Backup Files or Restore Backup:<br><br>';
      
      outstr += '&nbsp;&nbsp;<button id="backupFiles" onClick="backupFiles();">Backup</button>';
      // TODO
      //outstr += '&nbsp;&nbsp;<button id="restoreFiles" onClick="restoreFiles();">Restore</button>';
      //Get Log Files
      outstr += '<br><br>Download Log Files:<br><br>';
      outstr += '&nbsp;&nbsp;<button id="logFiles" onClick="logFiles();">Log Files</button></center>';
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
               } else {
                     $('#updateNeeded').html("").fadeIn(1000);
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
             setTimeout(function(){ vex.closeAll(); window.location.href = window.location.pathname+"?page=about&reload=true"; }, 10000);
       }


    });
}

//*****************************************************************************
function restoreFiles(){
    // TODO
    let input = document.createElement('input');
    input.type = 'file';
    input.onchange = _ => {
      // you can use this method to get file and perform respective operations
      let files =   Array.from(input.files);
      console.log(files);
    };
    input.click();
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
function logFiles(){

    var link=document.createElement("a");
    link.id = 'logLink'; //give it an ID
    link.href=baseurl.concat("get_logs");

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
function sendServerCommand(cmd){

    var msg = "";

    switch (cmd) {
       case "restart":
          msg = 'Restart Genmon Software?<br><span class="confirmSmall">Are you sure you want to restart your Genmon software?</span>';
          break;
       case "reboot":
          msg = 'Reboot System?<br><span class="confirmSmall">Are you sure you want to reboot your Genmon host?</span>';
          break;
       case "shutdown":
          msg = 'Shutdown System?<br><span class="confirmSmall">Are you sure you want to shutdown your genmon host? NOTE: THIS CANNOT BE UNDONE VIA THE GUI OR COMMAND LINE AND YOU MAY HAVE TO ACCESS YOUR GENERATOR TO PHYSICALLY RESTART THE HOST AGAIN.</span>';
          break;
    }

    vex.dialog.confirm({
        unsafeMessage: msg,
        overlayClosesOnClick: false,
        callback: function (value) {
             if (value == false) {
                return;
             } else {
                var url = baseurl.concat(cmd);
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

    var RegTypes = ['Holding', 'Inputs', 'Coils'];
    $.each(RegTypes, function(i, reg_type){
      if (!(regHistory["_10m"].hasOwnProperty(reg_type))){
        // no data for this register
        return;
      }
      $.each(Object.keys(regHistory["updateTime"][reg_type]).sort(), function(i, reg_key) {
          if ((i % 4) == 0){
          outstr += '</tr><tr>';
          }

          var reg_val = regHistory["_10m"][reg_type][reg_key][0];

          outstr += '<td width="25%" class="registerTD">';
          outstr +=     '<table width="100%" heigth="100%" id="val_'+reg_type+'_'+reg_key+'">';
          outstr +=     '<tr><td align="center" class="registerTDtitle">' + BaseRegistersDescription[reg_type][reg_key] + '</td></tr>';
          outstr +=     '<tr><td align="center" class="registerTDsubtitle">(' + reg_type+':'+reg_key + ')</td></tr>';
          outstr +=     '<tr><td align="center" class="tooltip registerChart" id="content_'+reg_type+'_'+reg_key+'">';
          outstr +=        ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
          // This handles the case for byte data returning Not a Number (NaN) for coil registers
          var strHi = ((parseInt(reg_val) & 0xff00) >> 8).toString()
          var strLo = (parseInt(reg_val) & 0x00ff).toString()
          outstr +=        ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+strHi +':'+ strLo +'</span>');
          outstr +=     '</td></tr>';
          outstr +=     '</table>';
          outstr += '</td>';
      });
    
      if ((regHistory["_10m"][reg_type].length % 4) > 0) {
        for (var i = (regHistory["_10m"][reg_type].length % 4); i < 4; i++) {
          outstr += '<td width="25%" class="registerTD"></td>';
        }
      }
    });
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
            var reg_type = regId.split('_')[0]
            var reg_key = regId.split('_')[1]
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
               if (regHistory["_10m"][reg_type][reg_key].length > i)
                   plot_data1.push([-i/12, parseInt(regHistory["_10m"][reg_type][reg_key][i], 16)]);
               if (regHistory["_60m"][reg_type][reg_key].length > i)
                   plot_data2.push([-i/2, parseInt(regHistory["_60m"][reg_type][reg_key][i], 16)]);
               if (regHistory["_24h"][reg_type][reg_key].length > i)
                   plot_data3.push([-i/5, parseInt(regHistory["_24h"][reg_type][reg_key][i], 16)]);
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
            var localRegData = null;
            var RegTypes = ['Holding', 'Inputs','Coils'];
            $.each(RegTypes, function(i, reg_type){
              
              if (!(RegData.Registers.hasOwnProperty(reg_type))){
                // no data for this register
                return;
              }
              if (Object.keys(RegData.Registers[reg_type]).length < 1){
                // no data for this register
                return
              }
              localRegData = RegData.Registers[reg_type]
            
              if (localRegData == null){
                return
              }
              $.each(localRegData, function(i, item) {
                  var reg_key = Object.keys(item)[0]
                  var reg_val = item[Object.keys(item)[0]];

                  if ((init) || (regHistory["_10m"][reg_type] == undefined) || (regHistory["_10m"][reg_type][reg_key] == undefined)) {
                      // reg has not been set before in regHistory so do it now
                      if (regHistory["_10m"][reg_type] == undefined) {
                        regHistory["updateTime"][reg_type] = {}
                        regHistory["_10m"][reg_type] = {}
                        regHistory["_60m"][reg_type] = {}
                        regHistory["_24h"][reg_type] = {}
                      }
                      if (regHistory["_10m"][reg_type][reg_key] == undefined){
                        regHistory["updateTime"][reg_type][reg_key] = 0;
                        regHistory["_10m"][reg_type][reg_key] = [reg_val];
                        regHistory["_60m"][reg_type][reg_key] = [reg_val, reg_val];
                        regHistory["_24h"][reg_type][reg_key] = [reg_val, reg_val];
                      }
                  } else {
                    if (reg_val != regHistory["_10m"][reg_type][reg_key][0]) {
                        regHistory["updateTime"][reg_type][reg_key] = new Date().getTime();

                        if (printToScreen) {
                          var outstr  = ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
                              // This handles the case for byte data returning Not a Number (NaN) for coil registers that are one byte long
                              var strHi = ((parseInt(reg_val) & 0xff00) >> 8).toString()
                              var strLo = (parseInt(reg_val) & 0x00ff).toString()                    
                              outstr += ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+ strHi +':'+ strLo +'</span>');
                          $("#content_"+reg_key).html(outstr);
                        }
                    }
                  }
                  // add the value to the begining of the array
                  regHistory["_10m"][reg_type][reg_key].unshift(reg_val);
                  if  (regHistory["_10m"][reg_type][reg_key].length > 120) {
                    var removed = regHistory["_10m"][reg_type][reg_key].pop  // remove the last element
                  }

                  if (regHistory["count_60m"] >= 12) {
                    var min = 0;
                    var max = 0;
                    for (var i = 1; i <12; i++) {
                        if (regHistory["_10m"][reg_type][reg_key][i] > regHistory["_10m"][reg_type][reg_key][max])
                            max = i;
                        if (regHistory["_10m"][reg_type][reg_key][i] < regHistory["_10m"][reg_type][reg_key][min])
                            min = i;
                    }
                    regHistory["_60m"][reg_type][reg_key].unshift(regHistory["_10m"][reg_type][reg_key][((min > max) ? min : max)], regHistory["_10m"][reg_type][reg_key][((min > max) ? max : min)]);

                    if  (regHistory["_60m"][reg_type][reg_key].length > 120)
                      regHistory["_60m"][reg_type][reg_key].splice(-2, 2);  // remove the last 2 element
                  }

                  if (regHistory["count_24h"] >= 288) {
                    var min = 0;
                    var max = 0;
                    for (var i = 1; i <24; i++) {
                        if (regHistory["_60m"][reg_type][reg_key][i] > regHistory["_60m"][reg_type][reg_key][max])
                            max = i;
                        if (regHistory["_60m"][reg_type][reg_key][i] < regHistory["_60m"][reg_type][reg_key][min])
                            min = i;
                    }
                    regHistory["_24h"][reg_type][reg_key].unshift(regHistory["_60m"][reg_type][reg_key][((min > max) ? min : max)], regHistory["_60m"][reg_type][reg_key][((min > max) ? max : min)]);

                    if  (regHistory["_24h"][reg_type][reg_key].length > 120)
                      regHistory["_24h"][reg_type][reg_key].splice(-2, 2);  // remove the last 2 element
                  }
              }); // end register data loop
            });   // end register type loop
            regHistory["count_60m"] = ((regHistory["count_60m"] >= 12) ? 0 : regHistory["count_60m"]+1);
            regHistory["count_24h"] = ((regHistory["count_24h"] >= 288) ? 0 : regHistory["count_24h"]+1);

            if (printToScreen)
               UpdateRegistersColor();
          }
          catch(err){
              console.log("Error in UpdateRegisters: " + err)
          }
    }});
}
//*****************************************************************************
function UpdateRegistersColor() {
    var CurrentTime = new Date().getTime();

    var RegTypes = ['Holding', 'Inputs', 'Coils'];
    $.each(RegTypes, function(i, reg_type){
      if (!(regHistory["updateTime"].hasOwnProperty(reg_type))){
        // no data for this register
        return;
      }
      $.each(regHistory["updateTime"][reg_type], function( reg_key, update_time ){
        var difference = CurrentTime - update_time;
        var secondsDifference = Math.floor(difference/1000);
        if ((update_time > 0) && (secondsDifference >= fadeOffTime)) {
           $("#content_"+ reg_type + '_'+ reg_key).css("background-color", "#AAAAAA");
           $("#content_"+reg_type + '_'+ reg_key).css("color", "red");
        } else if ((update_time > 0) && (secondsDifference <= fadeOffTime)) {
           var hexShadeR = toHex(255-Math.floor(secondsDifference*85/fadeOffTime));
           var hexShadeG = toHex(Math.floor(secondsDifference*170/fadeOffTime));
           var hexShadeB = toHex(Math.floor(secondsDifference*170/fadeOffTime));
           $("#content_"+reg_type + '_'+ reg_key).css("background-color", "#"+hexShadeR+hexShadeG+hexShadeB);
           $("#content_"+reg_type + '_'+ reg_key).css("color", "black");
        }
      });
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

    var data_length = 0;
    var RegTypes = ['Holding', 'Inputs', 'Coils'];
    $.each(RegTypes, function(i, reg_type){
      if (!(data.hasOwnProperty(reg_type))){
        // no data for this register
        return;
      }
      $.each(Object.keys(data[reg_type]).sort(), function(i, reg_key) {
          data_length += 1;
          var max=data[reg_type][reg_key][0];
          var min=data[reg_type][reg_key][0];
          for (var j = 120; j >= 0; --j) {
            if (data[reg_type][reg_key][j] > max)
                max = data[reg_type][reg_key][j];
            if (data[reg_type][reg_key][j] < min)
                min = data[reg_type][reg_key][j];
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

          var reg_val = data[reg_type][reg_key][0];

          outstr += '<td width="33%" class="printRegisterTD">';
          outstr +=     '<table width="333px" heigth="100%" id="val_'+reg_type+'_'+reg_key+'">';
          outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">' + reg_type+':'+reg_key + '</td></tr>';
          outstr +=     '<tr><td align="center" class="printRegisterTDtitle">' + BaseRegistersDescription[reg_type][reg_key] + '</td></tr>';
          outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">Current Value: ' + regHistory["_10m"][reg_type][reg_key][0] + '</td></tr>';
          if (min != max) {
            outstr +=     '<tr><td align="center" class="printRegisterTDsubtitle">Minimum Value: '+min+'<br>Maximum Value: '+max+'</td></tr>';
            outstr +=     '<tr><td align="center" class="regHistoryPlotCell"><div id="printPlot_'+reg_type+'_'+reg_key+'"></div></td></tr>';
            plots.push(reg_key);
            rowHeight = 45;
          } else {
            outstr +=     '<tr><td align="center" class="printRegisterTDvalMedium">no change</td></tr>';
          }
          outstr +=     '</table>';
          outstr += '</td>';
      });
    });
    if ((data_length % 3) > 0) {
      for (var i = (data_length % 3); i < 3; i++) {
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
        outstr += '</table></fieldset></form>';

        outstr += '<table id="allactions" border="0">';
        outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">Restart Genmon Software</td><td><button style="margin-left:0px; margin-top:5px" id="callcmdrestart" onClick="sendServerCommand(\'restart\')">Restart</button></td></tr>';
        outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">Reboot System</td><td><button style="margin-left:0px; margin-top:5px" id="callcmdreboot" onClick="sendServerCommand(\'reboot\')">Reboot</button></td></tr>';
        outstr += '<tr><td width="25px">&nbsp;</td><td width="300px">Shutdown System</td><td><button style="margin-left:0px; margin-top:5px" id="callcmdshutdown" onClick="sendServerCommand(\'shutdown\')">Shutdown</button></td></tr>';

        outstr += '</table></fieldset></form><br>';
        outstr += '<button id="setadvancedsettingsbutton" onClick="saveAdvancedSettings()">Save</button>';

        $("#mydisplay").html(outstr);
        $('input').lc_switch();
        $.extend($.idealforms.rules, {
           // The rule is added as "ruleFunction:arg1:arg2"
           HTTPAddress: function(input, value, arg1, arg2) {
             //var regex = RegExp("^http[s]?:\\/\\/(([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             var regex = RegExp("^(?:https?:\/\/)(?!$)(?:www\.)?[a-zA-Z]*(?:\.[a-zA-Z]{2,6})?(?:(?:\d{1,3}\.){3}\d{1,3})?", 'g');
             return regex.test(value);
           },
           InternetAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(([a-z0-9]+([-\\.]{1}[a-z0-9]+)*\\.[a-z]{2,5}(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           IPAddress: function(input, value, arg1, arg2) {
             var regex = RegExp("^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/.*)?)|(localhost(\/.*)?))$", 'g');
             return regex.test(value);
           },
           InternationalPhone: function(input, value, arg1, arg2) {
             var regex = RegExp('^[0-9\-().+\s]{10,20}$', 'g');
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
// called when Save Advanced Settings is clicked
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
// GetRegisterNames - Get names of the registers
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
//
//*****************************************************************************
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
          myGenerator['AltDateformat'] = result['AltDateformat']
          if (myGenerator['version'].length > 0) {
             if (myGenerator['version'] != result['version']) {
                myGenerator['version'] = result['version'];
                var myDialog = vex.dialog.open({
                   unsafeMessage: '',
                   overlayClosesOnClick: false,
                   buttons: []
                });
                
                var DisplayStr1 = 'A change in the version was detected. Reloading web interface...';
                var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
                $('.vex-dialog-message').html(DisplayStr1);
                $('.vex-dialog-buttons').html(DisplayStr2);
                $('.progress-bar-fill').queue(function () {
                     $(this).css('width', '100%')
                });
                
                setTimeout(function(){ vex.closeAll(); window.location.href = window.location.pathname+"?page=about&reload=true"; }, 10000);
             }
          } else {
             myGenerator['version'] = result['version'];
          }


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

          if (result['Weather'] != undefined && result['Weather'].length > 5) {
            weatherCondition = "Unknown"
            weatherIcon = "unknown.png"
            weatherTemp = "unknown"
            weatherWind = "unknown"
            jQuery.each(result["Weather"], function( i, val ) {
               if (Object.keys(val)[0] == "icon") {
                  weatherIcon = val["icon"];
               }
               if (Object.keys(val)[0] == "Conditions") {
                  weatherCondition = val["Conditions"];
               }
               if (Object.keys(val)[0] == "Current Temperature") {
                  weatherTemp = val["Current Temperature"];
               }
               if (Object.keys(val)[0] == "Wind") {
                  weatherWind = val["Wind"].replace(/\(.*\)/g, "").replace(/,/g, "");
               }
            });
            if ((weatherIcon != "unknown.png") && (weatherTemp != "unknown") && (weatherWind != "unknown")) {
               var tempMsg = '<table style="padding:0px;margin:0px"><tr><td><img class="greyscale" style="padding:0px;margins:0px;height:25px" src="https://openweathermap.org/img/w/' + weatherIcon + '.png"></td><td align="left" valign="middle"><b><font size="-2"><div style="line-height:9px;">'+weatherTemp+'<br>'+weatherWind+'</div></font></b></td><td>&nbsp;&nbsp;&nbsp;</td></tr></table>';
               $('#footerWeather').html(tempMsg);
            }
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
