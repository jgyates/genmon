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
    '</ul>' ;

// global base state
var baseState = "READY";        // updated on a time
var currentbaseState = "READY"; // menus change on this var
var currentClass = "active";    // CSS class for menu color
var menuElementID = 0;
// on page load call init
window.onload = init;
var pathname = ""
var baseurl = ""

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
    CreateSelectLists()
    SetVisibilityOfMaintList()
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
    var array = ["Sunday","Monday","Tuesday","Wednesday", "Thursday", "Friday", "Saturday"];

    //Create and append select list
    var selectList = document.createElement("select");
    selectList.id = "days";
    myDiv.appendChild(selectList);

    //Create and append the options
    for (var i = 0; i < array.length; i++) {
        var option = document.createElement("option");
        option.value = array[i];
        option.text = array[i];
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

    //Create and append the options
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

    //Create and append the options
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

    var DisplayStr = "Set exercise time to ";
    DisplayStr = DisplayStr.concat(strDays)
    DisplayStr = DisplayStr.concat(", ")
    DisplayStr = DisplayStr.concat(strHours)
    DisplayStr = DisplayStr.concat(":")
    DisplayStr = DisplayStr.concat(strMinutes)
    DisplayStr = DisplayStr.concat("  ")
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

//*****************************************************************************
// sets the setexerise control with the current settings
//*****************************************************************************
function SetExerciseChoice(){

    var url = baseurl.concat("getexercise");
    $.getJSON(url,function(result){

        // should return str in this format: Saturday!13!30!On
        var resultsArray = result.split("!")

        if (resultsArray.length == 4){

            var element = document.getElementById('days');
            element.value = resultsArray[0];

            element = document.getElementById('hours');
            element.value = resultsArray[1];

            element = document.getElementById('minutes');
            element.value = resultsArray[2];

            element = document.getElementById('quietmode');
            element.value = "QuietMode=".concat(resultsArray[3]);
        }
   });

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
                    SetExerciseChoice()
                }
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
    GetDisplayValues(menuElementID.id);
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
