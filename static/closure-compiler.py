#!/usr/bin/python

import os, os.path, shutil
import urllib, zipfile, re, requests
from time import sleep

def compress(compiler, in_files, out_file, in_type='js'):

    if in_type == 'js':
        print ('java -jar %s --js "%s" --js_output_file "%s"' % (compiler, '" --js "'.join(in_files), out_file))
        os.system('java -jar %s --js "%s" --js_output_file "%s"' % (compiler, '" --js "'.join(in_files), out_file))

    if in_type == 'css':
        print ('java -jar %s --allow-unrecognized-functions --allow-unrecognized-properties  --output-file "%s" "%s"' % (compiler, out_file, '" "'.join(in_files)))
        os.system('java -jar %s --allow-unrecognized-functions --allow-unrecognized-properties --output-file "%s" "%s"' % (compiler, out_file, '" "'.join(in_files)))

MINIFY_SCRIPTS = [
    'js/jquery-3.3.1.min.js',
    'js/jquery-ui.min.js',
    'js/jquery.ui.touch-punch.min.js',
    'js/tooltipster.bundle.js',
    'js/vex.combined.min.js',
    'js/gauge.min.js',
    'js/jquery.jqplot.min.js',
    'js/jqplot.dateAxisRenderer.js',
    'js/printThis.js',
    'js/moment.min.js',
    'js/lc_switch.genmon.js',
    'js/selectize.min.js',
    'js/packery.pkgd.min.js',
    'js/jquery.idealforms.genmon.js',
    'js/jquery.CalendarHeatmap.genmon.js',
    'js/jquery.timepicker.min.js',
    'js/jquery.qrcode.min.js',
    'genmon.js'
    ]
NON_MINIFY_SCRIPTS = [
    ]
SCRIPTS_OUT = 'libraries.min.js'

STYLESHEETS = [
    'css/jquery-ui.css',
    'genmon.css',
    'css/jquery.idealforms.css',
    'css/lc_switch.css',
    'css/selectize.default.css',
    'css/vex.css',
    'css/jquery.CalendarHeatmap.css',
    'css/jquery.jqplot.min.css',
    'css/tooltipster.bundle.min.css',
    'css/vex-theme-os.css',
    'css/jquery.timepicker.min.css'
    ]
STYLESHEETS_OUT = 'libraries.min.css'

def main():

    CLOSURE_COMPILER = "closure-compiler-v20200719.jar"
    CLOSURE_STYLESHEET = "closure-stylesheets.jar"

    print( 'Downlaod Compilers...')

    r = requests.get("https://repo1.maven.org/maven2/com/google/javascript/closure-compiler/v20200719/closure-compiler-v20200719.jar", allow_redirects=True)  # to get content after redirection
    with open(CLOSURE_COMPILER, 'wb') as f:
        f.write(r.content)
    # r = requests.get("https://dl.google.com/closure-compiler/compiler-latest.zip", allow_redirects=True)  # to get content after redirection
    # with open("compiler-latest.zip", 'wb') as f:
    #    f.write(r.content)
    # zip_ref = zipfile.ZipFile("compiler-latest.zip", 'r')
    # filenames = zip_ref.namelist()
    # CLOSURE_COMPILER = list(filter(lambda x: re.search(r'.jar', x), filenames))[0]
    # zip_ref.extract(CLOSURE_COMPILER, '.')
    # zip_ref.close()
    # os.remove("compiler-latest.zip")

    print( "Downloaded: "+CLOSURE_COMPILER)

    r = requests.get("https://github.com/google/closure-stylesheets/releases/download/v1.5.0/closure-stylesheets.jar", allow_redirects=True)  # to get content after redirection
    with open(CLOSURE_STYLESHEET, 'wb') as f:
        f.write(r.content)
    print ("Downloaded: "+CLOSURE_STYLESHEET)

    print ('Compressing JavaScript...')
    compress(CLOSURE_COMPILER, MINIFY_SCRIPTS, SCRIPTS_OUT, 'js')

    # temp = open(SCRIPTS_OUT, 'a')
    # for f in NON_MINIFY_SCRIPTS:
    #    fh = open(f)
    #    data = fh.read() + '\n'
    #    fh.close()
    #
    #    temp.write(data)
    #
    #    print ' + %s' % f
    # temp.close()

    print( 'Compressing JavaScript Completed...')
    sleep (5)

    print ('Compressing CSS...')
    compress(CLOSURE_STYLESHEET, STYLESHEETS, STYLESHEETS_OUT, 'css')
    print ('Compressing CSS Completed...')

    os.remove(CLOSURE_COMPILER)
    os.remove(CLOSURE_STYLESHEET)
    print ('Clean-Up completed...')

if __name__ == '__main__':
    main()
