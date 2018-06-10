#!/usr/bin/python

import os, os.path, shutil
import urllib, zipfile, re, requests
from time import sleep

def compress(in_files, out_file, in_type='js'):

    if in_type == 'js':
        print 'java -jar closure-compiler-v20180506.jar --js "%s" --js_output_file "%s"' % ('" --js "'.join(in_files), out_file)
        os.system('java -jar closure-compiler-v20180506.jar --js "%s" --js_output_file "%s"' % ('" --js "'.join(in_files), out_file))

    if in_type == 'css':
        print 'java -jar %s --allow-unrecognized-functions --allow-unrecognized-properties  --output-file "%s" "%s"' % (CLOSURE_COMPILER, out_file, '" "'.join(in_files))
        os.system('java -jar %s --allow-unrecognized-functions --allow-unrecognized-properties --output-file "%s" "%s"' % (CLOSURE_STYLESHEET, out_file, '" "'.join(in_files)))

CLOSURE_COMPILER = "closure-compiler-v20180506.jar";
CLOSURE_STYLESHEET = "closure-stylesheets.jar";
    
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
    'css/vex-theme-os.css'
    ]
STYLESHEETS_OUT = 'libraries.min.css'

def main():
    
    print 'Downlaod Compilers...'

    c1file = urllib.URLopener()
    c1file.retrieve("https://dl.google.com/closure-compiler/compiler-latest.zip", "compiler-latest.zip")
    zip_ref = zipfile.ZipFile("compiler-latest.zip", 'r')
    filenames = zip_ref.namelist()
    CLOSURE_COMPILER = filter(lambda x: re.search(r'.jar', x), filenames)[0]
    zip_ref.extract(CLOSURE_COMPILER, '.')
    zip_ref.close()
    os.remove("compiler-latest.zip") 
    
    print "Downloaded: "+CLOSURE_COMPILER

    r = requests.get("https://github.com/google/closure-stylesheets/releases/download/v1.5.0/closure-stylesheets.jar", allow_redirects=True)  # to get content after redirection
    with open(CLOSURE_STYLESHEET, 'wb') as f:
        f.write(r.content)
    print "Downloaded: "+CLOSURE_STYLESHEET

    print 'Compressing JavaScript...'
    compress(MINIFY_SCRIPTS, SCRIPTS_OUT, 'js')

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

    print 'Compressing JavaScript Completed...'
    sleep (5)

    print 'Compressing CSS...'
    compress(STYLESHEETS, STYLESHEETS_OUT, 'css')
    print 'Compressing CSS Completed...'

    os.remove(CLOSURE_COMPILER)
    os.remove(CLOSURE_STYLESHEET)
    print 'Clean-Up completed...'

if __name__ == '__main__':
    main()