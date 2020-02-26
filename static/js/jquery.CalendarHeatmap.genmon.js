/*
 *  calendarheatmap - v0.0.3
 *  A simple Calendar Heatmap for jQuery.
 *  https://github.com/SeBassTian23/CalendarHeatmap
 *
 *  Made by Sebastian Kuhlgert
 *  Under MIT License
 */
;( function( $, window, document, undefined ) {

    "use strict";

        // Default Options
        var pluginName = "CalendarHeatmap",
            defaults = {
                title: null,
                months: 12,
                lastMonth: moment().month() + 1,
                lastYear: moment().year(),
                coloring: null,
                labels: {
                    days: false,
                    months: true,
                    custom: {
                        weekDayLabels: null,
                        monthLabels: null
                    }
                },
                legend: {
                    show: true,
                    align: "right",
                    minLabel: "Less",
                    maxLabel: "More"
                },
                tooltips: {
                    show: false,
                    options: {}
                }
            };

        // The actual plugin constructor
        function Plugin ( element, data, options ) {
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

                // Check if the moment.js library is available.
                if ( !moment ) {
                    console.log( "The calendar heatmap plugin requires moment.js" );
                }
            },
            weeksInMonth: function( month, year ) {

                // This function determines, how many weeks there are in the month,
                // to display the right number of columns
                var s = moment()
                    .set( { "year": year, "month": month } )
                    .startOf( "month" )
                    .isoWeek();
                var e = moment()
                    .set( { "year": year, "month": month } )
                    .endOf( "month" )
                    .isoWeek();
                if ( s > e ) {
                    e =  moment()
                    .set( { "year": year, "month": month } )
                    .endOf( "month" ).subtract(7, 'days')
                    .isoWeek()+1;
                }
                return e - s + 1;
            },
            pad: function( str, max ) {
                str = String( str );
                return str.length < max ? this.pad( "0" + str, max ) : str;
            },
            matchDate: function( obj, key ) {
                return $.grep(obj, function(o){ return o.date === key; })[0];
                // return obj.find( function( o ) {
                //    return o.date === key;
                // } );

            },
            calendarHeatmap: function( ) {

                if ( !this.data || $.type( this.data ) !== "array" ) {
                    return;
                }

                var binLabels = [ "1", "2", "3" ];
                var currMonth = this.settings.lastMonth;
                var currYear = this.settings.lastYear;
                var months = this.settings.months;
                var i;

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

                // Add weekday labels
                if ( this.settings.labels.days ) {
                    $( ".ch-year", this.element )
                    .append( "<div class=\"ch-week-labels\"></div>" );

                    $( ".ch-week-labels", this.element )
                    .append( "<div class=\"ch-week-label-col\"></div>" );

                    if ( this.settings.labels.months ) {
                        $( ".ch-week-labels", this.element )
                        .append( "<div class=\"ch-month-label\">&nbsp;</div>" );
                    }

                    $( ".ch-week-label-col", this.element )
                    .append( "<div class=\"ch-day-labels\"></div>" );

                    for ( i = 1; i < 8; i++ ) {
                        var dayName = moment().weekday( i ).format( "ddd" );
                        if ( i % 8 ) {
                            var wdl = this.settings.labels.custom.weekDayLabels;
                            if ( $.type( wdl ) === "array" ) {
                                dayName = wdl[ ( i - 1 ) ] || "";
                            }else if ( $.type( wdl ) === "string" ) {
                                dayName = moment().weekday( i )
                                .format( wdl );
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

                // Start building the months
                for ( i = months; i > 0; i-- ) {

                    var month = currMonth - i;
                    var year = currYear;
                    if ( month < 0 ) {
                        year -= 1;
                        month += 12; // TODO: FIX for more than one year
                    }

                    // Build Month
                    var monthName = moment().set( { "month": month, "year": year } )
                    .format( "MMM" );
                    if ( this.settings.labels.custom.monthLabels ) {
                        if ( $.type( this.settings.labels.custom.monthLabels ) === "array" ) {
                            monthName = this.settings.labels.custom.monthLabels[ month ] || "";
                        }else {
                            monthName = moment().set( { "month": month, "year": year } )
                                .format( this.settings.labels.custom.monthLabels );
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

                    // Add weeks
                    var weeks = this.weeksInMonth( month, year );
                    for ( var j = 0; j < weeks; j++ ) {

                        // Add week
                        $( ".ch-month:last .ch-weeks", this.element )
                            .append( "<div class=\"ch-week\"></div>" );
                        var offset = 0;
                        if ( j === 0 ) {
                            offset = moment().set( { "month":month, "year": year } )
                                .startOf( "month" ).isoWeekday() - 1;
                        }
                        if ( j === weeks - 1 ) {
                            offset = moment().set( { "month":month, "year": year } )
                                .endOf( "month" ).isoWeekday() - 1;
                        }

                        // Add days
                        for ( var k = 0; k < 7; k++ ) {
                            if ( ( offset > k && j === 0 ) || ( offset < k && j === weeks - 1 ) ) {
                                $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                                    .append( "<div class=\"ch-day is-outside-month\"></div>" );
                            }else {
                                var key = year + "-";
                                key += this.pad( ( month + 1 ), 2 ) + "-";
                                key += this.pad( ( ( 7 * j ) + ( k + 1 ) - moment()
                                .set( { "month":month, "year": year } )
                                .startOf( "month" ).isoWeekday() + 1 ), 2 );
                                var obj = this.matchDate( this.data, key );

                                if ( obj !== undefined ) {
                                    $( "<div>", {
                                        "class": "tooltip ch-day lvl-" + obj.count,
                                        "title": '<center><b>'+obj.dateFormatted+'</b></center><small>'+obj.title+'</small>',
                                    } ).appendTo(
                                        $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                                    );

                                    if ( this.settings.coloring ) {
                                        $( ".ch-month:last .ch-weeks .ch-week:last .ch-day:last",
                                        this.element )
                                        .addClass( this.settings.coloring + "-" + obj.count );
                                    }

                                }else {
                                    $( "<div>", {
                                        "class": "ch-day"
                                    } ).appendTo(
                                        $( ".ch-month:last .ch-weeks .ch-week:last", this.element )
                                    );
                                }
                            }
                        }
                    }
                }

                // Add a legend
                if ( this.settings.legend.show ) {

                    // Add the legend container
                    $( "<div>", {
                        class: "ch-legend"
                    } )
                    .appendTo( this.element )
                    .append( "<small>" + this.settings.legend.minLabel + "</small>" )
                    .append( "<ul class=\"ch-lvls\"></ul>" )
                    .append( "<small>" + this.settings.legend.maxLabel + "</small>" );

                    if ( this.settings.legend.align === "left" ) {
                        $( ".ch-legend", this.element ).addClass( "ch-legend-left" );
                    }

                    if ( this.settings.legend.align === "center" ) {
                        $( ".ch-legend", this.element ).addClass( "ch-legend-center" );
                    }

                    // Add the legend steps
                    for ( i = 0; i < 5; i++ ) {
                        $( "<li>", {
                            "class": "ch-lvl lvl-" + i,
                            "title": binLabels[ i ],
                        } )
                        .appendTo( $( ".ch-lvls", this.element ) );
                        if ( this.settings.coloring ) {
                            $( ".ch-lvls li:last", this.element  )
                            .addClass( this.settings.coloring + "-" + i );
                        }
                    }
                }

                // Add tooltips to days and steps
                if ( this.settings.tooltips.show && typeof $.fn.tooltipster === "function" ) {
                    $('#annualCalendar .tooltip').tooltipster({
                               animation: 'fade',
                               delay: 100,
                               contentAsHTML: 'true',
                               trigger: 'hover',
                               side: ['top', 'left']
                    });
                }
            }
        } );

        // A really lightweight plugin wrapper around the constructor,
        // preventing against multiple instantiations
        $.fn[ pluginName ] = function( data, options ) {
            return this.each( function() {
                if ( !$.data( this, "plugin_" + pluginName ) ) {
                    $.data( this, "plugin_" +
                        pluginName, new Plugin( this, data, options ) );
                }
            } );
        };

} )( jQuery, window, document );
