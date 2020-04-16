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

my $inputfile = "full.pdf";
my $dir = "/media/sf_Downloads";
my $debug; my $verbose;
my $api_key = "OyXjxjAoVimqycLz63vLtYk9L";
my $api_secret = "jNNvalfCIlGFgUjdovnKEV2TgiQbGBE8nDqb5ycrGHojHLlPmT";
my $access_token = "635567256-gcRKwmhD5Ds1Xx9AkJeWiNzCDQgssMSsDbfYoRpZ";
my $access_token_secret = "p6xYke2uVuMbBLuaB47nycx6T09nkboAv1142EfVFB1Gb";

my $cmd; my $ret;

GetOptions(
	   'i|input|inputfile:s' => \$inputfile,
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

my $doi; my $keywords;
while(1) {
  $cmd = "find $dir -maxdepth 1 -mindepth 1 -name \"*$inputfile\" | xargs -r ls -t | head -n 1";
  print STDERR "#$cmd\n" if ($verbose);
  $ret = `$cmd`; chomp $ret;
  my $pdffile = $ret;
  if (defined($prev_preprint) && $pdffile ne $prev_preprint) {
    my $txtfile = $pdffile;
    $txtfile =~ s/\.pdf/\.txt/;
    $cmd = "pdftotext $pdffile";
    $ret = `$cmd`; chomp $ret;
    $cmd = "grep doi $txtfile";
    $ret = `$cmd`; chomp $ret;
    $DB::single=1;1;#??
    # Bioinformatics Oupjournals
    if ($ret =~ /Downloaded from https:\/\/academic.oup.com\/bioinformatics\/article-abstract\/doi/) {
      $ret =~ s/Downloaded from https:\/\/academic.oup.com\/bioinformatics\/article-abstract\/doi/#oupjournals #bioinformatics doi\: https:\/\/doi.org\//;
    # GigaScience
    } elsif ($ret =~ /doi\:\ 10\./) {
      $ret =~ s|doi\:\ 10\.|doi\:\ https://doi.org/10\.|;
    }
    $DB::single=1;1;#??
    # biorxiv medrxiv
    if ($ret =~ /(^.+https\:\/\/doi\..+)[\.\n]/) {
      $doi = $1;
      $doi =~ s/preprint/\#preprint/;
      $doi =~ s/The\ copyright.+//;
      $doi =~ s/^(.+\/bioinformatics\/btaa\d+)\/.+/$1/;
    }
    $DB::single=1;1;#??

    # $cmd = "grep -i keyword $txtfile";
    # $ret = `$cmd`; chomp $ret;
    # $DB::single=1;1;#??

    my $pngfile = $txtfile; $pngfile =~ s/\.txt/\.png/;
    $cmd = "cat $txtfile | wordcloud_cli --imagefile $pngfile --stopwords /media/sf_Downloads/stop-words/stop-words-english1.txt 2>/dev/null | csvtk sort -H -k 2:rn | head -n 10 | csvtk cut -f 1";
    print STDERR "#$cmd\n";
    $ret = `$cmd`; chomp $ret;
    my @keywords = split("\n",$ret);
    my $str_keywords;
    foreach my $word (@keywords) {
      $word =~ s/\-/\_/g;
      $word =~ s/\s/\_/g;
      $str_keywords .= "#$word ";
    }

    my $first = $nt->update("$doi $str_keywords");
    $status_id = $first->{id};
    print STDERR "\n[$doi $str_keywords]\n";
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
    next unless (defined($filename) && (-s $filename));

    if (defined($prev_image) && $filename ne $prev_image) {

      my $file_contents = read_file($filename , binmode => ':raw');
      my $media = $nt->update_with_media({in_reply_to_status_id => $status_id, status => "$doi \@albertvilella", media => [undef, $filename, Content_Type => 'image/png', Content => $file_contents]});

      $status_id = $media->{id};
      print STDERR "\n[$status_id]\n";
      $prev_image = $filename;
    }
  }
  print STDERR ".";
  sleep 2;
}

1;
