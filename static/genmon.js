// genmon.js - javascrip source for generator monitor
// Define header
$("#myheader").html('<header>Generator Monitor</header>');

// Define main menu
$("#navMenu").html('<ul>' +
      '<li id="status"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/status.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Status</td></tr></table></a></li>' +
      '<li id="maint"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/maintenance.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Maintenance</td></tr></table></a></li>' +
      '<li id="outage"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/outage.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Outage</td></tr></table></a></li>' +
      '<li id="logs"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/log.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Logs</td></tr></table></a></li>' +
      '<li id="monitor"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/monitor.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Monitor</td></tr></table></a></li>' +
      '<li id="notifications"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/notifications.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Notifications</td></tr></table></a></li>' +
      '<li id="settings"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src="images/settings.png" width="20px" height="20px"></td><td valign="middle">&nbsp;Settings</td></tr></table></a></li>' +
    '</ul>') ;

// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var currentClass = "active";    // CSS class for menu color
var menuElement = "status";
var ExerciseParameters = {};
    ExerciseParameters['EnhancedExerciseEnabled']  = false;
// on page load call init
var pathname = "";
var baseurl = "";
var DaysOfWeekArray = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];

//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
$(document).ready(function() {
    pathname = window.location.href;
    baseurl = pathname.concat("cmd/")
    SetHeaderValues();
    $("#footer").html('<table border="0" width="100%" height="30px"><tr><td width="90%"><a href="https://github.com/jgyates/genmon" target="_blank">GenMon Project on GitHub</a></td></tr></table>');
    SetFavIcon();
    GetExerciseValues();
    $("#status").find("a").addClass(GetCurrentClass());
    setInterval(GetBaseStatus, 3000);       // Called every 3 sec
    setInterval(UpdateDisplay, 5000);       // Called every 5 sec
    DisplayStatusFull();
    $("li").on('click',  function() {  MenuClick($(this));});
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
var gaugeBatteryVoltage;
var gaugeUtilityVoltage;
var gaugeOutputVoltage;
var gaugeBatteryFrequency;

function DisplayStatusFull()
{
    var url = baseurl.concat("status_json");
    $.getJSON(url,function(result){
        var outstr = 'Dashboard:<br><br>';
        outstr += '<center><table width="80%" border="0"><tr>';
        outstr += '<td width="25%" class="gaugeTD" align="center">';
        outstr += 'Battery Voltage<br><canvas class="gaugeCanvas" id="gaugeBatteryVoltage"></canvas><br><div id="textBatteryVoltage" class="gaugeDiv"></div>V';
        outstr += '</td>';
        outstr += '<td width="25%" class="gaugeTD" align="center">';
        outstr += 'Utility Voltage<br><canvas class="gaugeCanvas" id="gaugeUtilityVoltage"></canvas><br><div id="textUtilityVoltage" class="gaugeDiv"></div>V';
        outstr += '</td>';
        outstr += '<td width="25%" class="gaugeTD" align="center">';
        outstr += 'Output Voltage<br><canvas class="gaugeCanvas" id="gaugeOutputVoltage"></canvas><br><div id="textOutputVoltage" class="gaugeDiv"></div>V';
        outstr += '</td>';
        outstr += '<td width="25%" class="gaugeTD" align="center">';
        outstr += 'Frequency<br><canvas class="gaugeCanvas" id="gaugeFrequency"></canvas><br><div id="textFrequency" class="gaugeDiv"></div>Hz';
        outstr += '</td>';
        outstr += '</tr></table></center><br>';

        $("#mydisplay").html(outstr + json2html(result, "", "root"));

        gaugeBatteryVoltage = createGauge($("#gaugeBatteryVoltage"), $("#textBatteryVoltage"), 1, 10, 16, [10, 11, 12, 13, 14, 15, 16],
                                          [{strokeStyle: "#F03E3E", min: 10, max: 11},
                                           {strokeStyle: "#FFDD00", min: 11, max: 12},
                                           {strokeStyle: "#30B32D", min: 12, max: 15},
                                           {strokeStyle: "#FFDD00", min: 15, max: 15.5},
                                           {strokeStyle: "#F03E3E", min: 15.5, max: 16}], 6, 10);
        gaugeBatteryVoltage.set(result["Status"]["Engine"]["Battery Voltage"].replace(/V/g, '')); // set current value

        gaugeUtilityVoltage = createGauge($("#gaugeUtilityVoltage"), $("#textUtilityVoltage"), 0, 0, 260, [0, 100, 156, 220, 240, 260],
                                          [{strokeStyle: "#F03E3E", min: 0, max: 220},
                                           {strokeStyle: "#FFDD00", min: 220, max: 235},
                                           {strokeStyle: "#30B32D", min: 235, max: 245},
                                           {strokeStyle: "#FFDD00", min: 245, max: 255},
                                           {strokeStyle: "#F03E3E", min: 255, max: 260}], 26, 0);
        gaugeUtilityVoltage.set(result["Status"]["Line State"]["Utility Voltage"].replace(/V/g, '')); // set actual value

        gaugeOutputVoltage = createGauge($("#gaugeOutputVoltage"), $("#textOutputVoltage"), 0, 0, 260, [0, 100, 156, 220, 240, 260],
                                          [{strokeStyle: "#F03E3E", min: 0, max: 220},
                                           {strokeStyle: "#FFDD00", min: 220, max: 235},
                                           {strokeStyle: "#30B32D", min: 235, max: 245},
                                           {strokeStyle: "#FFDD00", min: 245, max: 255},
                                           {strokeStyle: "#F03E3E", min: 255, max: 260}], 26, 0);
        gaugeOutputVoltage.set(result["Status"]["Engine"]["Output Voltage"].replace(/V/g, '')); // set actual value

        gaugeFrequency = createGauge($("#gaugeFrequency"), $("#textFrequency"), 1, 0, 70, [10, 20, 30, 40, 50, 60, 70],
                                          [{strokeStyle: "#F03E3E", min: 0, max: 57},
                                           {strokeStyle: "#FFDD00", min: 57, max: 59},
                                           {strokeStyle: "#30B32D", min: 59, max: 61},
                                           {strokeStyle: "#FFDD00", min: 61, max: 63},
                                           {strokeStyle: "#F03E3E", min: 63, max: 70}], 7, 10);
        gaugeFrequency.set(result["Status"]["Engine"]["Frequency"].replace(/Hz/g, '')); // set actual value
    });
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
      colorStart: '#6FADCF',   // Colors
      colorStop: '#8FC0DA',    // just experiment with them
      strokeColor: '#E0E0E0',  // to see which ones work best for you
      generateGradient: true,
      highDpiSupport: true,     // High resolution support
      staticLabels: {
        font: "10px sans-serif",  // Specifies font
        labels: pLabels,  // Print labels at these values
        color: "#000000",  // Optional: Label text color
        fractionDigits: 0  // Optional: Numerical precision. 0=round off.
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
    gauge.setTextField(pText[0], pTextPrecision);
    gauge.animationSpeed = 1;
    gauge.set(pMin); // setting starting point
    gauge.animationSpeed = 128; // set animation speed (32 is default value)

    return gauge;
}

//*****************************************************************************
// DisplayStatusUpdate - updates the status page at every interval
//*****************************************************************************
function DisplayStatusUpdate()
{
    var url = baseurl.concat("status_json");
    $.getJSON(url,function(result){
        json2updates(result, "root");

        gaugeBatteryVoltage.set(result["Status"]["Engine"]["Battery Voltage"].replace(/V/g, '')); // set actual value
        gaugeUtilityVoltage.set(result["Status"]["Line State"]["Utility Voltage"].replace(/V/g, '')); // set actual value
        gaugeOutputVoltage.set(result["Status"]["Engine"]["Output Voltage"].replace(/V/g, '')); // set actual value
        gaugeFrequency.set(result["Status"]["Engine"]["Frequency"].replace(/Hz/g, '')); // set actual value
    });
    return;
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

    var url = baseurl.concat("maint");
    $.getJSON(url,function(result){

        // replace /n with html friendly <br/>
        var outstr = replaceAll(result,'\n','<br/>')
        // replace space with html friendly &nbsp
        outstr = replaceAll(outstr,' ','&nbsp')

        outstr += "<br>Generator Exercise Time:<br><br>";

        //Create array of options to be added
        var FreqArray = ["Weekly", "Biweekly", "Monthly"];
        if (ExerciseParameters['EnhancedExerciseEnabled'] == true) {
            outstr += "&nbsp;&nbsp;&nbsp;&nbsp;Mode: ";
            for(var i = 0; i < FreqArray.length; i++)  {
                outstr += '<label for="' + FreqArray[i] + '">' + FreqArray[i] + '</label>';
                outstr += '<input type="radio" name="choice" value="' + FreqArray[i] + '" id="' + FreqArray[i] + '" ';
                outstr += ((ExerciseParameters['ExerciseFrequency'] == FreqArray[i]) ? ' checked ' : '');
                outstr += ((FreqArray[i] == "Monthly") ? ' onClick="MonthlyExerciseSelection();" ' : ' onClick="WeekdayExerciseSelection();" ');
                outstr += '>';
            }
        }

        //Create and append the options, days
        outstr += '<br><br>&nbsp;&nbsp;&nbsp;&nbsp;<select style="width:200px;" id="days"></select> , ';
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
        outstr += '</select>&nbsp;&nbsp;';

        //Create and append select list
        outstr += '&nbsp;&nbsp;&nbsp;&nbsp;<select id="quietmode">';
        outstr += '<option value="QuietMode=On" ' + (ExerciseParameters['QuietMode'] == "On"  ? ' selected="selected" ' : '') + '>Quiet Mode On </option>';
        outstr += '<option value="QuietMode=Off"' + (ExerciseParameters['QuietMode'] == "Off" ? ' selected="selected" ' : '') + '>Quiet Mode Off</option>';
        outstr += '</select><br><br>';

        outstr += '&nbsp;&nbsp;<button id="setexercisebutton" onClick="saveMaintenance();">Set Exercise Time</button>';

        outstr += '<br><br>Generator Time:<br><br>';
        outstr += '&nbsp;&nbsp;<button id="settimebutton" onClick="SetTimeClick();">Set Generator Time</button>';

        outstr += '<br><br>Remote Commands:<br><br>';
        outstr += '&nbsp;&nbsp;<button id="remotestop" onClick="SetStopClick();">Stop Generator</button><br><br>';
        outstr += '&nbsp;&nbsp;<button id="remotestart" onClick="SetStartClick();">Start Generator</button><br><br>';
        outstr += '&nbsp;&nbsp;<button id="remotetransfer" onClick="SetTransferClick();">Start Generator and Transfer</button><br><br>';

        $("#mydisplay").html(outstr);

        if ((ExerciseParameters['EnhancedExerciseEnabled'] == true) && ($("#Monthly").is(":checked") == true)) {
           MonthlyExerciseSelection();
        } else {
           WeekdayExerciseSelection();
        }
        $("#days").val(ExerciseParameters['ExerciseDay']);
        $("#hours").val(ExerciseParameters['ExerciseHour']);
        $("#minutes").val(ExerciseParameters['ExerciseMinute']);

        if((baseState === "EXERCISING") || (baseState === "RUNNING")) {
            $("#remotestop").prop("disabled",false);
            $("#remotestart").prop("disabled",true);
            $("#remotetransfer").prop("disabled",true);
        }
        else {
            $("#remotestop").prop("disabled",true);
            $("#remotestart").prop("disabled",false);
            $("#remotetransfer").prop("disabled",false);
        }

   });
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
    $("#days").val(ExerciseParameters['ExerciseDay']);
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
    $("#days").val(ExerciseParameters['ExerciseDay']);
}

//*****************************************************************************
// called when Set Remote Stop is clicked
//*****************************************************************************
function SetStopClick(){

    vex.dialog.confirm({
        unsafeMessage: 'Stop generator?<br><span class="confirmSmall">Note: If the generator is powering a load there will be a cool down period of a few minutes.</span>',
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
// called when Set Exercise is clicked
//*****************************************************************************
function saveMaintenance(){

    try {
        var strDays         = $("#days").val();
        var strHours        = $("#hours").val();
        var strMinutes      = $("#minutes").val();
        var strQuiet        = $("#quietmode").val();
        var strChoice       = ((ExerciseParameters['EnhancedExerciseEnabled'] == true) ? $('input[name=choice]:checked').val() : "Weekly");
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
// Display the Notification Tab
//*****************************************************************************
function DisplayNotifications(){

    var url = baseurl.concat("notifications");
    $.getJSON(url,function(result){

        var  outstr = 'Notification Recepients:<br><br>';
        outstr += '<button value="+Add" id="addRow">+Add</button><br><br>';
        outstr += '<form id="formNotifications">';
        outstr += '<table id="allnotifications" border="0"><tbody>';

        outstr += '<tr id="row_0"><td>&nbsp;&nbsp;&nbsp;&nbsp;</td><td>&nbsp;&nbsp;&nbsp;&nbsp;</td><td width="15%" align="center">All:</td><td width="15%" align="center">Outages:</td><td width="15%" align="center">Errors:</td><td width="15%" align="center">Warning:</td><td width="15%" align="center">Information:</td><td></td></tr>';

        var rowcount;
        var emails =  getSortedKeys(result, 0);
        for (var index = 0; index < emails.length; ++index) {
            rowcount = index+1;
            var email = emails[index];
            var permissions = {}
            if ((typeof result[email][1] !== 'undefined' ) && (result[email][1] != "")) {
               $.each(result[email][1].split(','), function(index, value) {
                   permissions[value] = "true"
               });
            } else {
               $.each( ["all", "outage", "error", "warn", "info"], function( index, type ){
                  permissions[type] = "true"
               });
            }

            outstr += '<tr id="row_' + rowcount + '"><td>&nbsp;&nbsp;&nbsp;&nbsp;</td>';
            outstr += '<td>'+email+'<input type="hidden" name="email_' + rowcount + '" id="email_' + rowcount + '" value="'+email+'"></td>';

            $.each( ["all", "outage", "error", "warn", "info"], function( index, type ){
               outstr += '<td width="15%" align="center">';
               outstr += '<span id="bg_'+rowcount+'"><input id="' + type + '_' + rowcount + '" name="' + type + '_' + rowcount + '" type="checkbox" value="true" ' +
                          (((typeof permissions[type] !== 'undefined' ) && (permissions[type].toLowerCase() == "true")) ? ' checked ' : '') +
                          (((typeof permissions[type] !== 'undefined' ) && (permissions[type].toLowerCase() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') +
                         '></span>';
               outstr += '</td>';
            });
            outstr += '<td width="15%" align="center"><button type="button" rowcount="' + rowcount + '" id="removeRow">Remove</button></td></tr>';
        }
        outstr += '</tbody></table></form><br>';
        outstr += '<button id="setnotificationsbutton" onClick="saveNotifications()">Save</button>';
        $("#mydisplay").html(outstr);
        rowcount++;
        $('#rowcount').val(rowcount);

        $(document).ready(function() {
           $("#addRow").click(function () {
              $("#allnotifications").each(function () {
                  var outstr = '<tr id="row_' + rowcount + '"><td>&nbsp;&nbsp;&nbsp;&nbsp;</td>';
                  outstr += '<td><input id="email_' + rowcount + '" style="width: 300px;" name="email_' + rowcount + '" type="text"></td>';

                  $.each( ["all", "outage", "error", "warn", "info"], function( index, type ){
                     outstr += '<td width="15%" align="center">';
                     outstr += '<span id="bg_'+rowcount+'"><input id="' + type + '_' + rowcount + '" name="' + type + '_' + rowcount + '" type="checkbox" value="true" ></span>';
                     outstr += '</td>';
                  });
                  outstr += '<td width="15%" align="center"><button type="button" rowcount="' + rowcount + '" id="removeRow">Remove</button></td></tr>';
                  rowcount++;
                  if ($('tbody', this).length > 0) {
                      $('tbody', this).append(outstr);
                  } else {
                      $(this).append(outstr);
                  }
              });
           });

           $("#allnotifications tbody").on('click', 'button', function(){
              $('table#allnotifications tr#row_'+$(this).attr("rowcount")).remove();
           });

           $("#allnotifications tbody").on('change', 'input:checkbox', function(){
              var ids = $(this).attr("id").split('_');
              var myval = ($(this).prop('checked') === true ? "true" : "false");
              if ((ids[0] == "all") && (myval == "true")) {
                 $.each( ["outage", "error", "warn", "info"], function( index, type ){
                     $('#'+type+'_'+ids[1]).prop('checked', true);
                 });
              } else if ((ids[0] != "all") && (myval == "false")) {
                 $('#all_'+ids[1]).prop('checked', false);
              } else if ((ids[0] != "all") && (myval == "true")) {
                 if  ($('#outage_'+ids[1]).is(":checked") &&
                      $('#error_'+ids[1]).is(":checked") &&
                      $('#warn_'+ids[1]).is(":checked") &&
                      $('#info_'+ids[1]).is(":checked")) {
                   $('#all_'+ids[1]).prop('checked', true);
                 }

              }
           });

        });
   });
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
    $.each($('#formNotifications input[type=text]'), function( index, type ){
        if ($(this).val().trim() == "") {
           blankEmails++
        }
    });
    if (blankEmails > 0) {
       GenmonAlert("Emails cannot be blank.<br>You have "+blankEmails+" blank lines.");
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
             setTimeout(function(){ vex.closeAll(); }, 10000);
           }
        }
    })
}

function saveNotificationsJSON(){
    try {
        var fields = {};

        $('#formNotifications input[type=text],#formNotifications input[type=hidden]').each(function() {
            var thisRow = ($(this).attr('id').split("_"))[1];
            if ($('#outage_'+thisRow).is(":checked") &&
                $('#error_'+thisRow).is(":checked") &&
                $('#warn_'+thisRow).is(":checked") &&
                $('#info_'+thisRow).is(":checked")) {
               fields[$(this).val()] = "";
            } else if (!($('#outage_'+thisRow).is(":checked")) &&
                       !($('#error_'+thisRow).is(":checked"))&&
                       !($('#warn_'+thisRow).is(":checked")) &&
                       !($('#info_'+thisRow).is(":checked"))) {
              // email will be deleted
            } else {
                var val = []
                $.each( ["outage", "error", "warn", "info"], function( index, type ) {
                   if ($('#'+type+'_'+thisRow).is(":checked")) {
                     val.push(type)
                   }
                });
                fields[$(this).val().trim()] = val.join(",");
            }
        });

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
    $.getJSON(url,function(result){

        var outstr = '<form id="formSettings"><table id="allsettings" border="0">';
        var settings =  getSortedKeys(result, 2);
        for (var index = 0; index < settings.length; ++index) {
            var key = settings[index];
            if (result[key][2] == 1) {
              outstr += '<tr><td colspan="2">General Settings:</td></tr>';
            } else if (result[key][2] == 50) {
              outstr += '<tr><td colspan="2"><br><br>Console Settings:</td></tr>';
            } else if (result[key][2] == 40) {
              outstr += '<tr><td colspan="2"><br><br>Generator Model Specific Settings:</td></tr>';
            } else if (result[key][2] == 26) {
              outstr += '<tr><td colspan="2"><br><br>Webserver Security Settings:</td></tr>';
            } else if (result[key][2] == 101) {
              outstr += '<tr><td colspan="2"><br><br>Email Settings:</td></tr>';
            } else if (result[key][2] == 150) {
              outstr += '<tr><td colspan="2"><br><br>Email Commands Processing:</td></tr>';
            }
            outstr += '<tr><td>&nbsp;&nbsp;&nbsp;&nbsp;</td><td> '+result[key][1];
            if ((typeof result[key][5] !== 'undefined' ) && (result[key][5] == 1)) {
              outstr += '<div id="' + key + '_disabled"><font size="-3">(disabled)</font></div>';
            }
            outstr += '</td><td>';
            switch (result[key][0]) {
              case "string":
                outstr += '<input id="' + key + '" style="width: 400px;" name="' + key + '" type="text" ' +
                           (typeof result[key][3] === 'undefined' ? '' : 'value="' + replaceAll(result[key][3], '"', '&quot;') + '" ') +
                           (typeof result[key][3] === 'undefined' ? '' : 'oldValue="' + replaceAll(result[key][3], '"', '&quot;') + '" ') +
                           (((typeof result[key][4] === 'undefined' ) || (result[key][4].trim() == "")) ? '' : 'title="' + replaceAll(result[key][4], '"', '&quot;') + '" ') +
                          ' class="tooltip">';
                break;
              case "int":
                outstr += '<input id="' + key + '" name="' + key + '" type="text" ' +
                           (typeof result[key][3] === 'undefined' ? '' : 'value="' + result[key][3].toString() + '" ') +
                           (typeof result[key][3] === 'undefined' ? '' : 'oldValue="' + result[key][3].toString() + '" ') +
                           (((typeof result[key][4] === 'undefined' ) || (result[key][4].trim() == "")) ? '' : 'title="' + replaceAll(result[key][4], '"', '&quot;') + '" ') +
                          ' class="tooltip">';
                break;
              case "boolean":
                outstr += '<span id="' + key + '_bg"><input id="' + key + '" name="' + key + '" type="checkbox" ' +
                           (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toString() == "true")) ? ' checked ' : '') +
                           (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toString() == "true")) ? ' oldValue="true" ' : ' oldValue="false" ') +
                           (((typeof result[key][4] === 'undefined' ) || (result[key][4].trim() == "")) ? '' : 'title="' + replaceAll(result[key][4], '"', '&quot;') + '" ') +
                          ' class="tooltip"></span>';
                break;
              default:
                break;
            }
            outstr += '</td>';
        }
        outstr += '</table></form>';
        outstr += '<button id="setsettingsbutton" onClick="saveSettings()">Save</button>';
        $("#mydisplay").html(outstr);
        $('.tooltip').tooltipster({
           animation: 'fade',
           delay: 100,
           trigger: 'click',
           side: ['bottom', 'left']
        });
	$("#disableemail").trigger("change");
        $("#displayoutput").trigger("change");
        $("#usehttps").trigger("change");
        $("#imap_server").trigger("change");

        $(document).ready(function() {
            $('input').change(function(){
               var name = $(this).attr("id");
               var oldValue = $(this).attr('oldValue');
               var currentValue = (($(this).attr('type') == "checkbox") ? ($(this).prop('checked') === true ? "true" : "false") : $(this).val());
               if (oldValue != currentValue) {
                 if ($("#"+name+"_disabled").is(":visible")) {
                    $("#"+name+"_disabled").hide(500);
                    $(this).attr("oldValue", "")
                 }
                 if ($(this).attr('type') == "checkbox") {
                   // $("#"+name+"_bg").css("background-color","#FFB");
                   $(this).parent().find(".lcs_switch").addClass("lcs_changed");
                 } else {
                   $(this).css("background-color","#FFB");
                 }
               } else {
                 $(this).css("background-color","#FFF");
                 // $("#"+name+"_bg").css("background-color","#FFF");
                 $(this).parent().find(".lcs_switch").removeClass("lcs_changed");
               }
            });
            $("#disableemail").change(function () {
                 if($(this).is(":checked")) {
                     $("#smtp_port").attr("disabled", "disabled");
                     $("#imap_server").attr("disabled", "disabled");
                     $("#smtp_server").attr("disabled", "disabled");
                     $("#ssl_enabled").attr("disabled", "disabled");
                     $("#email_recipient").attr("disabled", "disabled");
                     $("#sender_account").attr("disabled", "disabled");
                     $("#email_pw").attr("disabled", "disabled");
                     $("#email_account").attr("disabled", "disabled");
                     $("#incoming_mail_folder").attr("disabled", "disabled");
                     $("#processed_mail_folder").attr("disabled", "disabled");
                 } else {
                     $("#smtp_port").removeAttr("disabled");
                     $("#imap_server").removeAttr("disabled");
                     $("#smtp_server").removeAttr("disabled");
                     $("#ssl_enabled").removeAttr("disabled");
                     $("#email_recipient").removeAttr("disabled");
                     $("#sender_account").removeAttr("disabled");
                     $("#email_pw").removeAttr("disabled");
                     $("#email_account").removeAttr("disabled");
                     if ($("#imap_server").val() != "") {
                       $("#incoming_mail_folder").removeAttr("disabled");
                       $("#processed_mail_folder").removeAttr("disabled");
                     }
                 }
            });
            $("#displayoutput").change(function () {
                 if($(this).is(":checked")) {
                     $("#displaymonitor").removeAttr("disabled");
                     $("#displayregisters").removeAttr("disabled");
                     $("#displaystatus").removeAttr("disabled");
                     $("#displaymaintenance").removeAttr("disabled");
                    // $("#displayunknown").removeAttr("disabled");
                 } else {
                     $("#displaymonitor").attr("disabled", "disabled");
                     $("#displayregisters").attr("disabled", "disabled");
                     $("#displaystatus").attr("disabled", "disabled");
                     $("#displaymaintenance").attr("disabled", "disabled");
                    // $("#displayunknown").attr("disabled", "disabled");
                 }
            });
            $("#usehttps").change(function () {
                 if(($(this).is(":checked")) & (!$("#usehttps_disabled").is(":visible"))) {
                     $("#useselfsignedcert").removeAttr("disabled");
                     if (!$("#useselfsignedcert").is(":checked")) {
                       $("#keyfile").removeAttr("disabled");
                       $("#certfile").removeAttr("disabled");
                     }
                     $("#http_user").removeAttr("disabled");
                     $("#http_pass").removeAttr("disabled");
                 } else {
                     $("#useselfsignedcert").attr("disabled", "disabled");
                     $("#keyfile").attr("disabled", "disabled");
                     $("#certfile").attr("disabled", "disabled");
                     $("#http_user").attr("disabled", "disabled");
                     $("#http_pass").attr("disabled", "disabled");
                 }
            });
            $("#useselfsignedcert").change(function () {
                 if ($(this).is(":checked")) {
                     $("#keyfile").attr("disabled", "disabled");
                     $("#certfile").attr("disabled", "disabled");
                 } else {
                     $("#keyfile").removeAttr("disabled");
                     $("#certfile").removeAttr("disabled");
                 }
            });
            $("#imap_server").change(function () {
                 if($(this).val() != "") {
                     $("#incoming_mail_folder").removeAttr("disabled");
                     $("#processed_mail_folder").removeAttr("disabled");
                 } else {
                     $("#incoming_mail_folder").attr("disabled", "disabled");
                     $("#processed_mail_folder").attr("disabled", "disabled");
                 }
            });
            $("#disableemail").trigger("change");
            $("#displayoutput").trigger("change");
            $("#usehttps").trigger("change");
            $("#imap_server").trigger("change");
            $("#useselfsignedcert").trigger("change");
        });

   });

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
                if ($('#sitename').val() != $('#sitename').attr('oldValue')) { SetHeaderValues(); }
                if ($('#favicon').val() != $('#favicon').attr('oldValue')) { changeFavicon($('#favicon').val()); }
                if (($('#enhancedexercise').prop('checked')  === true ? "true" : "false") != $('#enhancedexercise').attr('oldValue')) { ExerciseParameters['EnhancedExerciseEnabled'] = ($('#enhancedexercise').prop('checked')  === true ? "true" : "false") }
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
var GlobalOldRegKeys;
var InitOK = false;
var UpdateTime = {};
var fadeOffTime = 60;

var BaseRegistersDescription = { "0000" : "Product line",
                                 "0005" : "Exercise Time HH:MM (Read Only)",
                                 "0006" : "Exercise Time Hi Byte = Day of Week 00=Sunday 01=Monday, Low Byte = 00=quiet=no, 01=yes",
                                 "0007" : "Engine RPM",
                                 "0008" : "Engine Frequency Hz",
                                 "000a" : "Battery Voltage",
                                 "000c" : "Engine Run Hours (Nexus, EvoAC)",
                                 "000e" : "Generator Time HH:MM",
                                 "000f" : "Generator Time Hi = month, Lo = day of the month",
                                 "0010" : "Generator Time Hi Day of Week, Lo = year",
                                 "0011" : "Utility Threshold",
                                 "0012" : "Output voltage",
                                 "001a" : "Hours until next service",
                                 "002a" : "Hardware  Version (high byte), Firmware version (low byte)",
                                 "0059" : "Set Voltage from Dealer Menu (not currently used) (EvoLC)",
                                 "023b" : "Pick Up Voltage (EvoLC)",
                                 "023e" : "Exercise time duration (EvoLC)",
                                 "0054" : "Hours since generator activation (hours of protection) (EvoLC)",
                                 "005f" : "Engine Run Minutes (EvoLC)",
                                 "01f1" : "Unknown Status ",
                                 "01f2" : "Unknown Status",
                                 "01f3" : "Unknown Status (EvoAC)",
                                 "001b" : "Unknown",
                                 "001c" : "Unknown",
                                 "001d" : "Unknown",
                                 "001e" : "Unknown",
                                 "001f" : "Unknown",
                                 "0020" : "Unknown",
                                 "0021" : "Unknown",
                                 "0019" : "Unknown",
                                 "0057" : "Unknown Status",
                                 "0055" : "Unknown",
                                 "0056" : "Unknown Status",
                                 "005a" : "Unknown",
                                 "000d" : "Bit changes when the controller is updating registers.",
                                 "003c" : "Raw RPM Sensor",
                                 "0058" : "Unknown Sensor (EvoLC)",
                                 "005d" : "Unknown Sensor (EvoLC)",
                                 "05ed" : "Ambient Temp Sensor (EvoLC)",
                                 "05ee" : "Unknown Sensor (EvoLC)",
                                 "05f5" : "Unknown Status (EvoAC, Nexus)",
                                 "05fa" : "Unknown Status (EvoAC, Nexus)",
                                 "0034" : "Unknown Sensor (Nexus, EvoAC)",
                                 "0032" : "Unknown Sensor (Nexus, EvoAC)",
                                 "0033" : "Unknown Sensor (EvoAC)",
                                 "0037" : "Unknown Sensor (Nexus, EvoAC)",
                                 "0038" : "Unknown Sensor (Nexus, EvoAC)",
                                 "003b" : "Unknown Sensor (Nexus, EvoAC)",
                                 "002b" : "UnknownSensor (Temp?) (EvoAC)",
                                 "0208" : "Unknown (EvoAC)",
                                 "002e" : "Exercise Day",
                                 "002c" : "Exercise Time HH:MM",
                                 "002d" : "Weekly, Biweekly, Monthly Exercise (EvoAC)",
                                 "002f" : "Quite Mode (EvoAC)",
                                 "005c" : "Unknown",
                                 "0001" : "Switch, Engine and Alarm Status",
                                 "05f4" : "Output relay status register (EvoAC)",
                                 "0053" : "Output relay status register (EvoLC)",
                                 "0052" : "Input status register (sensors) (Evo LC)",
                                 "0009" : "Utility Voltage",
                                 "05f1" : "Last Alarm Code (Evo)",
                                 "01f4" : "Serial Number"};

function DisplayRegistersFull()
{
    var url = baseurl.concat("registers_json");
    $.getJSON(url,function(RegData){

        var outstr = 'Live Register View:<br><br>';
        outstr += '<center><table width="80%" border="0"><tr>';
        var reg_keys = {};
        $.each(RegData.Registers["Base Registers"], function(i, item) {
            reg_keys[Object.keys(item)[0]] = item[Object.keys(item)[0]]
        });
        $.each(Object.keys(reg_keys).sort(), function(i, reg_key) {
            if ((i % 4) == 0){
                outstr += '</tr><tr>';
            }

            var reg_val = reg_keys[reg_key];
            if (InitOK == true) {
                var old_reg_val = GlobalOldRegKeys[reg_key];
                if (reg_val != old_reg_val) {
                    UpdateTime[reg_key] = new Date().getTime();
                }
            } else {
                UpdateTime[reg_key] = 0;
            }
            outstr += '<td width="25%" class="registerTD">';
            outstr +=     '<table width="100%" heigth="100%" id="val_'+reg_key+'">';
            outstr +=         '<tr><td align="center" class="registerTDtitle">' + BaseRegistersDescription[reg_key] + '</td></tr>';
            outstr +=         '<tr><td align="center" class="registerTDsubtitle">(' + reg_key + ')</td></tr>';
            outstr +=         '<tr><td align="center" id="content_'+reg_key+'">';
            outstr +=            ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
            outstr +=            ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+parseInt(reg_val.substring(0,2), 16)+':'+parseInt(reg_val.substring(2,4), 16)+'</span>');
            outstr +=         '</td></tr>';
            outstr +=     '</table>';
            outstr += '</td>';
        });
        if ((RegData.Registers["Base Registers"].length % 4) > 0) {
          for (var i = (RegData.Registers["Base Registers"].length % 4); i < 4; i++) {
             outstr += '<td width="25%" class="registerTD"></td>';
          }
        }
        outstr += '</tr></table></center>';

        $("#mydisplay").html(outstr);
        GlobalOldRegKeys = reg_keys;
        InitOK = true;
    });
}

function DisplayRegistersUpdate()
{
    var url = baseurl.concat("registers_json");
    $.getJSON(url,function(RegData){

        var reg_keys = {};
        $.each(RegData.Registers["Base Registers"], function(i, item) {
            reg_keys[Object.keys(item)[0]] = item[Object.keys(item)[0]]
        });
        $.each(Object.keys(reg_keys).sort(), function(i, reg_key) {
            var reg_val = reg_keys[reg_key];
            var old_reg_val = GlobalOldRegKeys[reg_key];
            if (reg_val != old_reg_val) {
                UpdateTime[reg_key] = new Date().getTime();
                var outstr  = ((reg_key == "01f4") ? '<span class="registerTDvalMedium">HEX:<br>' + reg_val + '</span>' : 'HEX: '+reg_val) + '<br>';
                    outstr += ((reg_key == "01f4") ? '' : '<span class="registerTDvalSmall">DEC: ' + parseInt(reg_val, 16) + ' | HI:LO: '+parseInt(reg_val.substring(0,2), 16)+':'+parseInt(reg_val.substring(2,4), 16)+'</span>');
                $("#content_"+reg_key).html(outstr)
            }
        });
        var CurrentTime = new Date().getTime();
        $.each(UpdateTime, function( reg_key, update_time ){
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
        GlobalOldRegKeys = reg_keys;
    });
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
            case "logs":
            case "monitor":
                GetDisplayValues(menuElement);
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
    $.getJSON(url,function(result){

        // replace /n with html friendly <br/>
        var outstr = replaceAll(result,'\n','<br/>')
        // replace space with html friendly &nbsp
        outstr = replaceAll(outstr,' ','&nbsp')
        $("#mydisplay").html(outstr);

   });

    return;
}

//*****************************************************************************
// Get the Excercise current settings
//*****************************************************************************
function GetExerciseValues(){

    var url = baseurl.concat("getexercise");
    $.getJSON(url,function(result){

        // should return str in this format:
        // Saturday!13!30!On!Weekly!True
        // Saturday!13!30!On!Biweekly!Falze
        // 2!13!30!On!Monthly!False
        // NOTE: Last param (True or False) is if enhanced exercise freq is enabled
        resultsArray = result.split("!");

        if (resultsArray.length == 6){
            ExerciseParameters['ExerciseDay'] = resultsArray[0];
            ExerciseParameters['ExerciseHour'] = resultsArray[1];
            ExerciseParameters['ExerciseMinute'] = resultsArray[2];
            ExerciseParameters['QuietMode'] = resultsArray[3];
            ExerciseParameters['ExerciseFrequency'] = resultsArray[4];
            ExerciseParameters['EnhancedExerciseEnabled'] = ((resultsArray[5] === "False") ? false : true);
        }
   });
}


//*****************************************************************************
// SetHeaderValues - updates header to display site name
//*****************************************************************************
function SetHeaderValues()
{
    url = baseurl.concat("getsitename");
    $.getJSON(url,function(result){
        // replace /n with html friendly <br/>
        var outstr = replaceAll(result,'\n','<br/>')
        // replace space with html friendly &nbsp
        outstr = replaceAll(outstr,' ','&nbsp')
        var HeaderStr = '<table border="0" width="100%" height="30px"><tr><td width="30px"></td><td width="90%">Generator Monitor at ' + outstr + '</td><td width="30px"><img id="registers" src="images/registers.png" width="20px" height="20px"></td></tr></table>';
        $("#myheader").html(HeaderStr);
        $("#registers").on('click',  function() {  MenuClick($(this));});
    });
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
    $.getJSON(url,function(result){
        changeFavicon(result);
    });
    return
}

//*****************************************************************************
// Show nice Alert Box (modal)
//*****************************************************************************
function GenmonAlert(msg)
{
       vex.closeAll();
       vex.dialog.alert({ unsafeMessage: '<table><tr><td valign="middle" width="200px" align="center"><img src="images/alert.png" width="64px" height="64px"></td><td valign="middle" width="70%">'+msg+'</td></tr></table>'});
}

//*****************************************************************************
// UpdateDisplay
//*****************************************************************************
function UpdateDisplay()
{
    if (menuElement == "registers") {
        DisplayRegistersUpdate();
    } else if (menuElement == "status") {
        DisplayStatusUpdate();
    } else if ((menuElement != "settings") && (menuElement != "notifications") && (menuElement != "maint")) {
        GetDisplayValues(menuElement);
    }
}

//*****************************************************************************
// GetBaseStatus - updates menu background color based on the state of the generator
//*****************************************************************************
function GetBaseStatus()
{
    url = baseurl.concat("getbase");

    $.getJSON(url,function(result){

        baseState = result;
        // active, activealarm, activeexercise
        if (baseState != currentbaseState) {

            // it changed so remove the old class
            RemoveClass()

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

            if (menuElement == "maint") {
                 if((baseState === "EXERCISING") || (baseState === "RUNNING")) {
                     $("#remotestop").prop("disabled",false);
                     $("#remotestart").prop("disabled",true);
                     $("#remotetransfer").prop("disabled",true);
                 } else {
                     $("#remotestop").prop("disabled",true);
                     $("#remotestart").prop("disabled",false);
                     $("#remotetransfer").prop("disabled",false);
                 }
            }
        }
        return
   });

    return
}