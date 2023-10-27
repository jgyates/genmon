// internal.js - javascrip source for generator internals
// Define header
document.getElementById("myheader").innerHTML =
    '<header>Generator Registers</header>';

window.onload = init;
var baseurl = ""
var GlobalBaseRegisters = null;
var InitColorComplete = false;

var BLACK = '<font color="black">';
var RED = '<font color="red">';
var ORANGE = '<font color="orange">';
var BROWN = '<font color="brown">';
//var ColorInfo = [];
ColorInfo = {"Holding Registers": [], 
             "Input Registers": [],
              "Coil Registers": []};




//*****************************************************************************
// called on window.onload
//      sets up listener events (click menu) and inits the default page
//*****************************************************************************
function init(){
    // the code to be called when the dom has loaded

    baseurl = window.location.protocol + "//" + window.location.host + "/" + "cmd/";
    setInterval(GetDisplayValues, 1000);            // Called every 1 sec
    setInterval(AgeEntries, (2000));                // Called every 2 sec
    document.getElementById("mydisplay").innerHTML = GetDisplayValues();

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

    var myFooter = document.getElementById("footer");
    var a = document.createElement('a');
    a.href = window.location.protocol + "//" + window.location.host
    a.innerHTML = "Generator Monitor";
    myFooter.appendChild(a);

}

//*****************************************************************************
// GetDisplayValues - updates display based on command sent to server
//*****************************************************************************
function GetDisplayValues()
{
    var url = baseurl.concat("registers_json");
    $.getJSON(url,function(result){

        var RegData = result;
        var textOut = ""

        if (InitColorComplete == false) {
            InitColor("Holding Register", RegData)
            InitColor("Input Registers", RegData)
            InitColor("Coil Register", RegData)
            InitColorComplete = true;
        }

        textOut += "<br><h3>Holding Registers:</h3><br>"
        textOut += DisplayRegisterData("Holding Registers", RegData)
        textOut += "<br><h3>Input Registers:</h3><br>"
        textOut += DisplayRegisterData("Input Registers", RegData)
        textOut += "<br><h3>Coil Registers:</h3><br>"
        textOut += DisplayRegisterData("Coil Registers", RegData)
        GlobalBaseRegisters = RegData;
        document.getElementById("mydisplay").innerHTML = textOut;

    });
}

//*****************************************************************************
// DisplayRegisterData - updates display based on command sent to server (helper)
//*****************************************************************************
function DisplayRegisterData(register_type, RegData)
{
    if (!(RegData.Registers.hasOwnProperty(register_type))){
        return ""
    }
    var textOut = "<ul>";
    for (var i = 0; i < RegData.Registers[register_type].length; i++) {

        if ((i % 4) == 0){
            textOut += "<li>";
        }

        if (GlobalBaseRegisters == null){
            Str1 = JSON.stringify(RegData.Registers[register_type][i]);
        }
        else{
            var Str1 = JSON.stringify(GlobalBaseRegisters.Registers[register_type][i]);
        }
        
        if (InitColorComplete == true) {
            var Str2 = JSON.stringify(RegData.Registers[register_type][i]);
            //console.log("Checking  %s and %s", Str1, Str2);
            if (Str1 != Str2) {
                Str1 = RED + Str1 +  '</font>';
                ColorInfo[register_type][i].Time = new Date();
                ColorInfo[register_type][i].Color = RED
            }
            else {

                Str1 = ColorInfo[register_type][i].Color + Str1 +  '</font>';
            }
        }
        textOut += Str1 + '&nbsp' + '&nbsp' + '&nbsp' + '&nbsp';

        if ((i % 4) == 3){
            textOut += "<li>";
        }
        else if (i == (RegData.Registers[register_type].length - 1)) {
            textOut += "<li>";
        }
    }
    textOut += "</ul>";

    var jsonStr = JSON.stringify(RegData.Registers[register_type], null, 4);
    //var jsonStr = JSON.stringify(RegData, null, 4);
    //var RegData = JSON.parse(result);

    
    return textOut

}
//*****************************************************************************
// Init Color entries
//*****************************************************************************
function InitColor(register_type, RegData){

    if (!(RegData.Registers.hasOwnProperty(register_type))){
        return
    }
    for (var i = 0; i < RegData.Registers[register_type].length; i++) {
        ColorInfo[register_type][i] = new Object;
        ColorInfo[register_type][i].Time = new Date();
        ColorInfo[register_type][i].Color = BLACK;
    }

}
//*****************************************************************************
// AgeEntries - updates colors of output based on time elapsed
//*****************************************************************************
function AgeEntries()
{
    if (InitColorComplete == false) {
        return
    }

    AgeOneEntry("Holding Registers")
    AgeOneEntry("Input Registers")
    AgeOneEntry("Coil Registers")



}
//*****************************************************************************
// AgeOneEntry - updates colors of output based on time elapsed (helper)
//*****************************************************************************
function AgeOneEntry(register_type) {

    var CurrentTime = new Date();
    if (GlobalBaseRegisters == null){
        return
    }
    if (InitColorComplete == false) {
        return
    }
    if (!(GlobalBaseRegisters.Registers.hasOwnProperty(register_type))){
        return 
    }
    for (var i = 0; i < GlobalBaseRegisters.Registers[register_type].length; i++) {

        var difference = CurrentTime.getTime() - ColorInfo[register_type][i].Time.getTime();
        var secondsDifference = Math.floor(difference/1000);

        if (ColorInfo[register_type][i].Color == ORANGE) {
            if (secondsDifference > 10) {
                ColorInfo[register_type][i].Color = BROWN;
            }
        }
        if (ColorInfo[register_type][i].Color == RED) {
            if (secondsDifference > 5) {
                ColorInfo[register_type][i].Color = ORANGE;
            }
        }
    }

}
