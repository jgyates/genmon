/*
 *  calendarheatmap - v0.0.3
 *  A simple Calendar Heatmap for jQuery.
 *  https://github.com/SeBassTian23/CalendarHeatmap
 *
 *  Made by Sebastian Kuhlgert
 *  Under MIT License
 */
( function( $ ) {

    "use strict";

        // Default Options
        var pluginName = "CalendarHeatmap",
            defaults = {
                title: null,
                months: 12,
                weekStartDay: 1,
                lastMonth: new Date().getMonth() + 1,
                lastYear: new Date().getFullYear(),
                coloring: null,
                labels: {
                    days: false,
                    months: true,
                    custom: {
                        weekDayLabels: null,
                        monthLabels: null
                    }
                },
                tiles: {
                    shape: "square"
                },
                legend: {
                    show: true,
                    align: "right",
                    minLabel: "Less",
                    maxLabel: "More",
                    divider: " to "
                },
                tooltips: {
                    show: false,
                    options: {}
                }
            };

        // The actual plugin constructor
        function Plugin( element, data, options ) {
            this.element = element;
            this.data = data;
            this.settings = $.extend( true, {}, defaults, options );
            this._defaults = defaults;
            this._name = pluginName;
            this.init();
        }

        // Avoid Plugin.prototype conflicts
        $.extend( Plugin.prototype, {
            init: function() {

                // Run Calandar Heatmap Function
                this.calendarHeatmap();
            },
            _parse: function( dates ) {
                var arr = [];
                if ( !Array.isArray( dates ) || typeof dates !== "object" ) {
                    console.log( "Invalid data source" );
                    return null;
                } else {
                    if ( Array.isArray( dates ) && dates.length > 0 ) {
                        var arrtype = typeof dates[ 0 ];
                        if ( typeof dates[ 0 ] === "object" && !Array.isArray( dates[ 0 ] ) ) {
                            if ( dates[ 0 ].date && dates[ 0 ].count ) {
                                arr = [];
                                for ( var h in dates ) {
                                    var objDate = dates[ h ].date;
                                    if ( this._isNumeric( dates[ h ].date ) ) {
                                        objDate = parseInt( dates[ h ].date );
                                    }
                                    arr.push( {
                                        "count": parseInt( dates[ h ].count ),
                                        "date": this._dateFormat( objDate ),
                                        "dateFormatted": dates[ h ].dateFormatted,
                                        "title": dates[ h ].title,
                                    } );
                                }
                                return arr;
                            } else {
                                    console.log( "Invalid Object format." );
                                return null;
                            }
                        } else if ( [ "string", "date", "number" ].indexOf( arrtype ) > -1 ) {
                            if ( this._dateValid( dates[ 0 ] ) ) {
                                var obj = {};
                                for ( var i in dates ) {
                                    var d = this._dateFormat( dates[ i ] );
                                    if ( !obj[ d ] ) {
                                        obj[ d ] = 1;
                                    } else {
                                        obj[ d ] += 1;
                                    }
                                }
                                arr = [];
                                for ( var j in obj ) {
                                    arr.push( {
                                        "count": parseInt( obj[ j ] ),
                                        "date": j
                                    } );
                                }
                                return arr;
                            } else {
                                console.log( "Invalid Date format." );
                                return null;
                            }
                        } else {
                            console.log( "Invalid format." );
                            return null;
                        }
                    } else if ( Array.isArray( dates ) && dates.length === 0 ) {
                        return [];
                    } else if ( typeof dates === "object" && !Object.empty( dates ) ) {
                        var keys = Object.keys( dates );
                        if ( this._dateValid( keys[ 0 ] ) ) {
                            if ( this._isNumeric( dates[ keys[ 0 ] ] ) ) {
                                var data = [];
                                for ( var k in dates ) {
                                    data.push( {
                                        "count": parseInt( dates[ k ] ),
                                        "date": this._dateFormat( k )
                                    } );
                                }
                                return data;
                            }
                        } else {
                            console.log( "Invalid Date format." );
                            return null;
                        }
                    } else {
                        return null;
                    }
                }
            },
            _pad: function( str, max ) {
                str = String( str );
                return str.length < max ? this._pad( "0" + str, max ) : str;
            },
            _calculateBins: function( events ) {

                // Calculate bins for events
                var i;
                var bins = this.settings.steps || 4;
                var binlabels = [ "0" ];
                var binlabelrange = [ [ 0, 0 ] ];

                // Create an array with all counts
                var arr = events.map( function( x ) {
                    return parseInt( x.count );
                } );

                var minCount = Math.min.apply( Math, arr );
                var maxCount = Math.max.apply( Math, arr );
                var stepWidth = Math.ceil( maxCount / bins );

                if ( stepWidth === 0 ) {
                    stepWidth = maxCount / bins;
                    if ( stepWidth < 1 ) {
                        stepWidth = 1;
                    }
                }

                // Generate bin lables and ranges
                binlabelrange = [ [ 0, 0 ] ];
                if ( !Number.isFinite( minCount ) ) {
                    binlabels = [ "" ];
                } else {
                    binlabels = [ "0" ];
                }

                for ( i = 0; i < bins; i++ ) {

                    var r1 = ( stepWidth * i ) + 1;
                    var r2 = stepWidth * ( i + 1 );

                    binlabelrange.push( [ r1, r2 ] );

                    if ( !Number.isFinite( minCount ) ) {
                        binlabels.push( "" );
                    } else if ( Number.isNaN( r1 ) || !Number.isFinite( r1 ) ) {
                        binlabels.push( "" );
                    } else if ( r1 === r2 ) {
                        binlabels.push( String( r1 ) );
                    } else {
                        binlabels.push( String( r1 ) +
                            ( this.settings.legend.divider || " to " ) +
                            String( r2 ) );
                    }
                }

                // Assign levels (bins) to counts
                for ( i in events ) {
                    events[ i ].level = this._matchBin( binlabelrange, events[ i ].count );
                }

                return { events: events, bins: binlabels };
            },
            _matchBin: function( range, value ) {
                for ( var r in range ) {
                    if ( value >= range[ r ][ 0 ] && value <= range[ r ][ 1 ] ) {
                        return parseInt( r );
                    }
                }
                return 0;
            },
            _matchDate: function( obj, key ) {
                return obj.find( function( x ) {
                    return x.date === key;
                } ) || null;
            },
            _matchDateIdx: function( obj, key ) {
                return obj.findIndex( function( x ) {
                    return x.date === key;
                } );
            },
            _futureDate: function( str ) {
                var current = this._dateFormat().split( "-" );
                var compare = str.split( "-" );

                if ( parseInt( current[ 0 ] ) < parseInt( compare[ 0 ] ) ) {
                    return true;
                } else if ( parseInt( current[ 0 ] ) === parseInt( compare[ 0 ] ) &&
                        parseInt( current[ 1 ] ) < parseInt( compare[ 1 ] )
                    ) {
                    return true;
                } else if ( parseInt( current[ 0 ] ) === parseInt( compare[ 0 ] ) &&
                        parseInt( current[ 1 ] ) === parseInt( compare[ 1 ] ) &&
                        parseInt( current[ 2 ] ) < parseInt( compare[ 2 ] )
                    ) {
                    return true;
                }
                return false;
            },
            _isNumeric: function( n ) {
                return !isNaN( parseFloat( n ) ) && isFinite( n );
            },
            _dateValid: function( d ) {
                if ( String( d ).match( /^(\d{4}-\d{2}-\d{2})$/ ) ||
                    ( String( d ).match( /^(\d{1,13})$/ ) && typeof d === "number" ) ) {
                    return true;
                } else {
                    return false;
                }
            },
            _dateWords: {
                "MMM": [
                    "Jan",
                    "Feb",
                    "Mar",
                    "Apr",
                    "May",
                    "Jun",
                    "Jul",
                    "Aug",
                    "Sep",
                    "Oct",
                    "Nov",
                    "Dec"
                ],
                "MMMM": [
                    "January",
                    "February",
                    "March",
                    "April",
                    "May",
                    "June",
                    "July",
                    "August",
                    "September",
                    "October",
                    "November",
                    "December"
                ],
                "dd": [
                    "Su",
                    "Mo",
                    "Tu",
                    "We",
                    "Th",
                    "Fr",
                    "Sa"
                ],
                "ddd": [
                    "Sun",
                    "Mon",
                    "Tue",
                    "Wed",
                    "Thu",
                    "Fri",
                    "Sat"
                ],
                "dddd": [
                    "Sunday",
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday"
                ]
            },
            _dateFormat: function( d, str ) {
                if ( d === undefined ) {
                    d = new Date();
                } else {
                    if ( typeof d === "string" ) {
                        d = d.split( "-" );
                        d = new Date( parseInt( d[ 0 ] ),
                                parseInt( d[ 1 ] ) - 1,
                                parseInt( d[ 2 ] )
                            );
                    }
                }
                if ( str === undefined ) {
                    str = "YYYY-MM-DD";
                }
                var words = this._dateWords;
                return str.replace( /(Y{2,4})|(M{1,4})|(d{1,4})|(D{1,2})/g, function( s ) {
                    if ( s === "YY" ) {
                        return parseInt( d.getFullYear().toString().slice( 2, 4 ) );
                    }
                    if ( s === "YYYY" ) {
                        return d.getFullYear();
                    }
                    if ( s === "M" ) {
                        return d.getMonth() + 1;
                    }
                    if ( s === "MM" ) {
                        str = String( d.getMonth() + 1 );
                        return str.length < 2 ? "0" + str : str;
                    }
                    if ( s === "MMM" || s === "MMMM" ) {
                        return words[ s ][ d.getMonth() ];
                    }
                    if ( s === "D" ) {
                        return d.getDate();
                    }
                    if ( s === "DD" ) {
                        str = String( d.getDate() );
                        return str.length < 2 ? "0" + str : str;
                    }
                    if ( s === "d" ) {
                        return d.getDay() + 1;
                    }
                    if ( s === "dd" || s === "ddd" || s === "dddd" ) {
                        return words[ s ][ d.getDay() ];
                    }
                    return s;
                } );
            },
            _addWeekColumn: function( ) {
                if ( this.settings.labels.days ) {
                    $( ".ch-year", this.element )
                        .append( "<div class=\"ch-week-labels\"></div>" );

                    $( ".ch-week-labels", this.element )
                        .append( "<div class=\"ch-week-label-col\"></div>" );

                    $( ".ch-week-label-col", this.element )
                        .append( "<div class=\"ch-day-labels\"></div>" );

                    // If month labels are displayed a placeholder needs to be added
                    if ( this.settings.labels.months ) {
                        $( ".ch-week-labels", this.element )
                            .append( "<div class=\"ch-month-label\">&nbsp;</div>" );
                    }

                    var swd = this.settings.weekStartDay;

                    for ( var i = 0; i < 7; i++ ) {

                        var dayNumber = ( ( i + swd ) < 7 ) ? ( i + swd ) : ( i + swd - 7 );
                        var dayName = this._dateWords.ddd[ dayNumber ];

                        if ( ( i - 1 ) % 2 ) {
                            var wdl = this.settings.labels.custom.weekDayLabels;
                            if ( Array.isArray( wdl ) ) {
                                dayName = wdl[ dayNumber ] || "";
                            } else if ( typeof wdl === "string" ) {
                                dayName = this._dateWords[ wdl ][ dayNumber ] || "";
                            } else if ( typeof wdl === "function" ) {
                                dayName = wdl( dayNumber );
                            }
                        } else {
                            dayName = "&nbsp;";
                        }
                        $( "<div>", {
                            class: "ch-day-label",
                            html: dayName
                        } )
                        .appendTo( $( ".ch-day-labels", this.element ) );
                    }
                }
            },
            calendarHeatmap: function( ) {

                var data = this._parse( this.data );

                if ( !Array.isArray( data ) ) {
                    return;
                }

                this.data = data;
                var calc = this._calculateBins( data );
                var events = calc.events;
                var binLabels = calc.bins;
                var currMonth = this.settings.lastMonth;
                var currYear = this.settings.lastYear;
                var months = this.settings.months;
                var i;

                // Start day of the week
                var swd = this.settings.weekStartDay || 1;

                // Empty container first
                $( this.element ).empty();

                // Add a title to the container if not null
                if ( this.settings.title ) {
                    $( "<h3>", {
                        class: "ch-title",
                        html: this.settings.title
                    } ).appendTo( $( this.element ) );
                }

                // Add the main container for the year
                $( this.element ).addClass( "ch" )
                    .append( "<div class=\"ch-year\"></div>" );

                // Add labels
                this._addWeekColumn();

                // Adjust tile shape
                if ( this.settings.tiles.shape && this.settings.tiles.shape !== "square" ) {
                    $( this.element ).addClass( " ch-" + this.settings.tiles.shape );
                }

                var month = currMonth;
                var year = currYear;
                var blocks = [];
                for ( i = 0; i < months; i++ ) {
                    month += -1;
                    if ( month < 0 ) {
                        year -= 1;
                        month += 12;
                    }
                    blocks.push( [ month, year ] );
                }

                // Reverse the array to show the latest month last
                blocks.reverse();

                // Start building the months
                for ( i = 0; i < blocks.length; i++ ) {

                    month = blocks[ i ][ 0 ];
                    year = blocks[ i ][ 1 ];

                    // Build Month
                    var monthName = this._dateFormat( year + "-" + ( month + 1 ) + "-1", "MMM" );

                    var ml = this.settings.labels.custom.monthLabels;
                    if ( ml ) {
                        if ( Array.isArray( ml ) ) {
                            monthName = ml[ month ] || "";
                        } else if ( typeof ml === "function" ) {
                            monthName = ml( year, month + 1 );
                        } else {
                            monthName = this._dateFormat( year + "-" + ( month + 1 ) + "-1", ml );
                        }
                    }
                    $( ".ch-year", this.element )
                        .append( "<div class=\"ch-month\"></div>" );

                    $( ".ch-month:last", this.element )
                        .append( "<div class=\"ch-weeks\"></div>" );

                    if ( this.settings.labels.months ) {
                        $( ".ch-month:last", this.element )
                        .append( "<div class=\"ch-month-label\">" + monthName + "</div>" );
                    }

                    // Get the number of days for the month
                    var days = new Date( year, ( month + 1 ), 0 ).getDate();

                    // Add the first week
                    $( ".ch-month:last .ch-weeks", this.element )
                        .append( "<div class=\"ch-week\"></div>" );

                    // Week day counter
                    var wc = 0;
                    for ( var j = 0; j < days; j++ ) {
                        var str = year + "-" + this._pad( ( month + 1 ), 2 );
                        str += "-" + this._pad( ( j + 1 ), 2 );
                        var obj = this._matchDate( events, str );
                        var future = "";
                        if ( this._futureDate( str ) ) {
                            future = " is-after-today";
                        }
                        if ( obj ) {
                            // var title = obj.count + " on ";
                            // title += this._dateFormat( obj.date, "MMM D, YYYY" );

                            var color = "";

                            if ( this.settings.coloring ) {
                                color = " " + this.settings.coloring + "-" + obj.level;
                            }

                            $( "<div/>", {
                                "class": "tooltip ch-day lvl-" + obj.level + color,
                                "title": '<center><b>'+obj.dateFormatted+'</b></center><small>'+obj.title+'</small>',
                                "data-toggle": "tooltip"
                            } ).appendTo(
                                $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                            );

                        } else {
                            $( "<div/>", {
                                "class": "ch-day" + future
                            } ).appendTo(
                                $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                            );
                        }

                        // Get the iso week day to see if a new week has started
                        var wd = new Date( year, month, ( j + 2 ) ).getDay();
                        if ( wd === 0 ) {
                            wd = 7;
                        }

                        // Incrementing the day counter for the week
                        wc++;

                        if ( wd === swd  && ( days - 1 ) > j ) {

                            $( ".ch-month:last .ch-weeks", this.element )
                                .append( "<div class=\"ch-week\">" + j + "</div>" );

                            // Reset the week day counter
                            wc = 0;
                        }
                    }

                    // Now fill up the last week with blank days
                    for ( wc; wc < 7; wc++ ) {
                        $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                            .append( "<div class=\"ch-day is-outside-month\"></div>" );
                    }
                }

                // Add a legend
                if ( this.settings.legend.show ) {

                    // Add the legend container
                    $( "<div>", {
                        class: "ch-legend"
                    } )
                    .appendTo( this.element )
                    .append( "<small>" + ( this.settings.legend.minLabel || "" ) + "</small>" )
                    .append( "<ul class=\"ch-lvls\"></ul>" )
                    .append( "<small>" + ( this.settings.legend.maxLabel || "" ) + "</small>" );

                    if ( this.settings.legend.align === "left" ) {
                        $( ".ch-legend", this.element ).addClass( "ch-legend-left" );
                    }

                    if ( this.settings.legend.align === "center" ) {
                        $( ".ch-legend", this.element ).addClass( "ch-legend-center" );
                    }

                    // Add the legend steps
                    for ( i = 0; i < binLabels.length; i++ ) {
                        $( "<li>", {
                            "class": "ch-lvl lvl-" + i,
                            "title": binLabels[ i ],
                            "data-toggle": "tooltip"
                        } )
                        .appendTo( $( ".ch-lvls", this.element ) );
                        if ( this.settings.coloring ) {
                            $( ".ch-lvls li:last", this.element  )
                            .addClass( this.settings.coloring + "-" + i );
                        }
                    }
                }

                // Add tooltips to days and steps
                if ( this.settings.tooltips.show && typeof $.fn.tooltip === "function" ) {
//                    $( "[data-toggle=\"tooltip\"]", this.element )
//                    .tooltip( this.settings.tooltips.options );
                    $('#annualCalendar .tooltip').tooltipster({
                               animation: 'fade',
                               delay: 100,
                               contentAsHTML: 'true',
                               trigger: 'hover',
                               side: ['bottom', 'left']
                    });

                }
            },
            updateDates: function( arr ) {
                this.data = arr;
                this.calendarHeatmap();
            },
            appendDates: function( arr ) {
                var toAppend =  this._parse( arr );
                if ( Array.isArray( toAppend ) && Array.isArray( this.data ) ) {
                    for ( var i in toAppend ) {
                        var  idx = this._matchDateIdx( this.data, toAppend[ i ].date );
                        if ( idx > -1 ) {
                            this.data[ idx ].count += toAppend[ i ].count;
                        } else {
                            this.data.push( toAppend[ i ] );
                        }
                    }
                }
                this.calendarHeatmap();
            },
            updateOptions: function( obj ) {
                this.settings = $.extend( true, {}, this.settings, obj );
                this.calendarHeatmap();
            },
            getDates: function( ) {
                return this.data;
            },
            getOptions: function( ) {
                return this.settings;
            }
        } );

        // A really lightweight plugin wrapper around the constructor,
        // preventing against multiple instantiations
        $.fn[ pluginName ] = function( data, options ) {
            var args = arguments;

            // Is the first parameter an object (options), or was omitted,
            // instantiate a new instance of the plugin.
            // if ( data === undefined || typeof data === "object" ) {
            if ( Array.isArray( data ) ) {
                return this.each( function() {

                    // Only allow the plugin to be instantiated once,
                    // so we check that the element has no plugin instantiation yet
                    if ( !$.data( this, "plugin_" + pluginName ) ) {

                        // if it has no instance, create a new one,
                        // pass options to our plugin constructor,
                        // and store the plugin instance
                        // in the elements jQuery data object.
                        $.data( this, "plugin_" + pluginName, new Plugin( this, data, options ) );
                    }
                } );

            // If the first parameter is a string and it doesn't start
            // with an underscore or "contains" the `init`-function,
            // treat this as a call to a public method.
            } else if ( typeof data === "string" && data[ 0 ] !== "_" && data !== "init" ) {

                // Cache the method call
                // to make it possible
                // to return a value
                var returns;

                this.each( function() {
                    var instance = $.data( this, "plugin_" + pluginName );

                    // Tests that there's already a plugin-instance
                    // and checks that the requested public method exists
                    if ( instance instanceof Plugin && typeof instance[ data ] === "function" ) {

                        // Call the method of our plugin instance,
                        // and pass it the supplied arguments.
                        returns = instance[ data ].apply( instance,
                            Array.prototype.slice.call( args, 1 ) );
                    }

                    // Allow instances to be destroyed via the 'destroy' method
                    if ( data === "destroy" ) {
                        $( this ).removeData();
                    }
                } );

                // If the earlier cached method
                // gives a value back return the value,
                // otherwise return this to preserve chainability.
                return returns !== undefined ? returns : this;
            }
        };

} )( jQuery );
