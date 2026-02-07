@echo off
rem @echo on

REM genmonmaint.bat

set genmondir=%CD%

REM the current working directory should be genmon folder
set currentdir=%CD%
REM Use a FOR loop and path modifiers to get the parent directory
FOR %%I IN ("%currentdir%\..") DO SET parentdir=%%~fI
set config_path=%parentdir%\config\
set log_path=%parentdir%\logs

set install_opt=false
set backup_opt=false
set log_opt=false
set update_opt=false
set noprompt_opt=false
set help_opt=false
set copyfiles_opt=false
set log_opt=false
set pythoncommand=python
set pipoptions=--prefer-binary

REM parse command line
:GETOPTS
if /I "%1" == "-h" set help_opt=true & shift & goto :GETOPTS
if /I "%1" == "-u" set update_opt=true & shift & goto :GETOPTS
if /I "%1" == "-i" set install_opt=true & shift & goto :GETOPTS
if /I "%1" == "-b" set backup_opt=true & shift & goto :GETOPTS
if /I "%1" == "-s" set copyfiles_opt=true & shift & goto :GETOPTS
if /I "%1" == "-n" set noprompt_opt=true & shift & goto :GETOPTS
if /I "%1" == "-l" set log_opt=true & log_path=%2 & shift &shift & goto :GETOPTS
if /I "%1" == "-c" set config_path=%2 & shift & shift & goto :GETOPTS

REM Shift any unhandled arguments and continue the loop
shift
if not "%1" == "" goto :GETOPTS

REM Help
if %help_opt%==true call :printhelp & goto :eof

if %noprompt_opt%==true echo No prompt option enabled.

echo.
echo Config path is %config_path%

REM backup config
if %backup_opt%==true call :backupgenmon & goto :eof

REM backup logs
if %log_opt%==true call :archivelogs & goto :eof

REM copy config files
if %copyfiles_opt%==true call :copyconfigfiles & goto :eof

REM install
if %install_opt%==true call :installgenmon & goto :eof

REM update
if %update_opt%==true call :updategenmon & goto :eof



echo.
echo Exiting genmonmaint.bat
goto :eof


REM ----------------------------------------------------------------------------
:printhelp
    echo.
    echo  Usage:
    echo.
    echo     genmonmaint.bat ^<options^>
    echo.
    echo  Options:
    echo.
    echo   -i           Install genmon and required libraries
    echo   -b           Backup genmon configuration
    echo   -u           Update genmon to the latest version
    echo   -n           Do not prompt for Y/N, assume yes
    echo   -c           Specify full path to config file directory (i.e. C:\project\config\)
    echo   -s           Just copy conf files
    echo   -l           Specify the full path of the log directory to archive (i.e. C:\project\config\)
    echo   -h           Display help
    echo.
exit /b 0

REM ----------------------------------------------------------------------------
:updategenmon

    echo This script will install libraries needed by genmon.
    echo This script assumes you have already downloaded the genmon project via 'git'. 
    echo This script will optionally copy the config files to the configuration 
    echo directory. This script will not test the serial port. This script requires
    echo internet access to download the needed libraries. Press any key to continue. 
    if not %noprompt_opt%==true (
        PAUSE
    )
    echo "Updating genmon..."
    cd %genmondir%
    set current_time=%date% %time%
    
    set update_history=%config_path%update.txt
    if NOT EXIST %update_history% (
        echo %update_history% does not exist, creating file..
        copy NUL %update_history%
    )
    echo "%current_time%" >>  %update_history%
    git config --global --add safe.directory '*'
    git fetch origin
    git reset --hard origin/master
    echo "Update complete."

exit /b 0


REM ----------------------------------------------------------------------------
:installgenmon

    echo This script will install libraries needed by genmon.
    echo This script assumes you have already downloaded the genmon project via 'git'.
    echo This script will optionally copy the config files to the configuration
    echo directory. This script will not test the serial port. This script requires
    echo internet access to download the needed libraries.  
    if not %noprompt_opt%==true (
        SET /P yesno=Do you wish to continue? [Y/N]: 
        IF /I "%yesno%"=="y" GOTO YES
        echo Aborting install.
        exit /b 1
    )
    :YES
    
    echo "Installing genmon..."
    rem %pythoncommand% -m pip install --upgrade setuptools
    %pythoncommand% -m pip install -r %genmondir%/OtherApps/win/requirements_win.txt %pipoptions%
    echo Library install complete..
    echo.
    if not %noprompt_opt%==true (
        echo Copy configuration files to %config_path%? (y/n)?
        SET /P yesno=Do you wish to continue? [Y/N]: 
        IF /I "%yesno%"=="y" GOTO YESCOPY
        goto :NOCOPY
    )
    :YESCOPY
    call :copyconfigfiles
    :NOCOPY
    echo Install complete. Note: you must setup the serial port or network connection you will be using
    echo with genmon. 

