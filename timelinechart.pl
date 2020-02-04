#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;

use POSIX qw(strftime);
use Time::Local qw(timegm);

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
    <script type="text/javascript">';
$html .= "
      google.charts.load('current', {'packages':['timeline']});
      google.charts.setOnLoadCallback(drawChart);
      function drawChart() {
";
$html .= "
        var container = document.getElementById('timeline');
        var chart = new google.visualization.Timeline(container);
        var dataTable = new google.visualization.DataTable();

        dataTable.addColumn({ type: 'string', id: 'Entry' });
        dataTable.addColumn({ type: 'date', id: 'Start' });
        dataTable.addColumn({ type: 'date', id: 'End' });
        dataTable.addRows([
";

my @dates;
while (<IN>) {
  my $line = $_; chomp $line;
  my ($date,$val) = split(",",$line);
  next unless (defined $date);
  next if ($date =~ /Estimate/ || $val =~ /Method/);
  next unless ($date > 1990);
  my $year = $date;
  my $month = 1; my $day = 1;
  # push @dates, "[ new Date($year, $month, $day), $val ]";
 my ($sec,$min,$hour,$tmday,$tmon,$tyear,$wday,$yday,$isdst) =
                                                localtime(time);
  my $y = 1900+$tyear;
  # $DB::single=1;1;#??
  push @dates, "[ '$val', new Date($year, $month, $day), new Date($y, $tmon, $tmday) ]";
}

$html .= join(",\n",@dates);
$html .= "]);\n";


# [ 'Washington', new Date(1789, 3, 30), new Date(1797, 2, 4) ],
# [ 'Adams',      new Date(1797, 2, 4),  new Date(1801, 2, 4) ],
# [ 'Jefferson',  new Date(1801, 2, 4),  new Date(1809, 2, 4) ]]);

#           [ new Date(2012, 3, 13), 37032 ],
#           [ new Date(2012, 3, 14), 38024 ],
#           [ new Date(2012, 3, 15), 38024 ],
#           [ new Date(2012, 3, 16), 38108 ],
#           [ new Date(2012, 3, 17), 38229 ],
#           // Many rows omitted for brevity.
#           [ new Date(2013, 9, 4), 38177 ],
#           [ new Date(2013, 9, 5), 38705 ],
#           [ new Date(2013, 9, 12), 38210 ],
#           [ new Date(2013, 9, 13), 38029 ],
#           [ new Date(2013, 9, 19), 38823 ],
#           [ new Date(2013, 9, 23), 38345 ],
#           [ new Date(2013, 9, 24), 38436 ],
#           [ new Date(2013, 9, 30), 38447 ]

$html .= '        chart.draw(dataTable);
      }
    </script>
  </head>
  <body>
    <div id="timeline" style="width: 1800px; height: 2400px;"></div>
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
