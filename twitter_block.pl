#!/usr/bin/perl
use strict;
use warnings;
use File::Basename;

# Open a terminal window and type:
# while true; do clear; xdotool getmouselocation --shell; sleep 0.2; done

# Read the X and Y coordinates to determine the $start value below
# depending on the size of the window

use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;

my $inputfile;
my $debug; my $verbose;
my $type = 'main';
my $min = 20;

GetOptions(
	   'min:s' => \$min,
	   'i|input|inputfile:s' => \$inputfile,
           'type:s' => \$type,
           'debug' => \$debug,
          'verbose' => \$verbose,
          );

my $count = 1;
my @users = ("omicsomicsblog","XLR","sbarnettARK");

do {
  foreach my $user (@users) {
    `xte 'mousemove 383 105'`; sleep 0.2;
    `xte 'mouseclick 1'`; sleep 0.1; `xte 'mouseclick 1'`; sleep 0.5;
    my $string = "twitter.com/$user";
    `xte 'keydown Control_L'`;sleep 0.2;
    `xte 'str a'`; sleep 0.5;
    `xte 'keyup Control_L'`;sleep 0.2;
    `xte 'str $string'`; sleep 1.0;
    `xte 'key Return'`; sleep $min;
    # First
    `xte 'mousemove 577 408'`; sleep 0.2;
    `xte 'mouseclick 1'`; sleep 3;
    `xte 'key Down'`; sleep 2;
    `xte 'key Down'`; sleep 2;
    `xte 'key Down'`; sleep 2;
    `xte 'key Down'`; sleep 2;
    `xte 'key Down'`; sleep 2;
    `xte 'key Down'`; sleep 2;
    `xte 'key Return'`; sleep 2;
    `xte 'key Return'`; sleep 2;
  }
  foreach my $user (@users) {
    `xte 'mousemove 383 105'`; sleep 0.2;
    `xte 'mouseclick 1'`; sleep 0.1; `xte 'mouseclick 1'`; sleep 0.5;
    my $string = "twitter.com/$user";
    `xte 'keydown Control_L'`;sleep 0.2;
    `xte 'str a'`; sleep 0.5;
    `xte 'keyup Control_L'`;sleep 0.2;
    `xte 'str $string'`; sleep 1.0;
    `xte 'key Return'`; sleep $min;
    `xte 'mousemove 671 407'`; sleep 0.2;
    `xte 'mouseclick 1'`; sleep 1.7;
    `xte 'mousemove 418 494'`; sleep 0.2;
    `xte 'mouseclick 1'`; sleep 1.7;
  }
  sleep 1800;
} while (1);
