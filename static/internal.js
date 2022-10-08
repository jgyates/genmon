// internal.js - javascrip source for generator internals
// Define header
document.getElementById("myheader").innerHTML =
    '<header>Generator Registers</header>';

window.onload = init;
var baseurl = ""
var GlobalBaseRegisters;
var InitOK = false;

var BLACK = '<font color="black">';
var RED = '<font color="red">';
var ORANGE = '<font color="orange">';
var BROWN = '<font color="brown">';
var ColorInfo = [];



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

        var textOut = "<ul>";
        for (var i = 0; i < RegData.Registers["Base Registers"].length; i++) {

            if ((i % 4) == 0){
                textOut += "<li>";
            }

            var Str1 = JSON.stringify(RegData.Registers["Base Registers"][i]);
            if (InitOK == true) {
                var Str2 = JSON.stringify(GlobalBaseRegisters.Registers["Base Registers"][i]);
                //console.log("Checking  %s and %s", Str1, Str2);
                if (Str1 != Str2) {
                    Str1 = RED + Str1 +  '</font>';
                    ColorInfo[i].Time = new Date();
                    ColorInfo[i].Color = RED
                }
                else {

                    Str1 = ColorInfo[i].Color + Str1 +  '</font>';
                }
            }
            textOut += Str1 + '&nbsp' + '&nbsp' + '&nbsp' + '&nbsp';

            if ((i % 4) == 3){
                textOut += "<li>";
            }
            else if (i == (RegData.Registers["Base Registers"].length - 1)) {
                textOut += "<li>";
            }
        }
        textOut += "</ul>";

        var jsonStr = JSON.stringify(RegData.Registers["Base Registers"], null, 4);
        //var jsonStr = JSON.stringify(RegData, null, 4);
        //var RegData = JSON.parse(result);
        document.getElementById("mydisplay").innerHTML = textOut;

        GlobalBaseRegisters = RegData;
        if (InitOK == false) {
            InitOK = true;
            for (var i = 0; i < GlobalBaseRegisters.Registers["Base Registers"].length; i++) {
                ColorInfo[i] = new Object;
                ColorInfo[i].Time = new Date();
                ColorInfo[i].Color = BLACK;
            }
        }
    });
}
//*****************************************************************************
// AgeEntries - updates colors of output based on time elapsed
//*****************************************************************************
function AgeEntries()
{
    if (InitOK == false) {
        return
    }

    var CurrentTime = new Date();

    for (var i = 0; i < GlobalBaseRegisters.Registers["Base Registers"].length; i++) {

        var difference = CurrentTime.getTime() - ColorInfo[i].Time.getTime();
        var secondsDifference = Math.floor(difference/1000);

        if (ColorInfo[i].Color == ORANGE) {
            if (secondsDifference > 10) {
                ColorInfo[i].Color = BROWN;
            }
        }
        if (ColorInfo[i].Color == RED) {
            if (secondsDifference > 5) {
                ColorInfo[i].Color = ORANGE;
            }
        }


    }

}
