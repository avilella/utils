#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;

my $inputfile;
my $debug; my $verbose;
GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
           'debug' => \$debug,
          'verbose' => \$verbose,
          );

open IN, $inputfile or die $!;
my $html = '
<html>
  <head>
    <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
    <script type="text/javascript">
      google.charts.load("current", {packages:["calendar"]});
      google.charts.setOnLoadCallback(drawChart);

   function drawChart() {
       var dataTable = new google.visualization.DataTable();
';
$html .= "
       dataTable.addColumn({ type: 'date', id: 'Date' });
       dataTable.addColumn({ type: 'number', id: 'Volume' });
";
$html .= '
       dataTable.addRows([
';

my @dates;
while (<IN>) {
  my $line = $_; chomp $line;
  my ($date,$volume) = split(",",$line);
  next unless (defined $date);
  next if ($date =~ /date/);
  next unless ($volume > 0);
  my ($day, $month, $year) = split('/',$date);
  push @dates, "[ new Date($year, $month, $day), $volume ]";
}

$html .= join(",\n",@dates);

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
$html .= "
        ]);

       var chart = new google.visualization.Calendar(document.getElementById('calendar_basic'));

       var options = {
";
$html .= '
         title: "Yogurt production",
         height: 350,
       };

       chart.draw(dataTable, options);
   }
    </script>
  </head>
  <body>
    <div id="calendar_basic" style="width: 1000px; height: 350px;"></div>
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
