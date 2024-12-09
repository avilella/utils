#!/usr/bin/perl
use strict;
use warnings;

sleep 3;
use Getopt::Long;
my $debug; my $verbose;
my $num = 4;
my $multiplier = 1;

GetOptions(
	   'm:s' => \$multiplier,
	   'n:s' => \$num,
           'debug' => \$debug,
          'verbose' => \$verbose,
          );

do {
#    `xte 'mousemove 807 96'`; sleep 0.2;
#    `xte 'mouseclick 1'`;
#    sleep 10;
#    `xte 'mousemove 1308 191'`; sleep 0.2;
#    `xte 'mouseclick 1'`;
#    sleep 3;
#    `xte 'key Tab'`; sleep 0.25;
#    `xte 'key Tab'`; sleep 0.25;
#    `xte 'key Tab'`; sleep 0.5;
#    `xte 'key Spacebar'`; sleep 2;
    unless ($debug) {
	foreach my $iter (1..$num) {
	    `xte 'key Tab'`; sleep (0.25*$multiplier);
	    `xte 'key Tab'`; sleep (0.25*$multiplier);
	    `xte 'key Tab'`; sleep (0.5*$multiplier);
	    `xte 'key Space'`; sleep (1.5*$multiplier);
	}
    }
    `xte 'key Page_Down'`; sleep (1*$multiplier);
} while (1);
