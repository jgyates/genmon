// genmon.js - javascrip source for generator monitor
// Define header
document.getElementById("myheader").innerHTML =
    '<header>Generator Monitor</header>';

// Define main menu
document.getElementById("navMenu").innerHTML =
    '<ul>' +
      '<li><a id="status" >Status</a></li>' +
      '<li><a id="maint" >Maintenance</a></li>' +
      '<li><a id="outage" >Outage</a></li> ' +
      '<li><a id="logs" >Logs</a></li> ' +
      '<li ><a id="monitor" >Monitor</a></li> ' +
      '<li ><a id="notifications" >Notifications</a></li> ' +
      '<li ><a id="settings" >Settings</a></li> ' +
    '</ul>' ;

// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var currentClass = "active";    // CSS class for menu color
var menuElementID = 0;
var EnhancedExerciseEnabled = false;
// on page load call init
window.onload = init;
var pathname = ""
var baseurl = ""
var DaysOfWeekArray = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];

//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
function init(){
    // the code to be called when the dom has loaded

    pathname = window.location.href;
    baseurl = pathname.concat("cmd/")
    GetHeaderValues();
    menuElementID = document.getElementById("status");
    menuElementID.classList.add(GetCurrentClass());
    setInterval(GetBaseStatus, 3000);       // Called every 3 sec
    setInterval(UpdateDisplay, 5000);       // Called every 5 sec
    document.getElementById("mydisplay").innerHTML = GetDisplayValues("status");
    var ul = document.getElementById('navMenu');  // Parent
    CreateSelectLists();
    SetVisibilityOfMaintList();
    // Add event handler for click events
    ul.addEventListener('click', MenuClick);

}

//*****************************************************************************
//  Set the visibility of lists and buttons
//*****************************************************************************
function SetVisibilityOfMaintList(){

    var visStr;
    if (menuElementID.id == "maint")
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
    document.getElementById("settime").innerHTML = "<br>Generator Time: ";

    var option = document.createElement("button");
    option.id = "settimebutton";
    option.onclick = SetTimeClick;
    myDiv.appendChild(option);
    document.getElementById("settimebutton").innerHTML = "Set Generator Time";

    //Create and append select list
    var option = document.createElement("p");
    option.id = "remotecommands";
    myDiv.appendChild(option);
    document.getElementById("remotecommands").innerHTML = "<br>Remote Commands: ";

    var option = document.createElement("button");
    option.id = "remotestop";
    option.onclick = SetStopClick;
    myDiv.appendChild(option);
    document.getElementById("remotestop").innerHTML = "Stop Generator";

    var option = document.createElement("button");
    option.id = "remotestart";
    option.onclick = SetStartClick;
    myDiv.appendChild(option);
    document.getElementById("remotestart").innerHTML = "Start Generator";

    var option = document.createElement("button");
    option.id = "remotetransfer";
    option.onclick = SetTransferClick;
    myDiv.appendChild(option);
    document.getElementById("remotetransfer").innerHTML = "Start Generator and Transfer";

    // Create Footer Links
    var myFooter = document.getElementById("footer");
    var a = document.createElement('a');
    a.href = "https://github.com/jgyates/genmon";
    a.target = "_blank";
    a.innerHTML = "GenMon Project on GitHub";
    myFooter.appendChild(a);

    var option = document.createElement("p");
    option.id = "linksep";
    myFooter.appendChild(option);
    document.getElementById("linksep").innerHTML = " ";

    var a = document.createElement('a');
    var PathName = window.location.href;
    a.href = PathName.concat("internal");
    a.innerHTML = "Generator Registers";
    myFooter.appendChild(a);

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
        outstr += "<button value=\"+Add\" id=\"addRow\"/>+Add</button><br><br>";
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
        document.getElementById("mydisplay").innerHTML = outstr;
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

    var DisplayStr = "Save notifications? Note: Genmon must be restarted for this change to take effect.";

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

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

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
        document.getElementById("mydisplay").innerHTML = outstr;
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
                     $("#displayunknown").removeAttr("disabled");
                 } else {
                     $("#displaymonitor").attr("disabled", "disabled");
                     $("#displayregisters").attr("disabled", "disabled");
                     $("#displaystatus").attr("disabled", "disabled");
                     $("#displaymaintenance").attr("disabled", "disabled");
                     $("#displayunknown").attr("disabled", "disabled");
                 }
            });
            $("#usehttps").change(function () {
                 if(($(this).is(":checked")) & (!$("#usehttps_disabled").is(":visible"))) {
                     $("#useselfsignedcert").removeAttr("disabled");
                     $("#keyfile").removeAttr("disabled");
                     $("#certfile").removeAttr("disabled");
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

    var DisplayStr = "Save settings? Note: Genmon must be restarted for this change to take effect.";

    var r = confirm(DisplayStr);
    if (r == false) {
        return
    }

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
//  called when menu is clicked
//*****************************************************************************
function MenuClick(e)
{

    // is this an anchor
    if (e.target.tagName == 'A'){

        RemoveClass();  // remove class from menu items
        // add class active to the clicked item
        e.target.classList.add(GetCurrentClass());
        // update the display
        switch (e.target.id){
            case "status":
            case "maint":
            case "outage":
            case "logs":
            case "monitor":
                window.scrollTo(0,0);
                menuElementID = e.target;
                GetDisplayValues(e.target.id);
                if (e.target.id == "maint") {
                    SetExerciseChoice(true)
                }
                break;
            case "notifications":
                window.scrollTo(0,0);
                menuElementID = e.target;
                DisplayNotifications();
                SetVisibilityOfMaintList();
                break;
            case "settings":
                window.scrollTo(0,0);
                menuElementID = e.target;
                DisplaySettings();
                SetVisibilityOfMaintList();
                break;
            default:
                break;
        }

    }
}

//*****************************************************************************
// removes the current class from the menu anchor list
//*****************************************************************************
function RemoveClass() {

    var myNodelist = document.getElementsByTagName("a");

    var i;
    // remove all "active" class items (should only be one in the list)
    for (i = 0; i < myNodelist.length; i++)
    {
        myNodelist[i].classList.remove(GetCurrentClass());
    }
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
        document.getElementById("mydisplay").innerHTML = outstr;
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
        var HeaderStr = "Generator Monitor at "
        HeaderStr = HeaderStr.concat(outstr);
        document.getElementById("myheader").innerHTML = HeaderStr
    });
    return
}

//*****************************************************************************
// UpdateDisplay
//*****************************************************************************
function UpdateDisplay()
{
    if ((menuElementID.id != "settings") && (menuElementID.id != "notifications")) {
        GetDisplayValues(menuElementID.id);
    }
    else {
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
            menuElementID.classList.add(GetCurrentClass());

        }
        return
   });

    return
}
