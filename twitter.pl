#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3 'open3'; $SIG{CHLD} = 'IGNORE';
use Symbol 'gensym';
use Getopt::Long;
use Net::Twitter;
# use lib "$ENV{HOME}/perl5/lib/perl5";
# use Twitter::API;
use File::Slurp;
use MIME::Base64;
use Data::Dumper;

#curl -v --compressed -uavilella@gmail.com:t-fifty50 "https://gnip-api.twitter.com/search/30day/accounts/<account-name>/prod/counts.json?query=from%3Atwitterdev"

my $inputfile = "full.pdf:github.pdf:_Article_*.pdf";
my $dir = "/media/sf_Downloads";
my $debug; my $verbose;
my $api_key = "OyXjxjAoVimqycLz63vLtYk9L";
my $api_secret = "jNNvalfCIlGFgUjdovnKEV2TgiQbGBE8nDqb5ycrGHojHLlPmT";
my $access_token = "635567256-gcRKwmhD5Ds1Xx9AkJeWiNzCDQgssMSsDbfYoRpZ";
my $access_token_secret = "p6xYke2uVuMbBLuaB47nycx6T09nkboAv1142EfVFB1Gb";

my $cmd; my $ret;
my $previous;

GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
	   'p|previous:s' => \$previous,
	   'd|dir:s' => \$dir,
           'debug' => \$debug,
          'verbose' => \$verbose,
          );

my $nt = Net::Twitter->new(
    ssl      => 1,
    traits   => [qw/API::RESTv1_1/],
    consumer_key        => $api_key,
    consumer_secret     => $api_secret,
    access_token        => $access_token,
    access_token_secret => $access_token_secret,
    );

# my $nt = Twitter::API->new_with_traits(
#     ssl      => 1,
#     traits   => 'Enchilada',
#     consumer_key        => $api_key,
#     consumer_secret     => $api_secret,
#     access_token        => $access_token,
#     access_token_secret => $access_token_secret,
#     );

my $prev_preprint = 1;
my $prev_image    = 1;
my $status_id;

my $image_count = 0;
my $has_doi_shot = 0;

