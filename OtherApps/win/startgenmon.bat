@echo off
REM startgenmon.bat 
set pythoncommand=python
set loader_cmd=unknown
set help_opt=false

set genmondir=%CD%

REM the current working directory should be genmon folder
set currentdir=%CD%
REM Use a FOR loop and path modifiers to get the parent directory
FOR %%I IN ("%currentdir%\..") DO SET parentdir=%%~fI
set config_path=%parentdir%\config\

:GETOPTS
if /I "%1" == "start" set loader_cmd=-s & shift & goto :GETOPTS
if /I "%1" == "restart" set loader_cmd=-r & shift & goto :GETOPTS
if /I "%1" == "stop" set loader_cmd=-x & shift & goto :GETOPTS
if /I "%1" == "hardstop" set loader_cmd=-z & shift & goto :GETOPTS
if /I "%1" == "-h" set help_opt=true & shift & goto :GETOPTS
if /I "%1" == "-c" set config_path=%2 & shift & shift & goto :GETOPTS

REM Shift any unhandled arguments and continue the loop
shift
if not "%1" == "" goto :GETOPTS

REM Help
if %help_opt%==true call :printhelp & goto :eof

echo.
echo Config path is %config_path%
if NOT %loader_cmd%==unknown (
    %pythoncommand% genloader.py %loader_cmd% -c %config_path%
) else (
    echo No command specified. Type 'python genloader.py -h' for help.
)

echo.
echo Exiting startgenmon.bat
goto :eof


REM -------------------------------------------------------------------------------
:printhelp
  echo usage:
  echo.
  echo   ./startgenmon.bat ^<options^> start^|stop^|restart^|hardstop
  echo.
  echo valid options:
  echo    -h      display help
  echo    -c      path of config files
  echo.
  exit /b 0
