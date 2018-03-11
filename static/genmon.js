// genmon.js - javascrip source for generator monitor
// Define header
$("#myheader").html('<header>Generator Monitor</header>');

// Define main menu
$("#navMenu").html('<ul>' +
      '<li id="status"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/status.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Status</td></tr></table></a></li>' +
      '<li id="maint"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/maintenance.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Maintenance</td></tr></table></a></li>' +
      '<li id="outage"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/outage.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Outage</td></tr></table></a></li>' +
      '<li id="logs"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/log.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Logs</td></tr></table></a></li>' +
      '<li id="monitor"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/monitor.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Monitor</td></tr></table></a></li>' +
      '<li id="notifications"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/notifications.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Notifications</td></tr></table></a></li>' +
      '<li id="settings"><a><table width="100%" height="100%"><tr><td width="28px" align="right" valign="middle"><img src=\"images/settings.png\" width=\"20px\" height=\"20px\"></td><td valign="middle">&nbsp;Settings</td></tr></table></a></li>' +
    '</ul>') ;

// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var currentClass = "active";    // CSS class for menu color
var menuElement = 0;
var EnhancedExerciseEnabled = false;
// on page load call init
var pathname = ""
var baseurl = ""
var DaysOfWeekArray = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];

//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
$(document).ready(function() {
    pathname = window.location.href;
    baseurl = pathname.concat("cmd/")
    GetHeaderValues();
    $("#status").find("a").addClass(GetCurrentClass());
    setInterval(GetBaseStatus, 3000);       // Called every 3 sec
    setInterval(UpdateDisplay, 5000);       // Called every 5 sec
    $("#mydisplay").html(GetDisplayValues("status"));
    CreateSelectLists();
    SetVisibilityOfMaintList();
    $("li").on('click',  function() {  MenuClick($(this));});
});

//*****************************************************************************
//  Set the visibility of lists and buttons
//*****************************************************************************
function SetVisibilityOfMaintList(){

    var visStr;
    if (menuElement == "maint")
    {
        visStr = "visible";
        // set controls to current setting
    }
    else
    {
        visStr = "hidden";
    }
    document.getElementById("setexercise").style.visibility = visStr;
    document.getElementById("days").style.visibility = visStr;
    document.getElementById("daysep").style.visibility = visStr;
    document.getElementById("hours").style.visibility = visStr;
    document.getElementById("timesep").style.visibility = visStr;
    document.getElementById("minutes").style.visibility = visStr;
    document.getElementById("modesep").style.visibility = visStr;
    document.getElementById("quietmode").style.visibility = visStr;
    document.getElementById("setexercisebutton").style.visibility = visStr;
    document.getElementById("settime").style.visibility = visStr;
    if (EnhancedExerciseEnabled == true) {
        document.getElementById("freqsep").style.visibility = visStr;
    }
    document.getElementById("settimebutton").style.visibility = visStr;
    document.getElementById("remotecommands").style.visibility = visStr;
    document.getElementById("remotestop").style.visibility = visStr;
    document.getElementById("remotestart").style.visibility = visStr;
    document.getElementById("remotetransfer").style.visibility = visStr;

}

//*****************************************************************************
//
//*****************************************************************************
Number.prototype.pad = function(size) {
      var s = String(this);
      while (s.length < (size || 2)) {s = "0" + s;}
      return s;
    }

