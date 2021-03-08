#!/usr/bin/perl
use strict;
use warnings;
use File::Basename;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;

my $inputfile;
my $debug; my $verbose;
my $tag; my $outdir;
GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
           'debug' => \$debug,
           'tag:s' => \$tag,
           'outdir:s' => \$outdir,
          'verbose' => \$verbose,
          );

my $cmd; my $ret;

$tag = 'itab' unless (defined $tag);
my @suffixlist = ('.bam','.cram');
my ($name,$path,$suffix) = fileparse($inputfile,@suffixlist);
$outdir = $path unless (defined $outdir);
my $outfile = "$outdir/$name.$tag.csv";

$cmd = "samtools view $inputfile";

open IN, "$cmd |" or die $!;
open OUT, ">$outfile" or die $!;
print OUT "pos,type,subtype\n";
while (<IN>) {
  my $line = $_; chomp $line;
  my @fields = split("\t",$line);
  my $cigar = $fields[5];
  if ($cigar =~ /(\d+)\=(\d*([DI]))/) {
    my $pos = $1; my $subtype = $2; my $type = $3;
    if (!defined $pos || !defined $type || !defined $subtype) {
      $DB::single=1;1;
    }
    print OUT "$pos,$type,$subtype\n";
  } elsif ($cigar =~ /[DI]/) {
    $cigar =~ s/\=/\,/g; $cigar =~ s/X/\,/g;
    my @entries = split(",",$cigar);
    my $sum;
    foreach my $entry (@entries) {
      if ($entry !~ /[DI]/) {
	$sum += $entry;
      } else {
	if ($entry =~ /(\d*([DI]))/) {
	  my $type = $2; my $subtype = $1;
	  print OUT "$sum,$type,$subtype\n";
	  # $DB::single=1;1;
	}
      }
    }
  } else {
    print OUT "0,0,0\n";
    # $DB::single=1;1;
  }
}
close IN;
close OUT;

$cmd = "csvtk stats $outfile";
print STDERR "#$cmd\n";
print STDERR `$cmd`;

print STDERR "outfile:\n" . (-s $outfile) . "\n";
print "$outfile\n";