my $doi; my $keywords;
my @inputs = split(":",$inputfile);
my $first = shift @inputs;
my $search = "-name \"*$first\"";
foreach my $input (@inputs) {
  $search .= " -or -name \"*$input\"";
}
while(1) {
  $cmd = "find $dir -maxdepth 1 -mindepth 1 $search | xargs -r ls -t | head -n 1";
  print STDERR "#$cmd\n" if ($verbose);
  $ret = `$cmd`; chomp $ret;
  my $pdffile = $ret;
  $cmd = 'stat -c %y ' . $pdffile;
  # print STDERR "#$cmd\n";
  $ret = `$cmd`; chomp $ret;
  my $pdftimestamp = $ret;
  if (defined($prev_preprint) && $pdffile ne $prev_preprint) {
    my $txtfile = $pdffile;
    $txtfile =~ s/\.pdf/\.txt/i;
    $cmd = "pdftotext $pdffile";
    $ret = `$cmd`; chomp $ret;
    $cmd = "grep doi $txtfile";
    $ret = `$cmd`; chomp $ret;

    my $str_keywords = '';

    # github page
    if ($txtfile =~ /github/) {
      $cmd = "head -n 4 $txtfile";
      print STDERR "#$cmd\n";
      $ret = `$cmd`; chomp $ret;
      my @lines = split("\n",$ret);
      $doi = "http://github.com/" . $lines[0];
      $doi =~ s/\ //g;
      $lines[3] =~ s/\-/\_/g;
      $doi .= " - " . $lines[3];
      $doi =~ s/\#\ /\#/g;
      $doi .= " - " . $lines[2];
      $DB::single=1;1;#??
      $str_keywords = '';
    } elsif ($txtfile =~ /\_Article\_\d+/) {
      # Nature Comms
      $cmd = "grep 'NATURE COMMUNICATIONS' $txtfile | head -n 1";
      print STDERR "#$cmd\n";
      $ret = `$cmd`; chomp $ret;
      $doi = $ret;
    } else {

      # $DB::single=1;1;
      # Bioinformatics Oupjournals
      if ($ret =~ /Downloaded from https:\/\/academic.oup.com\/bioinformatics\/article-abstract\/doi/) {
	$ret =~ s/Downloaded from https:\/\/academic.oup.com\/bioinformatics\/article-abstract\/doi/#oupjournals #bioinformatics doi\: https:\/\/doi.org\//;
	# GigaScience
      } elsif ($ret =~ /doi\:\ 10\./) {
	$ret =~ s|doi\:\ 10\.|doi\:\ https://doi.org/10\.|;
      }
      # $DB::single=1;1;
      # biorxiv medrxiv
      if ($ret =~ /(^.+https\:\/\/doi\..+)[\.\n]/) {
	$doi = $1;
	$doi =~ s/preprint/\#preprint/;
	$doi =~ s/The\ copyright.+//;
	$doi =~ s/^(.+\/bioinformatics\/btaa\d+)\/.+/$1/;
      }
      # $DB::single=1;1;#??
      
      $cmd = "grep -A1 -i -e keyword -e 'key word' $txtfile";
      $ret = `$cmd`; chomp $ret; $ret =~ s/key words\:|keyword[s]\:\s+//i;
      chomp $ret;
      my @keyw = split(/\,|\;/,$ret);
      # $DB::single=1;1;
      
      my $pngfile = $txtfile; $pngfile =~ s/\.txt/\.png/;
      $cmd = "cat $txtfile | python3 /usr/local/bin/wordcloud_cli --imagefile $pngfile --stopwords $ENV{HOME}/utils/stop-words-twitter.txt 2>/dev/null | csvtk sort -H -k 2:rn 2>/dev/null | head -n 10 | csvtk cut -f 1 2>/dev/null";
      print STDERR "#$cmd\n";
      $ret = `$cmd`; chomp $ret;
      my @keywords = split("\n",$ret);
      $str_keywords = '';
      foreach my $word (@keywords,@keyw) {
	$word =~ s/^\s+//;
	$word =~ s/\-/\_/g;
	$word =~ s/\s/\_/g;

	my $tword = qr{ \w [\w'-]* }x;
	my $tnonword = qr{ [^\w'-]+ }x;
	$word =~ s{
		    \b
		    ($tword)
		    (?: $tnonword \1 )+
		    (?! \w )  # UPDATE
		}{$1}xg;
	$str_keywords .= "#$word ";
      }
      # Arxiv
      # $DB::single=1;1;#??
      if (!defined $doi) {
	$cmd = "grep -i arxiv $txtfile";
	print STDERR "#$cmd\n";
	$ret = `$cmd`; chomp $ret;
	$doi = "."; $doi .= $ret; $doi =~ s/\n/\ \|\ /g;
	$doi =~ s/arXiv\:(\d+)/https\:\/\/arxiv\.org\/abs\/$1/;
	$doi =~ s/\.http/http/;
	$doi = undef if $doi eq '.';
      }

      # Mobile Tweet saved as pdf
      if (!defined $doi) {
	$cmd = "grep -e '\@' -e http $txtfile";
	print STDERR "#$cmd\n";
	$ret = `$cmd`; chomp $ret;
	$doi = "."; $doi .= $ret; $doi =~ s/\n/\ \|\ /g;
	$doi =~ s/\s+\w+\@\w+\.\w+\s+/\ /g;
	$doi =~ s/\s+\w+\.\w+\@\w+\.\w+\s+/\ /g;
	$doi =~ s/\.\w+\@\w+\.\w+\s+/\ /g;
	$doi =~ s/\.\w+\@\w+\.\w+\.\w+\s+/\ /g;
	$doi =~ s/Correspondence\://;
	print STDERR "[$doi]";
      }
    }

    my $compose = "$doi $str_keywords";
    if (length($compose) > 240) {
      print STDERR "# Shorten:\n";
      $compose =~ s/^(.{140}).*/$1/;
    }
    print STDERR "\n[$compose]\n";
    my $first = $nt->update("$compose");
    $image_count = 0;
    $status_id = $first->{id};
    print STDERR "\n[$pdffile $status_id]\n";
    $prev_preprint = $pdffile;
    print STDERR ".";

    # my $file_contents = read_file($pngfile , binmode => ':raw');
    # my $media = $nt->update_with_media({in_reply_to_status_id => $status_id, status => "$doi \@albertvilella", media => [undef, $pngfile, Content_Type => 'image/png', Content => $file_contents]});

    # $status_id = $media->{id};
    # print STDERR "\n[$status_id]\n";
    # $prev_image = $pngfile;

    sleep 10;

  } else {

    $cmd = "find $dir -name \"Screenshot_????????_??????.png\" | xargs -r ls -t 2>/dev/null | head -n 1";
    print STDERR "#$cmd\n" if ($verbose);
    $ret = `$cmd`; chomp $ret;
    my $filename = $ret;

    $cmd = 'stat -c %y ' . $filename;
    # print STDERR "#$cmd\n";
    $ret = `$cmd`; chomp $ret;
    my $shottimestamp = $ret;
    my @x = sort($pdftimestamp,$shottimestamp);
    if ($x[0] eq $pdftimestamp) {
      $DB::single=1;1;#??
    }
    next unless (defined($filename) && (-s $filename));

    $cmd = "gocr -i $filename | tail -n 1 | grep '^doi\:'";
    # print STDERR "#$cmd\n";
    eval { $ret = `$cmd` ; }; chomp $ret;
    my $grepshot = $ret;
    if ($grepshot =~ /^doi\:/ && $image_count > 0 && 1 == $has_doi_shot) {
      # this is the first image of a pdf we haven't analysed yet, so skip
      # $prev_image = $filename;
      next;
    }

    if (defined($prev_image) && $filename ne $prev_image) {

      my $file_contents = read_file($filename , binmode => ':raw');
      if (length($doi) > 240) {
	print STDERR "# Shorten:\n";
	$doi =~ s/^(.{140}).*/$1/;
      }
      my $media = $nt->update_with_media({in_reply_to_status_id => $status_id, status => "$doi \@albertvilella", media => [undef, $filename, Content_Type => 'image/png', Content => $file_contents]});

      $status_id = $media->{id};
      $has_doi_shot = 1 if ($grepshot =~ /^doi\:/);
      $image_count++;
      print STDERR "\n[$status_id]\n";
      $prev_image = $filename;
    }
  }
  print STDERR ".";
  sleep 2;
}

$DB::single=1;1;#??

1;
