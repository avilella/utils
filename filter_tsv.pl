#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;
use File::Basename;

my $inputfile;
my $debug; my $verbose;
my $tag;
my $outdir;
my $stdout;
GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
           'debug' => \$debug,
           'o|outdir:s' => \$outdir,
           't|tag:s' => \$tag,
          'verbose' => \$verbose,
          'stdout' => \$stdout,
          );

my $cmd; my $ret;

$tag = 'filt' unless (defined $tag);
my @suffixlist = ('.tsv','.tab');
my ($name,$path,$suffix) = fileparse($inputfile,@suffixlist);
$outdir = $path unless (defined $outdir);
my $outfile = "$outdir/$name.$tag.tsv";

$cmd = "cat $inputfile " . q{ | sed 's/\r//g' | csvtk transpose -t -I | csvtk transpose -t } . " > $outfile";
print STDERR "# $cmd\n";
$ret = `$cmd`;

print STDERR "outfile:\n" . (-s $outfile) . "\n";
print "$outfile\n"   unless ($stdout);
print `cat $outfile` if     ($stdout);

1;