exit /b 0

REM ----------------------------------------------------------------------------
:backupgenmon

    echo "Backup genmon..."
    cd %genmondir%
    rmdir /S /Q genmon_backup
    del genmon_backup.tar.gz
    mkdir genmon_backup
    copy %config_path%genalexa.conf  .\genmon_backup
    copy %config_path%gencallmebot.conf .\genmon_backup
    copy %config_path%gencentriconnect.conf .\genmon_backup
    copy %config_path%gencthat.conf .\genmon_backup
    copy %config_path%gencustomgpio.conf .\genmon_backup
    copy %config_path%genemail2sms.conf .\genmon_backup
    copy %config_path%genexercise.conf .\genmon_backup
    copy %config_path%gengpio.conf .\genmon_backup
    copy %config_path%gengpioin.conf .\genmon_backup
    copy %config_path%gengpioledblink.conf .\genmon_backup
    copy %config_path%genhomeassistant.conf .\genmon_backup
    copy %config_path%genloader.conf .\genmon_backup
    copy %config_path%genmon.conf .\genmon_backup
    copy %config_path%genmopeka.conf .\genmon_backup
    copy %config_path%genmqtt.conf .\genmon_backup
    copy %config_path%genmqttin.conf .\genmon_backup
    copy %config_path%genpushover.conf .\genmon_backup
    copy %config_path%genslack.conf .\genmon_backup
    copy %config_path%gensms.conf .\genmon_backup
    copy %config_path%gensms_voip.conf .\genmon_backup
    copy %config_path%gensnmp.conf .\genmon_backup
    copy %config_path%gentankdiy.conf .\genmon_backup
    copy %config_path%gentankutil.conf .\genmon_backup
    copy %config_path%gentemp.conf .\genmon_backup
    copy %config_path%mymail.conf .\genmon_backup
    copy %config_path%mymodem.conf .\genmon_backup
    copy %config_path%outage.txt .\genmon_backup
    copy %config_path%kwlog.txt .\genmon_backup
    copy %config_path%fuellog.txt .\genmon_backup
    copy %config_path%maintlog.json .\genmon_backup
    copy %config_path%update.txt .\genmon_backup
    tar -zcvf genmon_backup.tar.gz genmon_backup
    rmdir /S /Q genmon_backup
    echo Backup complete
exit /b 0

REM ----------------------------------------------------------------------------
:archivelogs

    echo Archive log files from %log_path% ...
    cd %genmondir%
    rmdir /S /Q genmon_logs
    del genmon_logs.tar.gz
    mkdir genmon_logs
    copy %log_path%genmon.log ./genmon_logs
    copy %log_path%genserv.log ./genmon_logs
    copy %log_path%mymail.log ./genmon_logs
    copy %log_path%myserial.log ./genmon_logs
    copy %log_path%mymodbus.log ./genmon_logs
    copy %log_path%gengpio.log ./genmon_logs
    copy %log_path%gengpioin.log ./genmon_logs
    copy %log_path%gensms.log ./genmon_logs
    copy %log_path%gensms_modem.log ./genmon_logs
    copy %log_path%genmqtt.log ./genmon_logs
    copy %log_path%genmqttin.log ./genmon_logs
    copy %log_path%genpushover.log ./genmon_logs
    copy %log_path%gensyslog.log ./genmon_logs
    copy %log_path%genloader.log ./genmon_logs
    copy %log_path%myserialtcp.log ./genmon_logs
    copy %log_path%genlog.log ./genmon_logs
    copy %log_path%genslack.log ./genmon_logs
    copy %log_path%gencallmebot.log ./genmon_logs
    copy %log_path%genexercise.log ./genmon_logs
    copy %log_path%genemail2sms.log ./genmon_logs
    copy %log_path%gencentriconnect.log ./genmon_logs
    copy %log_path%genhomeassistant.log ./genmon_logs
    copy %log_path%gentankutil.log ./genmon_logs
    copy %log_path%genalexa.log ./genmon_logs
    copy %log_path%gensnmp.log ./genmon_logs
    copy %log_path%gentemp.log ./genmon_logs
    copy %log_path%gentankdiy.log ./genmon_logs
    copy %log_path%gengpioledblink.log ./genmon_logs
    copy %log_path%gencthat.log ./genmon_logs
    copy %log_path%genmopeka.log ./genmon_logs
    copy %log_path%gencustomgpio.log ./genmon_logs
    copy %log_path%gensms_voip.log ./genmon_logs
    tar -zcvf genmon_logs.tar.gz genmon_logs
    rmdir /S /Q genmon_logs
    echo "Done."
exit /b 0

REM ----------------------------------------------------------------------------
:copyconfigfiles
    echo "Copying up config files..."
    if NOT EXIST %config_path% (
        mkdir %config_path%
    )
    copy %genmondir%\conf\*.conf %config_path%
    echo Complete.
exit /b 0
