#!/usr/bin/perl
use strict;
use warnings;
use Getopt::Long;

my $inputfile;
my $debug; my $verbose; my $simulate;
my $cmd; my $ret;
my $tag='';
use File::Basename;
# ($name,$path,$suffix) = fileparse($inputfile,@suffixlist);
# $name = fileparse($fullname,@suffixlist);
# $basename = basename($fullname,@suffixlist);
# $dirname  = dirname($fullname);
my $ffmpeg = 'avconv';
my $onlyimages;

GetOptions(
           'i|input|inputfile:s'  => \$inputfile,
           'debug'                => \$debug,
           'onlyimages'                => \$onlyimages,
           'tag:s'                => \$tag,
           'ffmpeg|conv:s'                => \$ffmpeg,
           'verbose'              => \$verbose,
           'simulate'             => \$simulate,
          );

my @suffixlist = ('.pdf');
my ($name,$path,$suffix) = fileparse($inputfile,@suffixlist);

# basename=Illumina.NovaSeq.technical.details.and.implications
# convert -density 400 $basename.pdf $basename.jpg
# $ffmpeg -f image2 -i ${basename}-%d.jpg -y -vf "setpts=500*PTS" $basename.mpg

my $outfile_jpg = "$path$name.jpg";
$cmd = "convert -density 400 $inputfile $outfile_jpg";
print STDERR "# $cmd\n";
$ret = `$cmd`;
exit(0) if ($onlyimages);
my $outfile_mpg = "$path$name.mpg";
$cmd = "$ffmpeg -f image2 -i $path$name\-\%d.jpg -y -vf \"setpts=500*PTS\" $outfile_mpg";
print STDERR "# $cmd\n";
$ret = `$cmd`;

print STDERR "outfile_mpg:\n";
print        "$outfile_mpg\n";

$DB::single=1;1;
$DB::single=1;1;
