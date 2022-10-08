SNMP-MIB for GenMon.





ABOUT:

This MIB is provided to allow users and NMS applications to be able to query an
SNMP-enabled GenMon installation using symbolic names rather than OIDs.

The MIB in this directory assumes that the user is running GenMon with a
default Enterprise ID of '58399'.

If the user wishes to change the enterprise ID, the change has to be made in
two locations:

- The GenMon UI        (under "Add-ons", under the SNMP Support window.)
- The MIB file itself. (change line 10 after the 'enterprises' keyword )

Changing either location may cause the OIDs to not get mapped correctly and may
cause unexpected errors in an SNMP-aware NMS.


FILES:
genmon.mib    - The primary MIB file.


GENERATOR SUPPORT:

The MIB and underlying SNMP structure is controller agnostic however due to
some OIDs only being used for specific controllers (or specific states of
the generator), a blank response may be returned.

Some OIDs will only return data if the generator is running, other OIDs will
only return data for specific controllers (and again, only in certain states.)

You can use snmptranslate to pull up a quick message about a particular OID.

If the OID says:                       Then it will work on:
(Evo/Nexus)                            Evolution or Nexus controllers.
(h100)                                 H100 controllers.
(h100/PowerZone)                       H100 or PowerZone controllers.
(PowerZone)                            Only PowerZone controllers.
(Any controller) or (Generic)          Any controller that works with GenMon.

Be aware, some OIDs may not return data, even with the correct controller.
A single phase H100 controller will not return data for GenMon-MIB::VoltageBC
as that OID only populates for 3-phase generators.




INSTALLATION:

Installing these MIBs depends on which distribution or NMS application will be
monitoring GenMon.  For most cases, copying all .mib files in this directory
to '/usr/share/snmp/mibs' is adequate,  Other distributions may require the
MIBs be copied to another directory.

In some distributions, editing /etc/snmp/snmp.conf is necessary.  Locate the
"mibs" line (it may or may not be commented out)

and add "ALL" to the end of it:

(Before) > mibs :
(after)  > mibs ALL




VERIFICATION:

Verification of the MIBs can be performed using 'snmptranslate' as follows:

> $ snmptranslate -Td GenMon-MIB::switchState

which should return the following:

> GenMon-MIB::switchState
> switchState OBJECT-TYPE
>   -- FROM	GenMon-MIB
>   SYNTAX	OCTET STRING
>   MAX-ACCESS	read-only
>   STATUS	mandatory
>   DESCRIPTION	"(All controllers) The current ready state of the generator based on control panel status. (Auto/Off/Manual)"
> ::= { iso(1) org(3) dod(6) internet(1) private(4) enterprises(1) genmon(58399) controllerID(0) status(0) engineData(0) 1 }


If the above produces a result as above, you're all set.  If it produces an
error like the one below, check the MIB search path and ensure the MIBs in this
directory are in one of the directories in the MIB search path.

> $ snmptranslate -Td GenMon-MIB::switchState
> MIB search path: /home/matt/.snmp/mibs:/usr/share/snmp/mibs:/usr/share/ \
>  snmp/mibs/iana:/usr/share/snmp/mibs/ietf:/usr/share/mibs/site:/usr/share \
>  /snmp/mibs:/usr/share/mibs/iana:/usr/share/mibs/ietf:/usr/share/mibs/netsnmp
> Cannot find module (GenMon-MIB): At line 1 in (none)
> GenMon-MIB::switchState: Unknown Object Identifier

Finally, query the GenMon controller using snmpget:

> $ snmpget -v1 -c public (hostname_or_IP_of_genmon) GenMon-MIB::switchState

It should answer with the below (assuming your generator is in Auto mode):

> GenMon-MIB::switchState = STRING: "Auto"

From there, snmpwalk can be used to retrieve the OID data.

> $ snmpwalk -v1 -c public (hostname_or_IP_of_genmon) .




NAGIOS CONFIGURATION:

Nagios contains a basic SNMP plugin called "check_snmp".  While the full
capabilities of check_snmp are beyond the scope of this document, a basic
example is included below:

> $ ./check_snmp -C public -H IP.ADDR.OF.GENMON -o GenMon-MIB::switchState \
    -s \"Auto\"

This command will return a CRITICAL status if the generator is not in "Auto"
state.  Using the -s parameter, you can set up Nagios to alert if the expected
result string is not the result returned when polled.
