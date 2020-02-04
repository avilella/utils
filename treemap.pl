#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;

use POSIX qw(strftime);
use Time::Local qw(timegm);
use Scalar::Util 'looks_like_number';

my $inputfile;
my $debug; my $verbose;
my $datefmt = 'DMY';
my $split = '/';
my $log;

GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
           'debug' => \$debug,
           'split:s' => \$split,
           'log' => \$log,
           'datefmt:s' => \$datefmt,
          'verbose' => \$verbose,
          );

open IN, $inputfile or die $!;

my $html = '
<html>
  <head>
    <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
    <script type="text/javascript">
';
$html .= "
      google.charts.load('current', {'packages':['treemap']});
      google.charts.setOnLoadCallback(drawChart);
      function drawChart() {
        var data = google.visualization.arrayToDataTable([
";



my @dates;
my $count = 1;

my $parents;
while (<IN>) {
  my $line = $_; chomp $line;
  my ($val1,$val2,$val3) = split(",",$line);
  # $DB::single=1;1;#??
  $val2 =~ s/\"//g;
  $val3 =~ s/\"//g;
  $val2 =~ s/\,//g;
  $val3 =~ s/\,//g;
  my $parent = "'Global'";
  if ($count == 1) {
    $parent = "Parent";
  } else {
    if ($val1 =~ /^(\w+)\s+/) {
      $parent = $1;
      if (!defined $parents->{$parent}) {
	push @dates, "['$parent','Global', 0, 0]";
      }
      $parents->{$parent} = $parent;
    }
  }
  push @dates, "['Global',null, 0, 0]" if ($count == 2);
  $val2 = sprintf("%d",$val2) if (looks_like_number($val2));
  $val3 = sprintf("%d",$val3) if (looks_like_number($val3));
  push @dates, "['$val1', '$parent', $val2, $val3]" if ($count != 1);
  push @dates, "['$val1', '$parent', '$val2', '$val3']" if ($count == 1);
  $count++;
}
$DB::single=1;1;#??

$html .= join(",\n",@dates);

          # ['Location', 'Parent', 'Market trade volume (size)', 'Market increase/decrease (color)'],
          # ['Global',    null,                 0,                               0],
          # ['America',   'Global',             0,                               0],
          # ['Europe',    'Global',             0,                               0],

$html .= "
        ]);

        tree = new google.visualization.TreeMap(document.getElementById('chart_div'));

        tree.draw(data, {
          minColor: '#f00',
          midColor: '#ddd',
          maxColor: '#0d0',
          headerHeight: 15,
          fontColor: 'black',
          showScale: true
        });
";
$html .= '
      }
    </script>
  </head>
  <body>
    <div id="chart_div" style="width: 900px; height: 500px;"></div>
  </body>
</html>
';

my $outfile = "$inputfile.html";
open OUT, ">$outfile" or die $!;
print OUT $html;
close OUT;
print STDERR "outfile:\n" . (-s $outfile) . "\n";
print "$outfile\n";
$DB::single=1;1;#??
$DB::single=1;1;#??

#   <html>
#     <head>
#       <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
#       <script type="text/javascript">
#         google.charts.load('current', {'packages':['treemap']});
#         google.charts.setOnLoadCallback(drawChart);
#         function drawChart() {
#           var data = google.visualization.arrayToDataTable([
#             ['Location', 'Parent', 'Market trade volume (size)', 'Market increase/decrease (color)'],
#             ['Global',    null,                 0,                               0],
#             ['America',   'Global',             0,                               0],
#             ['Europe',    'Global',             0,                               0],
#             ['Asia',      'Global',             0,                               0],
#             ['Australia', 'Global',             0,                               0],
#             ['Africa',    'Global',             0,                               0],
#             ['Brazil',    'America',            11,                              10],
#             ['USA',       'America',            52,                              31],
#             ['Mexico',    'America',            24,                              12],
#             ['Canada',    'America',            16,                              -23],
#             ['France',    'Europe',             42,                              -11],
#             ['Germany',   'Europe',             31,                              -2],
#             ['Sweden',    'Europe',             22,                              -13],
#             ['Italy',     'Europe',             17,                              4],
#             ['UK',        'Europe',             21,                              -5],
#             ['China',     'Asia',               36,                              4],
#             ['Japan',     'Asia',               20,                              -12],
#             ['India',     'Asia',               40,                              63],
#             ['Laos',      'Asia',               4,                               34],
#             ['Mongolia',  'Asia',               1,                               -5],
#             ['Israel',    'Asia',               12,                              24],
#             ['Iran',      'Asia',               18,                              13],
#             ['Pakistan',  'Asia',               11,                              -52],
#             ['Egypt',     'Africa',             21,                              0],
#             ['S. Africa', 'Africa',             30,                              43],
#             ['Sudan',     'Africa',             12,                              2],
#             ['Congo',     'Africa',             10,                              12],
#             ['Zaire',     'Africa',             8,                               10]
#           ]);
#   
#           tree = new google.visualization.TreeMap(document.getElementById('chart_div'));
#   
#           tree.draw(data, {
#             minColor: '#f00',
#             midColor: '#ddd',
#             maxColor: '#0d0',
#             headerHeight: 15,
#             fontColor: 'black',
#             showScale: true
#           });
#   
#         }
#       </script>
#     </head>
#     <body>
#       <div id="chart_div" style="width: 900px; height: 500px;"></div>
#     </body>
#   </html>
