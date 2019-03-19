#!/usr/bin/perl
use strict;
use warnings;
use Getopt::Long;

my $url;
my $debug; my $verbose; my $simulate;
my $cmd; my $ret;
my $self = bless {};

use File::Basename;
# ($name,$path,$suffix) = fileparse($fullname,@suffixlist);
# $name = fileparse($fullname,@suffixlist);
# $basename = basename($fullname,@suffixlist);
# $dirname  = dirname($fullname);
GetOptions(
	   'u|url|i|input|inputfile:s' => \$url,
           'debug' => \$debug,
           'verbose' => \$verbose,
           'simulate' => \$simulate,
          );

my $owner; my $repo;
if ($url =~ /http\w*\:\/\/github\.com\/(\S+)\/(\S+)/) {
  $owner = $1;
  $repo  = $2;
} else {
  die "could not parse $url -- $!";
}

my $main = "/tmp/$owner.$repo.main.url";
my $this_url = "http://github.com/$owner/$repo";
$cmd = "wget -qO- \"$this_url\" > $main";
print STDERR "# $cmd\n";
$ret = `$cmd`;

open MAIN,"$main" or die $!;
my $watchers = 0;
my $starred  = 0;
my $forked   = 0;
while (<MAIN>) {
  my $line = $_; chomp $line;
  if ($line =~ /(\d+) users are watching this repository/) {
    $watchers = $1;
  } elsif ($line =~ /(\d+) users starred this repository/) {
    $starred = $1;
  } elsif ($line =~ /(\d+) users forked this repository/) {
    $forked = $1;
  }
}
close MAIN;

# cat /tmp/$i.url  | perl -lne 'print $1 if /(\d+) users are watching this repository/' | tosheets -u -c L$i -s Software --spreadsheet=$id
# cat /tmp/$i.url | perl -lne 'print $1 if /(\d+) users starred this repository/' | tosheets -u -c M$i -s Software --spreadsheet=$id
# cat /tmp/$i.url | perl -lne 'print $1 if /(\d+) users forked this repository/'

# Search languages
my $tag = "search?l=python";
my $search = "http://github.com/$owner/$repo/$tag";
my $lang = "/tmp/$owner.$repo.lang.url";
$cmd = "wget -qO- \"$search\" > $lang";
print STDERR "# $cmd\n";
$ret = `$cmd`;
$cmd = "html2text $lang | grep -A100 '\*\*\ Languages'";
print STDERR "# $cmd\n";
open LANG, "$cmd |" or die $!;
my @langs;
while (<LANG>) {
  my $line = $_; chomp $line;
  next if ($line =~ /\*\*\ Languages/);
  print STDERR "$line\n";
  last if ($line =~ /Language\ \[One/);
  if ($line =~ /\_(\w+)/) {
    $DB::single=1;1;
    push @langs, $1;
  }
}
close LANG;
print "$watchers,$starred,$forked,". join(";",@langs) . "\n";
$DB::single=1;1;#??
$DB::single=1;1;
