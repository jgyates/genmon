#!/usr/bin/python

### USES YUICOMPRESSOR FROM: 
### https://github.com/yui/yuicompressor/releases

import os, os.path, shutil

YUI_COMPRESSOR = 'yuicompressor-2.4.8.jar'

def compress(in_files, out_file, in_type='js', verbose=False,
             temp_file='.temp'):
    temp = open(temp_file, 'w')
    for f in in_files:
        fh = open(f)
        data = fh.read() + '\n'
        fh.close()

        temp.write(data)

        print ' + %s' % f
    temp.close()

    options = ['-o "%s"' % out_file,
               '--type %s' % in_type]
               ## '--nomunge',
               ## '--disable-optimizations']

    if verbose:
        options.append('-v')

    os.system('java -jar "%s" %s "%s"' % (YUI_COMPRESSOR, ' '.join(options), temp_file))

    org_size = os.path.getsize(temp_file)
    new_size = os.path.getsize(out_file)

    print '=> %s' % out_file
    print 'Original: %.2f kB' % (org_size / 1024.0)
    print 'Compressed: %.2f kB' % (new_size / 1024.0)
    print 'Reduction: %.1f%%' % (float(org_size - new_size) / org_size * 100)
    print ''

    os.remove(temp_file)
    
MINIFY_SCRIPTS = [
    'js/jquery.ui.touch-punch.min.js',
    'js/tooltipster.bundle.js',
    'js/vex.combined.min.js',
    'js/gauge.min.js',
    'js/jquery.jqplot.min.js',
    'js/jqplot.dateAxisRenderer.js',
    'js/printThis.js',
    'js/moment.min.js',
    'js/lc_switch.genmon.js',
    'js/selectize.min.js'
    ]
NON_MINIFY_SCRIPTS = [
    'js/packery.pkgd.min.js',
    'js/jquery.idealforms.genmon.js',
    'js/jquery.CalendarHeatmap.genmon.js'
    ]
SCRIPTS_OUT_DEBUG = 'libraries.js'
SCRIPTS_OUT = 'libraries.min.js'

STYLESHEETS = [
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
    print 'Compressing JavaScript...'
    compress(MINIFY_SCRIPTS, SCRIPTS_OUT, 'js', True, SCRIPTS_OUT_DEBUG)

    temp = open(SCRIPTS_OUT, 'a')
    for f in NON_MINIFY_SCRIPTS:
        fh = open(f)
        data = fh.read() + '\n'
        fh.close()

        temp.write(data)

        print ' + %s' % f
    temp.close()

    print 'Compressing CSS...'
    compress(STYLESHEETS, STYLESHEETS_OUT, 'css', True, "libraries.css")

if __name__ == '__main__':
    main()