//*****************************************************************************
//  Create menu lists and buttons
//*****************************************************************************
function CreateSelectLists(){

    var myDiv = document.getElementById("myDiv");

    //Create and append select list
    var option = document.createElement("p");
    option.id = "setexercise";
    myDiv.appendChild(option);
    document.getElementById("setexercise").innerHTML = "<br>Generator Exercise Time: ";

    //Create array of options to be added
    var FreqArray = ["Weekly", "Biweekly", "Monthly"];

    //
    if (EnhancedExerciseEnabled == true) {

        var option = document.createElement("p");
        option.id = "freqsep";
        myDiv.appendChild(option);
        document.getElementById("freqsep").innerHTML = "Mode:    ";

        for(var i = 0; i < FreqArray.length; i++)  {

            var choiceSelection = document.createElement('input');
            var label = document.createElement("label");
            choiceSelection.setAttribute('type', 'radio');
            choiceSelection.setAttribute('name', 'choice');
            choiceSelection.setAttribute('value', FreqArray[i]);
            choiceSelection.setAttribute('id', FreqArray[i]);
            choiceSelection.innerHTML = FreqArray[i];
            label.appendChild(choiceSelection);
            label.appendChild(document.createTextNode(FreqArray[i]));
            document.getElementById("freqsep").appendChild(label);
        }

        var ex1 = document.getElementById('Weekly');
        var ex2 = document.getElementById('Biweekly');
        var ex3 = document.getElementById('Monthly');

        ex1.onclick = WeeklyAndBiWeerklyHandlerClick;
        ex2.onclick = WeeklyAndBiWeerklyHandlerClick;
        ex3.onclick = MonthlyHandlerClick;

    }

    //Create and append select list
    var selectList = document.createElement("select");
    selectList.id = "days";
    myDiv.appendChild(selectList);

    //Create and append the options, days
    for (var i = 0; i < DaysOfWeekArray.length; i++) {
        var option = document.createElement("option");
        option.value = DaysOfWeekArray[i];
        option.text = DaysOfWeekArray[i];
        selectList.appendChild(option);
    }

    var option = document.createElement("p");
    option.id = "daysep";
    myDiv.appendChild(option);
    document.getElementById("daysep").innerHTML = ", ";


    //Create and append select list
    var selectList = document.createElement("select");
    selectList.id = "hours";
    myDiv.appendChild(selectList);

    //Create and append the options, hours
    for (var i = 0; i < 24; i++) {
        var option = document.createElement("option");
        option.value = i.pad();
        option.text = i.pad();
        selectList.appendChild(option);
    }

    var option = document.createElement("p");
    option.id = "timesep";
    myDiv.appendChild(option);
    document.getElementById("timesep").innerHTML = ":";

    //Create and append select list
    var selectList = document.createElement("select");
    selectList.id = "minutes";
    myDiv.appendChild(selectList);

    //Create and append the options, minute
    for (var i = 0; i < 60; i++) {
        var option = document.createElement("option");
        option.value = i.pad();
        option.text = i.pad();
        selectList.appendChild(option);
    }

    var option = document.createElement("p");
    option.id = "modesep";
    myDiv.appendChild(option);
    document.getElementById("modesep").innerHTML = "&nbsp&nbsp&nbsp&nbsp";

    //Create and append select list
    var selectList = document.createElement("select");
    selectList.id = "quietmode";
    myDiv.appendChild(selectList);

    var option = document.createElement("option");
    option.value = "QuietMode=On";
    option.text = "Quiet Mode On";
    selectList.appendChild(option);

    var option = document.createElement("option");
    option.value = "QuietMode=Off";
    option.text = "Quiet Mode Off";
    selectList.appendChild(option);

    var option = document.createElement("button");
    option.id = "setexercisebutton";
    option.onclick = SetExerciseClick;
    myDiv.appendChild(option);
    document.getElementById("setexercisebutton").innerHTML = "Set Exercise Time";

    //Create and append select list
    var option = document.createElement("p");
    option.id = "settime";
    myDiv.appendChild(option);
    document.getElementById("settime").innerHTML = "<br>Generator Time: <br><br>";

    var option = document.createElement("button");
    option.id = "settimebutton";
    option.onclick = SetTimeClick;
    myDiv.appendChild(option);
    document.getElementById("settimebutton").innerHTML = "Set Generator Time";

    //Create and append select list
    var option = document.createElement("p");
    option.id = "remotecommands";
    myDiv.appendChild(option);
    document.getElementById("remotecommands").innerHTML = "<br>Remote Commands: <br><br>";

    var option = document.createElement("button");
    option.id = "remotestop";
    option.onclick = SetStopClick;
    myDiv.appendChild(option);
    document.getElementById("remotestop").innerHTML = "Stop Generator";

    var option = document.createElement("p");
    option.id = "p1";
    myDiv.appendChild(option);
    document.getElementById("p1").innerHTML = "<br>";

    var option = document.createElement("button");
    option.id = "remotestart";
    option.onclick = SetStartClick;
    myDiv.appendChild(option);
    document.getElementById("remotestart").innerHTML = "Start Generator";

    var option = document.createElement("p");
    option.id = "p2";
    myDiv.appendChild(option);
    document.getElementById("p2").innerHTML = "<br>";

    var option = document.createElement("button");
    option.id = "remotetransfer";
    option.onclick = SetTransferClick;
    myDiv.appendChild(option);
    document.getElementById("remotetransfer").innerHTML = "Start Generator and Transfer";

    // Create Footer Links
    var FooterStr = "<table border=\"0\" width=\"100%\" height=\"30px\"><tr><td width=\"90%\" style=\"vertical-align:middle\"><a href=\"https://github.com/jgyates/genmon\" target=\"_blank\">GenMon Project on GitHub</a></td></tr></table>";
    $("#footer").html(FooterStr);

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
// called when Monthly is clicked
//*****************************************************************************
function MonthlyHandlerClick(){

    var oldSel = document.getElementById('days');

    while (oldSel.options.length > 0) {
        oldSel.remove(oldSel.options.length - 1);
    }

    //Create and append the options, days
    for (var i = 1; i <= 28; i++) {
        var option = document.createElement("option");
        option.value = i.pad()
        option.text = i.pad();
        oldSel.appendChild(option);
    }

}
//*****************************************************************************
// called when Monthly is clicked
//*****************************************************************************
function WeeklyAndBiWeerklyHandlerClick(){

    var oldSel = document.getElementById('days');

    if (oldSel.options.length == 7) {
        return
    }

    while (oldSel.options.length > 0) {
        oldSel.remove(oldSel.options.length - 1);
    }

    //Create and append the options, days
    for (var i = 0; i < DaysOfWeekArray.length; i++) {
        var option = document.createElement("option");
        option.value = DaysOfWeekArray[i];
        option.text = DaysOfWeekArray[i];
        oldSel.appendChild(option);
    }

}

//*****************************************************************************
// called when Set Remote Stop is clicked
//*****************************************************************************
function SetStopClick(){

    var DisplayStr = "Stop generator? Note: If the generator is powering a load there will be a cool down period of a few minutes.";

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

    SetRemoteCommand("stop")
}

//*****************************************************************************
// called when Set Remote Start is clicked
//*****************************************************************************
function SetStartClick(){

    var DisplayStr = "Start generator?";

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

    SetRemoteCommand("start")
}

//*****************************************************************************
// called when Set Remote Tansfer is clicked
//*****************************************************************************
function SetTransferClick(){

    var DisplayStr = "Start generator and activate transfer switch? Generator will start, warm up, the activate switch.";

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

    SetRemoteCommand("starttransfer")
}

//*****************************************************************************
// called when Set Time is clicked
//*****************************************************************************
function SetTimeClick(){

    var DisplayStr = "Set generator time to monitor time? Note: This operation may take up to one minute to complete";

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

    // set exercise time
    var url = baseurl.concat("settime");
    $.getJSON(  url,
                {settime: " "},
                function(result){
   });

}
//*****************************************************************************
// called when Set Exercise is clicked
//*****************************************************************************
function SetExerciseClick(){

    try {
        var e = document.getElementById("days");
        var strDays = e.options[e.selectedIndex].value;

        var e = document.getElementById("hours");
        var strHours = e.options[e.selectedIndex].value;

        var e = document.getElementById("minutes");
        var strMinutes = e.options[e.selectedIndex].value;

        var e = document.getElementById("quietmode");
        var strQuiet = e.options[e.selectedIndex].value;

        var strExerciseTime = strDays.concat(",")
        strExerciseTime = strExerciseTime.concat(strHours)
        strExerciseTime = strExerciseTime.concat(":")
        strExerciseTime = strExerciseTime.concat(strMinutes)

        if (EnhancedExerciseEnabled == true) {
            /* TODO change this */
            if(document.getElementById("Monthly").checked == true) {
                strExerciseTime = strExerciseTime.concat(",Monthly")
            }
            else if(document.getElementById("Biweekly").checked == true) {
                strExerciseTime = strExerciseTime.concat(",Biweekly")
            }
            else {
                strExerciseTime = strExerciseTime.concat(",Weekly")
            }
        }
        else {
            strExerciseTime = strExerciseTime.concat(",Weekly")
        }
        var DisplayStr = "Set exercise time to ";

        DisplayStr = strExerciseTime.concat(", ")
        DisplayStr = DisplayStr.concat(strQuiet)
        DisplayStr = DisplayStr.concat("?")

        var r = confirm(DisplayStr);
        if (r == false) {
            return
        }
        // set exercise time
        var url = baseurl.concat("setexercise");
        $.getJSON(  url,
                    {setexercise: strExerciseTime},
                    function(result){
       });

        // set quite mode
        var url = baseurl.concat("setquiet");
        $.getJSON(  url,
                    {setquiet: strQuiet},
                    function(result){
       });
    }
    catch(err) {
        alert("Error: invalid selection");
    }
}

//*****************************************************************************
// sets the setexerise control with the current settings
//*****************************************************************************
function SetExerciseChoice(bSetRadio){

    var url = baseurl.concat("getexercise");
    $.getJSON(url,function(result){

        // should return str in this format:
        // Saturday!13!30!On!Weekly!True
        // Saturday!13!30!On!Biweekly!Falze
        // 2!13!30!On!Monthly!False
        // NOTE: Last param (True or False) is if enhanced exercise freq is enabled
        var resultsArray = result.split("!")

        if (resultsArray.length == 6){

            if (resultsArray[4] == "Monthly") {
                MonthlyHandlerClick(false);
            }
            else {
                WeeklyAndBiWeerklyHandlerClick(false);
            }

            try {
                var element = document.getElementById('days');
                element.value = resultsArray[0];
            }
            catch(err) {

            }
            element = document.getElementById('hours');
            element.value = resultsArray[1];

            element = document.getElementById('minutes');
            element.value = resultsArray[2];

            element = document.getElementById('quietmode');
            element.value = "QuietMode=".concat(resultsArray[3]);


            if (EnhancedExerciseEnabled == true) {

                if( bSetRadio == true) {
                    document.getElementById(resultsArray[4]).checked = true;
                }

                if (resultsArray[5] === "False") {
                    document.getElementById("freqsep").style.visibility = "hidden";
                    document.getElementById("Weekly").disabled = true;
                    document.getElementById("Biweekly").disabled = true;
                    document.getElementById("Monthly").disabled = true;
                    EnhancedExerciseEnabled = false;
                }
                else {
                    document.getElementById("freqsep").style.visibility = "visible"
                    document.getElementById("Weekly").disabled = false;
                    document.getElementById("Biweekly").disabled = false;
                    document.getElementById("Monthly").disabled = false;
                    EnhancedExerciseEnabled = true
                }
            }
        }
   });

}

//*****************************************************************************
// Display the Notification Tab
//*****************************************************************************
function DisplayNotifications(){

    var url = baseurl.concat("notifications");
    $.getJSON(url,function(result){

        var  outstr = "Notification Recepients:<br><br>";
        outstr += "<button value=\"+Add\" id=\"addRow\">+Add</button><br><br>";
        outstr += "<form id=\"formNotifications\">";
        // outstr += "<input type=\"hidden\" name=\"deleted_rows\" id=\"deleted_rows\" value=\"\">";
        // outstr += "<input type=\"hidden\" name=\"rowcount\" id=\"rowcount\" value=\"0\">";
        outstr += "<table id=\"allnotifications\" border=\"0\"><tbody>";

        outstr += "<tr id=\"row_0\"><td style=\"padding: 5px;\">&nbsp;&nbsp;&nbsp;&nbsp;</td><td style=\"padding: 5px;\">&nbsp;&nbsp;&nbsp;&nbsp;</td><td width=\"15%\" align=\"center\" style=\"padding: 5px;\">All:</td><td width=\"15%\" align=\"center\" style=\"padding: 5px;\">Outages:</td><td width=\"15%\" align=\"center\" style=\"padding: 5px;\">Errors:</td><td width=\"15%\" align=\"center\" style=\"padding: 5px;\">Warning:</td><td width=\"15%\" align=\"center\" style=\"padding: 5px;\">Information:</td><td></td></tr>";

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

            outstr += "<tr id=\"row_" + rowcount + "\"><td style=\"padding: 5px;\">&nbsp;&nbsp;&nbsp;&nbsp;</td>";
            outstr += "<td style=\"padding: 5px;\"> "+email+"<input type=\"hidden\" name=\"email_" + rowcount + "\" id=\"email_" + rowcount + "\" value=\""+email+"\"></td>";

            $.each( ["all", "outage", "error", "warn", "info"], function( index, type ){
               outstr += "<td width=\"15%\" align=\"center\" style=\"padding: 5px;\">"
               outstr += "<span id=\"bg_"+rowcount+"\"><input id=\"" + type + "_" + rowcount + "\" name=\"" + type + "_" + rowcount + "\" type=\"checkbox\" value=\"true\" " +
                          (((typeof permissions[type] !== 'undefined' ) && (permissions[type].toLowerCase() == "true")) ? " checked " : "") +
                          (((typeof permissions[type] !== 'undefined' ) && (permissions[type].toLowerCase() == "true")) ? " oldValue=\"true\" " : " oldValue=\"false\" ") +
                         "></span>";
               outstr += "</td>";
            });
            outstr += "<td width=\"15%\" align=\"center\" style=\"padding: 5px;\" width=\"15%\"><button type=\"button\" rowcount=" + rowcount + " id=\"removeRow\">Remove</button></td></tr>";
        }
        outstr += "</tbody></table></form><br>";
        outstr += "<button id=\"setnotificationsbutton\" onClick=\"saveNotifications()\">Save</button>";
        $("#mydisplay").html(outstr);
        rowcount++;
        $('#rowcount').val(rowcount);

        $(document).ready(function() {
           $("#addRow").click(function () {
              $("#allnotifications").each(function () {
                  var tds = "<tr id=\"row_" + rowcount + "\"><td style=\"padding: 5px;\">&nbsp;&nbsp;&nbsp;&nbsp;</td>";
                  tds += "<td style=\"padding: 5px;\"><input id=\"email_" + rowcount + "\" style=\"width: 300px;\" name=\"email_" + rowcount + "\" type=\"text\"></td>";

                  $.each( ["all", "outage", "error", "warn", "info"], function( index, type ){
                     tds += "<td width=\"15%\" align=\"center\" style=\"padding: 5px;\">"
                     tds += "<span id=\"bg_"+rowcount+"\"><input id=\"" + type + "_" + rowcount + "\" name=\"" + type + "_" + rowcount + "\" type=\"checkbox\" value=\"true\" ></span>";
                     tds += "</td>";
                  });
                  tds += "<td width=\"15%\" align=\"center\" style=\"padding: 5px;\" width=\"15%\"><button type=\"button\" rowcount=" + rowcount + " id=\"removeRow\">Remove</button></td></tr>";
                  rowcount++;
                  // $('#rowcount').val(rowcount);
                  if ($('tbody', this).length > 0) {
                      $('tbody', this).append(tds);
                  } else {
                      $(this).append(tds);
                  }
              });
           });

           $("#allnotifications tbody").on('click', 'button', function(){
              // $('#deleted_rows').val($('#deleted_rows').val()+$(this).attr("rowcount")+","+$('#email_'+$(this).attr("rowcount")).val()+",");
              $('table#allnotifications tr#row_'+$(this).attr("rowcount")).remove();
           });

           $("#allnotifications tbody").on('change', 'input:checkbox', function(){
              var ids = $(this).attr("id").split('_');
              var myval = ($(this).prop('checked') === true ? "true" : "false");
              // alert ('Row: '+ids[1]+', field: '+ids[0]+', value: '+myval);
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
       alert("Emails cannot be blank. You have "+blankEmails+" blank lines");
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
        alert("Error: invalid selection");
    }
}

//*****************************************************************************
// Display the Settings Tab
//*****************************************************************************
function DisplaySettings(){

    var url = baseurl.concat("settings");
    $.getJSON(url,function(result){

        var outstr = "<form id=\"formSettings\"><table border=\"0\">";
        // var outstr = JSON.stringify(result, null, 4);
        // outstr = replaceAll(outstr,'\n','<br/>')
        // outstr = replaceAll(outstr,' ','&nbsp')
        var settings =  getSortedKeys(result, 2);
        for (var index = 0; index < settings.length; ++index) {
            var key = settings[index];
            if (result[key][2] == 1) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\">General Settings:</td></tr>";
            } else if (result[key][2] == 50) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\"><br><br>Console Settings:</td></tr>";
            } else if (result[key][2] == 40) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\"><br><br>Generator Model Settings:</td></tr>";
            } else if (result[key][2] == 25) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\"><br><br>Webserver Security Settings:</td></tr>";
            } else if (result[key][2] == 101) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\"><br><br>Email Settings:</td></tr>";
            } else if (result[key][2] == 150) {
              outstr += "<tr><td style=\"padding: 5px;\" colspan=\"2\"><br><br>Email Commands Processing:</td></tr>";
            }
            outstr += "<tr><td style=\"padding: 5px;\">&nbsp;&nbsp;&nbsp;&nbsp;</td><td style=\"padding: 5px;\"> "+result[key][1]
            if ((typeof result[key][5] !== 'undefined' ) && (result[key][5] == 1)) {
              outstr += "<div id=\"" + key + "_disabled\"><font size=\"-3\">(disabled)</font></div>";
            }
            outstr += "</td><td style=\"padding: 5px;\">";
            switch (result[key][0]) {
              case "string":
                outstr += "<input id=\"" + key + "\" style=\"width: 400px;\" name=\"" + key + "\" type=\"text\" " +
                           (typeof result[key][3] === 'undefined' ? "" : "value=\"" + replaceAll(result[key][3], '"', '&quot;') + "\" ") +
                           (typeof result[key][3] === 'undefined' ? "" : "oldValue=\"" + replaceAll(result[key][3], '"', '&quot;') + "\" ") +
                           (typeof result[key][4] === 'undefined' ? "" : "title=\"" + replaceAll(result[key][4], '"', '&quot;') + "\" ") +
                          " class=\"tooltip\">";
                break;
              case "int":
                outstr += "<input id=\"" + key + "\" name=\"" + key + "\" type=\"text\" " +
                           (typeof result[key][3] === 'undefined' ? "" : "value=\"" + replaceAll(result[key][3], '"', '&quot;') + "\" ") +
                           (typeof result[key][3] === 'undefined' ? "" : "oldValue=\"" + replaceAll(result[key][3], '"', '&quot;') + "\" ") +
                           (typeof result[key][4] === 'undefined' ? "" : "title=\"" + replaceAll(result[key][4], '"', '&quot;') + "\" ") +
                          " class=\"tooltip\">";
                break;
              case "boolean":
                outstr += "<span id=\"" + key + "_bg\"><input id=\"" + key + "\" name=\"" + key + "\" type=\"checkbox\" " +
                           (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toLowerCase() == "true")) ? " checked " : "") +
                           (((typeof result[key][3] !== 'undefined' ) && (result[key][3].toLowerCase() == "true")) ? " oldValue=\"true\" " : " oldValue=\"false\" ") +
                           (typeof result[key][4] === 'undefined' ? "" : " title=\"" + replaceAll(result[key][4], '"', '&quot;') + "\" ") +
                          " class=\"tooltip\"></span>";
                break;
              default:
                break;
            }
            outstr += "</td>";
        }
        outstr += "</table></form>";
        outstr += "<button id=\"setsettingsbutton\" onClick=\"saveSettings()\">Save</button>";
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
                   $("#"+name+"_bg").css("background-color","#FFB");
                 } else {
                   $(this).css("background-color","#FFB");
                 }
               } else {
                 $(this).css("background-color","#FFF");
                 $("#"+name+"_bg").css("background-color","#FFF");
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
             var DisplayStr2 = '<div class="progress-bar"><span class="progress-bar-fill" style="width: 0%"></span></div>';
             $('.vex-dialog-buttons').html(DisplayStr2);
             $('.progress-bar-fill').queue(function () {
                  $(this).css('width', '100%')
             });
             setTimeout(function(){ vex.closeAll(); if ($('#sitename').val() != $('#sitename').attr('oldValue')) { GetHeaderValues() }}, 10000);
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
        alert("Error: invalid selection");
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
                                 "05ed" : "Ambient Temp Sensor (EvoAC)",
                                 "05f5" : "Unknown Status (EvoAC, Nexus)",
                                 "05fa" : "Unknown Status (EvoAC, Nexus)",
                                 "0034" : "Unknown Sensor (Nexus, EvoAC)",
                                 "0032" : "Unknown Sensor (Nexus, EvoAC)",
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

function DisplayRegisters()
{
    var url = baseurl.concat("registers_json");
    $.getJSON(url,function(result){

        var RegData = result;

        var textOut = "Live Register View:<br><br>";
        textOut += "<center><table width=\"80%\" border=\"5\" style=\"border: 5px solid white;\"><tr>";
        var reg_keys = {};
        $.each(RegData.Registers["Base Registers"], function(i, item) {
            reg_keys[Object.keys(item)[0]] = item[Object.keys(item)[0]]
        });
        $.each(Object.keys(reg_keys).sort(), function(i, reg_key) {
            if ((i % 4) == 0){
                textOut += "</tr><tr>";
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
            textOut += "<td width=\"25%\" style=\"border:5px solid white; background-color: #AAAAAA; vertical-align:bottom\">";
            textOut +=     "<table width=\"100%\" heigth=\"100%\" style=\"border:2px solid #AAAAAA; height:100%;\" id=\"val_"+reg_key+"\">";
            textOut +=         "<tr><td align=\"center\" style=\"border-bottom: 1px solid #444444; font-size:12px;\">" + BaseRegistersDescription[reg_key] + "</td></tr>";
            textOut +=         "<tr><td align=\"center\" style=\"border-bottom: 1px solid #444444; font-size:11px;\">(" + reg_key + ")</td></tr>";
            textOut +=         "<tr><td align=\"center\" id=\"content_"+reg_key+"\">";
            textOut +=            ((reg_key == "01f4") ? "<span style=\"font-size:14px\">HEX:<br>" + reg_val + "</font>" : "HEX: "+reg_val) + "<br>";
            textOut +=            ((reg_key == "01f4") ? "" : "<span style=\"font-size:11px\">DEC: " + parseInt(reg_val, 16) + " | HI:LO: "+parseInt(reg_val.substring(0,2), 16)+":"+parseInt(reg_val.substring(2,4), 16)+"</span>");
            textOut +=         "</td></tr>";
            textOut +=     "</table>";
            textOut += "</td>";
        });
        for (var i = (RegData.Registers["Base Registers"].length % 4); i < 4; i++) {
             textOut += "<td width=\"25%\" style=\"border: 10px;\"></td>";
        }
        textOut += "</tr></table></center>";

        $("#mydisplay").html(textOut);

        var CurrentTime = new Date().getTime();
        $.each(UpdateTime, function( reg_key, update_time ){
            var difference = CurrentTime - update_time;
            var secondsDifference = Math.floor(difference/1000);
            if ((update_time > 0) && (secondsDifference >= fadeOffTime)) {
               $("#val_"+reg_key).css("background-color", "#AAAAAA");
               $("#content_"+reg_key).css("color", "red");
            } else if ((update_time > 0) && (secondsDifference <= fadeOffTime)) {
               var hexShadeR = toHex(255-Math.floor(secondsDifference*85/fadeOffTime));
               var hexShadeG = toHex(Math.floor(secondsDifference*170/fadeOffTime));
               var hexShadeB = toHex(Math.floor(secondsDifference*170/fadeOffTime));
               $("#val_"+reg_key).css("background-color", "#"+hexShadeR+hexShadeG+hexShadeB);
               $("#content_"+reg_key).css("color", "black");
            }
        });

        GlobalOldRegKeys = reg_keys;
        InitOK = true;
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
        switch (target.attr("id")){
            case "status":
            case "maint":
            case "outage":
            case "logs":
            case "monitor":
                window.scrollTo(0,0);
                GetDisplayValues(target.attr("id"));
                if (target.attr("id") == "maint") {
                    SetExerciseChoice(true)
                }
                break;
            case "notifications":
                window.scrollTo(0,0);
                DisplayNotifications();
                SetVisibilityOfMaintList();
                break;
            case "settings":
                window.scrollTo(0,0);
                DisplaySettings();
                SetVisibilityOfMaintList();
                break;
            case "registers":
                window.scrollTo(0,0);
                DisplayRegisters();
                SetVisibilityOfMaintList();
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
        SetVisibilityOfMaintList();

   });

    return
}

//*****************************************************************************
// GetHeaderValues - updates header to display site name
//*****************************************************************************
function GetHeaderValues()
{

    /* Make this call synchronous */
    var url = baseurl.concat("getexercise");

    $.ajax({dataType:"json",url: url, success: function(result){

        // should return str in this format:
        // Saturday!13!30!On!Weekly!True
        // Saturday!13!30!On!Biweekly!Falze
        // Day-2!13!30!On!Monthly!False
        // NOTE: Last param (True or False) is if enhanced exercise freq is enabled
        var resultsArray = result.split("!")

        if (resultsArray.length == 6){

            if (resultsArray[5] === "False") {
                EnhancedExerciseEnabled = false;
            }
            else {
                EnhancedExerciseEnabled = true
            }
        }
    }, async: false});

    url = baseurl.concat("getsitename");
    $.getJSON(url,function(result){

        // replace /n with html friendly <br/>
        var outstr = replaceAll(result,'\n','<br/>')
        // replace space with html friendly &nbsp
        outstr = replaceAll(outstr,' ','&nbsp')
        var HeaderStr = "<table border=\"0\" width=\"100%\" height=\"30px\"><tr><td width=\"30px\"></td><td width=\"90%\" style=\"vertical-align:middle\">Generator Monitor at " + outstr + "</td><td width=\"30px\" style=\"vertical-align:middle\"><img id=\"registers\" src=\"images/registers.png\" width=\"20px\" height=\"20px\"></td></tr></table>";
        $("#myheader").html(HeaderStr);
        $("#registers").on('click',  function() {  MenuClick($(this));});
    });
    return
}

//*****************************************************************************
// UpdateDisplay
//*****************************************************************************
function UpdateDisplay()
{
    if (menuElement == "registers") {
        DisplayRegisters();
    } else if ((menuElement != "settings") && (menuElement != "notifications")) {
        GetDisplayValues(menuElement);
    } else {
        SetVisibilityOfMaintList();
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

        if((baseState === "EXERCISING") || (baseState === "RUNNING")) {
            document.getElementById("remotestop").disabled = false;
            document.getElementById("remotestart").disabled = true;
            document.getElementById("remotetransfer").disabled = true;
        }
        else {
            document.getElementById("remotestop").disabled = true;
            document.getElementById("remotestart").disabled = false;
            document.getElementById("remotetransfer").disabled = false;
        }

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

        }
        return
   });

    return
}
