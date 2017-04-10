#!/usr/bin/perl
use strict;
use warnings;
use Getopt::Long;

my $user;
my $debug; my $verbose; my $simulate;
my $cmd; my $ret;
use File::Basename;
# ($name,$path,$suffix) = fileparse($fullname,@suffixlist);
# $name = fileparse($fullname,@suffixlist);
# $basename = basename($fullname,@suffixlist);
# $dirname  = dirname($fullname);

$user = 'epigen_papers';

GetOptions(
	   'i|input|user:s' => \$user,
           'debug' => \$debug,
           'verbose' => \$verbose,
           'simulate' => \$simulate,
          );

$cmd = "lynx -dump http://twitter.com/$user | grep -i \"$user/status/\" " . q{ | awk '{print $2}' };
print STDERR "# $cmd\n";
$ret = `$cmd`; chomp $ret;
my @entries = split("\n",$ret);
foreach my $entry (@entries) {
  my $tweet = 'NA';
  print "$entry\n";
  $cmd = "lynx -dump $entry";
print STDERR "# $cmd\n";
$ret = `$cmd`; $ret =~ s/\n/\ /g;
  $ret =~ /(Twitter\:.+)\[\d+\]alternate \[\d+\]alternate/;
  if (defined $1) {
    $DB::single=1;1;
    $tweet = $1;
  } else {
    next;
  }
  print "$tweet\n";
}

$DB::single=1;1;
$DB::single=1;1;
