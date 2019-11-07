#!/usr/bin/perl -w
#
# TheThingsNetwork HTTP integration for letter box sensor
# - receives payload via POST from TTN
# - serves a small web page with status of letter box sensor(s)
#   - directly called CGI
#   - included with SSI
#
# Initial:
# (P) & (C) 2019-2019 Alexander Hierle <alex@hierle.com>
#
# Major extensions:
# (P) & (C) 2019-2019 Dr. Peter Bieringer <pb@bieringer.de>
#
# License: GPLv3
#
# Authors:  Alexander Hierle (hie)
#           Dr. Peter Bieringer (bie)
#
#
# Compatibility of letterbox-sensor
#   - supports version 1 sending "full" / "empty"
#   - supports planned future version sending also "emptied" / "filled"
#
# Installation
#   - store CGI into cgi-bin directory
#   - optionally: include CGI in SSI enabled webpage using
#       <!--#include virtual="cgi-bin/ttn-letterbox.cgi" -->
#
# Configuration (optional overwritten by config file <DOCUMENT_ROOT>/../conf/ttn-letterbox.conf)
#   - datadir=<by CGI user writable directory>:
#     - default: <DOCUMENT_ROOT>/ttn
#   - autoregister=<value>
#     - default: 0 (do not autoregister devices)
#     - 1 (autoregister devices)
#   - debug=<value>
#     - default: 0 (no debug)
#   - threshold.<dev_id>=<value>
#     - default: received in JSON from sensor
#   - delta.warn=<minutes>
#     - default: 45
#   - delta.crit=<minutes>
#     - default: 90
#
# Access control
#   - CGI honors for POST requests X-TTN-AUTH header which can be configured manually on TTN controller side
#     - on device autoregistration, password will be also stored in device list, allowed chars: [:alnum:]\.\-\+%
#     - in case device is already registered without password, watch for hint in log
#   - GET requests are currently NOT protected
#
# Logging
#   - warnings/errors will be logged to web server error log using "print STDERR"
#
#
# Persistent data storage for log & status
#   - it is strongly recommended to store the persistent data outside pub directory (see configuration above)
#
# File: ttn.devices.list
# Contents: <dev_id>:<hardware_serial>:<salted encrpyted password>
# Purpose: (auto)store seen devices, add seen password on registration
#
# File: ttn.<dev_id>.%Y%m%d.raw.log
# Contents: <TIMESTAMP> <raw data received from TTN>
# Purpose: log all received data
#
# File: ttn.<dev_id>.%Y%m%d.raw.status
# Contents: <TIMESTAMP> <raw data received from TTN>
# Purpose: last received data
#
# File: ttn.<dev_id>.%Y%m%d.filled.status
# Contents: <TIMESTAMP>
# Purpose: time of last detected (received/autodetected) filled status
#
# File: ttn.<dev_id>.%Y%m%d.emptied.status
# Contents: <TIMESTAMP>
# Purpose: time of last detected (received/autodetected) emptied status
#
#
# Changelog:
# 20191007/hie: initial
# 20191029/bie: major extension, improve output, add support for additional sensors, add some error catching
# 20191030/bie: add full/empty status support
# 20191031/bie: add filled/empty support (directly [future usage] and indirectly)
# 20191101/bie: add optional password protection capability for POST request, add support for config file
# 20191104/bie: add deltaLastChanged and threshold per dev_id in config, change color in case lastReceived is above limits
# 20191107/bie: fix+improve delta time calc+display
#
# TODO:
# - lock around file writes
# - safety check on config file value parsing
# - ability to run in tainted mode

# simple ttn http integration
use English;
use strict;
use warnings;
use CGI;
use POSIX qw(strftime);
use JSON;
use Date::Parse;
use Crypt::SaltedHash;

# prototyping
sub response($$;$$);
sub letter($);
sub logging($);
sub deltatime_string($);

# global config (can be overwritten/extended by config file)
my %config = (
  'autoregister'  => 0,     # autoregister devices
  'autorefresh'   => 900,   # (seconds) of HTML autorefreshing
  'delta.warn'    => 45,    # (minutes) when color of deltaLastReceived turns orange
  'delta.crit'    => 75,    # (minutes) when color of deltaLastReceived turns red
  'debug'         => 0      # debug
);

# name of program
my $program = "ttn-letterbox.cgi";

# set time strings
my $nowstr = strftime "%Y-%m-%dT%H:%M:%SZ", gmtime(time);
my $today = strftime "%Y%m%d", gmtime(time);

# defines from environment
my $reqm = $ENV{'REQUEST_METHOD'};

####################
## basic error check
####################

my $datadir;
my $confdir;

# default
if (!defined $ENV{'DOCUMENT_ROOT'}) {
  response(500, "major problem found", "", "'DOCUMENT_ROOT' not defined in environment");
  exit;
};
$datadir = $ENV{'DOCUMENT_ROOT'} . "/ttn"; # default
$confdir = $ENV{'DOCUMENT_ROOT'} . "/../conf"; # default

# read optional config
my $conffile = "$confdir/ttn-letterbox.conf";

if (-e $conffile) {
  if (! -r $conffile) {
    response(500, "major problem found", "", "config file exists but not readable: $conffile");
    exit;
  };
  # read key value
  open CONFF, '<', $conffile or die;
  while (my $line = <CONFF>) {
    chomp($line);
    if ($line =~ /^([A-Za-z0-9-\.]+)=(.*)$/o) {
      $config{$1} = $2;
    };
  };
  close CONFF;
  if (defined $config{'debug'} && $config{'debug'} > 0) {
    for my $key (sort keys %config) {
      logging("config: " . $key . "=" . $config{$key});
    };
  };
};

# print environment to error log
if (defined $config{'debug'} && $config{'debug'} ne "0") {
  for my $env (sort keys %ENV) {
    logging("CGI environment: " . $env . "=" . $ENV{$env});
  };
};

# owerwrite datadir
if (defined $config{'datadir'}) {
  $datadir = $config{'datadir'};
};

if (! -e $datadir) {
  response(500, "major problem found", "", "datadir not existing: $datadir");
  exit;
};

if (! -r $datadir) {
  response(500, "major problem found", "", "datadir not readable: $datadir");
  exit;
};

if (! -w $datadir) {
  response(500, "major problem found", "", "datadir not writable: $datadir");
  exit;
};


if (! defined $reqm) {
  response(500, "major problem found", "", "REQUEST_METHOD not defined");
  exit;
};


## background colors
my %bg_colors = (
  'full'    => 'lightgreen',
  'empty'   => 'lightgrey',
  'filled'  => 'yellow',
  'emptied' => 'pink',
);

# list of seen devices
my $devfile =  "$datadir/ttn.devices.list";

# filetemplates per DEV_ID
my $rawfile_template =  "$datadir/ttn.DEV_ID.$today.raw.log";
my $lastfile_template = "$datadir/ttn.DEV_ID.last.raw.status";
my $filledfile_template = "$datadir/ttn.DEV_ID.filled.time.status";
my $emptiedfile_template = "$datadir/ttn.DEV_ID.emptied.time.status";

# list and order of info rows in output
my @info_array = ('timeNow', 'deltaLastChanged', 'deltaLastReceived', 'timeLastReceived', 'timeFilled', 'timeEmptied', 'sensor', 'threshold', 'tempC', 'voltage', 'rssi', 'snr', 'counter', 'hardwareSerial');

# definitions
my %dev_hash;


###########
## START ##
###########


## handle web request
if (defined $reqm && $reqm eq "POST") { # POST data
  # receive POST data
  my @lines;
  while (<STDIN>) {
    push @lines, $_;
  };

  # check contents
  if (scalar(@lines) > 1) {
    response(500, "too many lines received via POST request");
    exit;
  };

  # decode JSON
  my $content = eval{ decode_json($lines[0])};
  if ($@) {
    response(500, "unsupported POST data", "", "POST request does not contain valid JSON contents");
    exit;
  };

  # extract & check dev_id
  my $dev_id = $content->{'dev_id'};
  if (! defined $dev_id) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'dev_id' not found");
    exit;
  };
  if ($dev_id !~ /^([a-zA-Z0-9-]+)$/o) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'dev_id' contains illegal chars");
    exit;
  };

  # extract & check hardware_serial
  my $hardware_serial = $content->{'hardware_serial'};
  if (! defined $hardware_serial) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'hardware_serial' not found");
    exit;
  };
  if ($hardware_serial !~ /^([A-F0-9-]{16})$/o) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'hardware_serial' contains illegal chars/improper length");
    exit;
  };

  # get optional auth header
  my $auth;
  if (defined $ENV{'HTTP_X_TTN_AUTH'}) {
    # check for illegal chars
    if ($ENV{'HTTP_X_TTN_AUTH'} !~ /^([[:alnum:]\.\-\+%]+)$/o) {
      response(500, "unsupported HTTP_X_TTN_AUTH header content", "", "HTTP_X_TTN_AUTH header contains illegal chars");
      exit;
    } else {
      $auth = $1;
    };
  };

  # check for dev_id/hardware_serial in file
  my $found = 0;
  if (-e $devfile) {
    open DEVF, '<', $devfile or die;
    while (my $line = <DEVF>) {
      chomp($line);
      if ($line !~ /^([^:]+):([^:]+)(:.*)?$/o) {
        next;
      };
      if (defined $1 && $1 eq $dev_id) {
        # dev_id found
        if (defined $2 && $2 eq $hardware_serial) {
          if (defined $auth && defined $3) {
            # password defined and  given
            if (Crypt::SaltedHash->validate($3, $auth)) {
              # password defined and given and match
              $found = 1;
              last;
            } else {
              response(403, "access denied", "", "POST request does contain valid JSON, dev_id=$dev_id/hardware_serial=$hardware_serial matching but required password is not matching");
              exit;
            };
          } elsif (defined $3) {
            # password defined but not given
            response(403, "access denied", "", "POST request does contain valid JSON, dev_id=$dev_id/hardware_serial=$hardware_serial matching but no required password given");
            exit;
          } elsif (defined $auth) {
            # password given but not defined
            my $csh = Crypt::SaltedHash->new(algorithm => 'SHA-512');
            $csh->add($auth);
            logging("request received with password, strongly recommend to replace entry in $devfile with $dev_id:$hardware_serial:" . $csh->generate);
            $found = 1;
            last;
          } else {
            # password neither given nor defined
            $found = 1;
            last;
          };
        } else {
          response(403, "access denied", "", "POST request does contain valid JSON but dev_id=$dev_id/hardware_serial=$hardware_serial is not matching known one");
          exit;
        };
      };
    };
    close DEVF;
  } else {
    if (defined $config{'autoregister'} && $config{'autoregister'} ne "1") {
      response(403, "access denied", "", "POST request does contain valid JSON with dev_id=$dev_id/hardware_serial=$hardware_serial, autoregister is disabled and file missing: $devfile");
    };
  };

  if ($found == 0) {
    if (defined $config{'autoregister'} && $config{'autoregister'} eq "1") {
      my $line = $dev_id . ":" . $hardware_serial;

      if (defined $auth) {
        my $csh = Crypt::SaltedHash->new(algorithm => 'SHA-512');
        $csh->add($auth);
        $line .= ":" . $csh->generate;
      };

      # add to file
      open DEVF, '>>', $devfile or die;
      print DEVF $line . "\n";
      close DEVF;
      logging("new device registered: $dev_id:$hardware_serial");
    } else {
      response(403, "access denied", "", "POST request does contain valid JSON with dev_id=$dev_id/hardware_serial=$hardware_serial, but autoregister is disabled");
      exit;
    };
  };

  # fill with template
  my $lastfile = $lastfile_template;
  my $rawfile = $rawfile_template;
  my $filledfile = $filledfile_template;
  my $emptiedfile = $emptiedfile_template;

  # replace placeholders
  $lastfile =~ s/DEV_ID/$dev_id/g;
  $rawfile =~ s/DEV_ID/$dev_id/g;
  $filledfile =~ s/DEV_ID/$dev_id/g;
  $emptiedfile =~ s/DEV_ID/$dev_id/g;

  # empty/full toggle
  my $emptiedtime_write = 0;
  my $filledtime_write = 0;

  if (defined $config{"threshold." . $dev_id}) {
    # overwrite threshold if given
    my $threshold = $config{"threshold." . $dev_id};
    $content->{'payload_fields'}->{'threshold'} = $threshold;

    my $sensor = $content->{'payload_fields'}->{'sensor'};
    my $box = $content->{'payload_fields'}->{'box'};

    if (($sensor < $threshold) && ($box eq "full")) {
      $content->{'payload_fields'}->{'box'} = "empty";
    } elsif (($sensor >= $threshold) && ($box eq "empty")) {
      $content->{'payload_fields'}->{'box'} = "full";
    };
  };

  # init
  if ($content->{'payload_fields'}->{'box'} eq "full") {
    if (! -e $filledfile) {
      $filledtime_write = 1; 
    };
  };
   
  if ($content->{'payload_fields'}->{'box'} eq "empty") {
    if (! -e $emptiedfile) {
      $emptiedtime_write = 1; 
    };
  };
   
  # check
  if (-e $filledfile && -e $emptiedfile) {
    # files are existing, retrieve contents
    open FILLEDF, "<", $filledfile or die;
    my $filledtime_ut = str2time(<FILLEDF>);
    close FILLEDF;

    open EMPTIEDF, "<", $emptiedfile or die;
    my $emptiedtime_ut = str2time(<EMPTIEDF>);
    close EMPTIEDF;
     
    if ($content->{'payload_fields'}->{'box'} eq "filled") {
      # support for future
      $filledtime_write = 1; 
    } elsif ($content->{'payload_fields'}->{'box'} eq "emptied") {
      # support for future
      $emptiedtime_write = 1; 
    } elsif ($content->{'payload_fields'}->{'box'} eq "full") {
      # box is full
      if ($filledtime_ut < $emptiedtime_ut) {
        # box was empty last time
        $filledtime_write = 1; 
        # adjust status
        $lines[0] =~ s/"full"/"filled"/o;
      };
    } elsif ($content->{'payload_fields'}->{'box'} eq "empty") {
      # box is empty
      if ($emptiedtime_ut < $filledtime_ut) {
        # box was full last time
        $emptiedtime_write = 1;
        # adjust status
        $lines[0] =~ s/"empty"/"emptied"/o;
      };
    };
  };

  if ($filledtime_write == 1) {
    open FILLEDF, ">", $filledfile or die;
    print FILLEDF $nowstr;
    close FILLEDF;
  };
 
  if ($emptiedtime_write == 1) {
    open EMPTIEDF, ">", $emptiedfile or die;
    print EMPTIEDF $nowstr;
    close EMPTIEDF;
  };

  ## write contents to files
  # last status
  open LASTF, ">", $lastfile or die;
  print LASTF $nowstr . " ";
  print LASTF $lines[0] . "\n";
  close LASTF;

  # log
  open LOGF, ">>", $rawfile or die;
  print LOGF $nowstr . " ";
  print LOGF $lines[0] . "\n";
  close LOGF;

  response(200, "OK");
  exit;

} elsif (defined $reqm && $reqm eq "GET") { # GET request
  my @devices;
  if (-e $devfile) {
    # read devices
    open DEVF, '<', $devfile or die;
    while (my $line = <DEVF>) {
      push @devices, $line;
    };
    close DEVF;
  } else {
    response(500, "no devices seen so far", "", "file not existing: $devfile");
    exit;
  };
  if (scalar(@devices) == 0) {
    response(500, "no devices seen so far", "", "file empty: $devfile");
    exit;
  };

  for my $line (@devices) {
    chomp($line);
    if ($line !~ /^([^:]+):([^:]+)(:.*)?$/o) {
      next;
    };

    my $dev_id = $1;
    my $hardware_serial = $2;

    # fill with template
    my $lastfile = $lastfile_template;
    my $filledfile = $filledfile_template;
    my $emptiedfile = $emptiedfile_template;
    
    # replace placeholders
    $lastfile =~ s/DEV_ID/$dev_id/g;
    $filledfile =~ s/DEV_ID/$dev_id/g;
    $emptiedfile =~ s/DEV_ID/$dev_id/g;

    if (! -e $lastfile) {
      # no events seen so far
      next;
    };

    my ($filledtime_ut, $emptiedtime_ut);

    if (-e $filledfile) {
      open FILLEDF, "<", $filledfile or die;
      $filledtime_ut = str2time(<FILLEDF>);
      close FILLEDF;
    };

    if (-e $emptiedfile) {
      open EMPTIEDF, "<", $emptiedfile or die;
      $emptiedtime_ut = str2time(<EMPTIEDF>);
      close EMPTIEDF;
    };

    open LASTF, "<", $lastfile || die;
    my $last = <LASTF>;
    close LASTF;
    if (! defined $last) {
      response(500, "major problem found", "", "file contains lo data: $lastfile");
      exit;
    };

    # extract reciving time before JSON starts
    $last =~ s/^([^{]+) //g;
    my $timeReceived = $1;

    # parse and check JSON
    my $content = eval{ decode_json($last)};
    if ($@) {
      response(500, "major problem found", "", "last received content not in JSON format in $lastfile");
      exit;
    };

    if ($hardware_serial ne $content->{'hardware_serial'}) {
      response(500, "major problem found", "", $hardware_serial . "(" . length($hardware_serial) . "/" . $devfile . ") not matching " . $content->{'hardware_serial'} . " (" . length($content->{'hardware_serial'}) . "/" . $lastfile . ")");
      exit;
    };

    my $sensor = $content->{'payload_fields'}->{'sensor'};
    my $threshold = $content->{'payload_fields'}->{'threshold'};
    my $voltage = $content->{'payload_fields'}->{'voltage'};
    my $tempC = $content->{'payload_fields'}->{'tempC'};
    my $time = $content->{'metadata'}->{'time'};
    my $rssi = $content->{'metadata'}->{'gateways'}[0]->{'rssi'};
    my $snr = $content->{'metadata'}->{'gateways'}[0]->{'snr'};

    # overwrite threshold if given
    if (defined $config{"threshold." . $dev_id}) {
      $threshold = $config{"threshold." . $dev_id};
    };

    # create array with additional information
    my $time_ut = str2time($time);
    my $timeReceived_ut = str2time($timeReceived);

    # store in hash
    $dev_hash{$dev_id}->{'box'} = $content->{'payload_fields'}->{'box'};

    my ($timeLastChange, $typeLastChange); 

    if (defined $filledtime_ut) {
      $dev_hash{$dev_id}->{'info'}->{'timeFilled'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($filledtime_ut));
      $timeLastChange = $filledtime_ut;
      $typeLastChange = "Filled";
    } else {
      $dev_hash{$dev_id}->{'info'}->{'timeFilled'} = "n/a";
    };

    if (defined $emptiedtime_ut) {
      $dev_hash{$dev_id}->{'info'}->{'timeEmptied'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($emptiedtime_ut));
      if ($emptiedtime_ut > $timeLastChange) {
        $timeLastChange = $emptiedtime_ut;
        $typeLastChange = "Emptied";
      };
    } else {
      $dev_hash{$dev_id}->{'info'}->{'timeEmptied'} = "n/a";
    };

    $dev_hash{$dev_id}->{'info'}->{'timeNow'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime(time));
    if (defined $timeLastChange) {
      $dev_hash{$dev_id}->{'info'}->{'deltaLastChanged'} = deltatime_string(time - $timeLastChange);
    };

    my $deltaLastReceived = time - $timeReceived_ut;

    $dev_hash{$dev_id}->{'values'}->{'deltaLastReceived'} = $deltaLastReceived;
    $dev_hash{$dev_id}->{'info'}->{'deltaLastReceived'} = deltatime_string($deltaLastReceived);
    $dev_hash{$dev_id}->{'info'}->{'timeLastReceived'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($timeReceived_ut));
    $dev_hash{$dev_id}->{'info'}->{'sensor'} = $sensor;
    $dev_hash{$dev_id}->{'info'}->{'threshold'} = $threshold;
    $dev_hash{$dev_id}->{'info'}->{'tempC'} = $tempC;
    $dev_hash{$dev_id}->{'info'}->{'voltage'} = $voltage;
    $dev_hash{$dev_id}->{'info'}->{'rssi'} = $rssi;
    $dev_hash{$dev_id}->{'info'}->{'snr'} = $snr;
    $dev_hash{$dev_id}->{'info'}->{'counter'} = $content->{'counter'};
    $dev_hash{$dev_id}->{'info'}->{'hardwareSerial'} = $hardware_serial;
    # mask hardware_serial
    $dev_hash{$dev_id}->{'info'}->{'hardwareSerial'} =~ s/(..)....(..)/$1****$2/g;
  };

  # create output
  letter(\%dev_hash);

} elsif (defined $reqm && $reqm eq "HEAD") { # HEAD request
  response(200, "OK");
  exit;

} elsif (defined $reqm) { # not supported method
  response(400, "unsupported request method", "", "request method: $reqm");
  exit;
};


##############
# Functions
##############

## logging to STDERR
sub logging($) {
  my $message = shift || "";

  if (length($message) > 0) {
    print STDERR $program . ": " . $message . "\n";
  };
};


## create deltatime string
sub deltatime_string($) {
  my $delta = shift;
  if ($delta < 3600) {
    return sprintf("%d min", int($delta / 60));
  } elsif ($delta < 3600 * 24) {
    return sprintf("%d hrs %d min", int($delta / 3600), int($delta / 60) % 60);
  } else {
    return sprintf("%d days %d hrs", int($delta / 3600 / 24), int($delta / 60 / 60) % 24);
  };
};


## print HTTP response
sub response($$;$$) {
  my $status = shift;
  my $message = shift || "";
  my $header = shift || "";
  my $error = shift || "";

  # Header
  print CGI::header(
	-status=>$status,
	-expires=>'now'
  );

  # sleep to avoid DoS
  my $sleep = 0.1 * (1 + rand(1));
  if ($status ne "200") {
    # increase sleep time in case of error
    $sleep += 3;
    # log to error log
    my $log = $message;
    $log .= ": " . $error if length($error) > 0;
    logging($log);
  };
  sleep($sleep);

  if (defined $ENV{'SERVER_PROTOCOL'} && $ENV{'SERVER_PROTOCOL'} eq "INCLUDED") {
    # called by SSI (embedded in HTML)
    print "$message";
  } else {
    # directly called
    print "<!DOCTYPE html>\n<html>\n<head>\n";
    print "$header";
    print "</head>\n<body>\n";

    print "$message";

    if (defined $reqm && $reqm eq "GET" && $status eq "200") {
      if ($config{'autorefresh'} ne "0") {
        print "<font color=grey size=-2>automatic refresh active every " . $config{'autorefresh'} . " seconds</font>\n";
      };
      # print reload button
      print "<br />";
      print qq {
<form method="get">
 <input type="submit" value="reload" style="width:200px;height:50px;">
</form>
};
    };

    print "\n</body>\n</html>\n";
  };
}


## query string parser
sub getqs{
    my $qs = $ENV{'QUERY_STRING'};
    ### dont nned this ;-)
    if(!defined $qs) { $qs = $ENV{'REDIRECT_QUERY_STRING'}; }
    if(!defined $qs) { return (); }

    my @pairs = split(/\&/,$qs);
    my $pair;
    my $key;
    my $value;
    ###my $qsdata;
    my @qsdata;
    foreach $pair (@pairs)
    {
        ($key,$value) = split(/\=/,$pair);
        if (!defined $value) { next; }
        $value =~ s/\+/ /g;
        $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
        # $value =~ s/~!/ ~!/g;
        $value =~ s/ +/ /g;
        $value =~ s/^ +//g;
        $value =~ s/ +$//g;
        $value =~ s/\n//g;
        $value =~ s/\r/\[ENTER\]/g;
        push (@qsdata,$key);
        push (@qsdata,$value);
    }
    if ($#qsdata >= 0) { return @qsdata; }
    else { return (); }
}


## letterbox HTML generation
sub letter($) {
  my $dev_hash_p = shift;
  my $num_boxes = scalar(keys %$dev_hash_p);

  my $response;
  my $bg;
  my $fc;

  $response = "<table border=\"1\" cellspacing=\"0\" cellpadding=\"2\">\n";

  $response .= " <tr>";

  $response .= "<th></th>";

  # row 1
  for my $dev_id (sort keys %$dev_hash_p) {
    $response .= "<th align=\"center\"><font size=+1><b>". $dev_id . "</b></font></th>";
  };
  $response .= "</tr>\n";

  # row 2
  $response .= " <tr>";
  $response .= "<td></td>";
  for my $dev_id (sort keys %$dev_hash_p) {
    if (defined $bg_colors{$$dev_hash_p{$dev_id}->{'box'}}) {
      # set bgcolor if defined
      $bg = " bgcolor=" . $bg_colors{$$dev_hash_p{$dev_id}->{'box'}};
    };
    $response .= "<td" . $bg . " align=\"center\"><font size=+3><b>" . uc($$dev_hash_p{$dev_id}->{'box'}) . "</b></font></td>";
  };
  $response .= "</tr>\n";

  # row 3+
  for my $info (@info_array) {
    $response .= " <tr>";
    $response .= "<td><font size=-1>" . $info . "</font></td>";

    for my $dev_id (sort keys %$dev_hash_p) {
      # no bgcolor
      $bg = "";
      # no fontcolor
      $fc = "";
      if ($info =~ /(Filled|Emptied)/o) {
        # set predefined bgcolor
        $bg = " bgcolor=" . $bg_colors{lc($1)};
        # no fontcolor
        $fc = "";
      } elsif ($info =~ /LastReceived/o) {
        if (defined $bg_colors{$$dev_hash_p{$dev_id}->{'box'}}) {
          # set bgcolor if defined
          $bg = " bgcolor=" . $bg_colors{$$dev_hash_p{$dev_id}->{'box'}};
        };
        if ($$dev_hash_p{$dev_id}->{'values'}->{'deltaLastReceived'} >= $config{"delta.crit"} * 60) {
          # disable bgcolor
          $bg = "";
          # activate fontcolor
          $fc = " color=red";
        } elsif ($$dev_hash_p{$dev_id}->{'values'}->{'deltaLastReceived'} >= $config{"delta.warn"} * 60) {
          # disable bgcolor
          $bg = "";
          # activate fontcolor
          $fc = " color=orange";
        };
      };

      $response .= "<td" . $bg . " align=\"right\"><font size=-1" . $fc . ">" . $$dev_hash_p{$dev_id}->{'info'}->{$info} . "</font></td>";
    };
    $response .= "</tr>\n";
  };

  $response .= "</table>\n";

  # autoreload header
  my $header = '<meta name="viewport" content="width=device-width, initial-scale=1">' . "\n";
  if (defined $config{'autorefresh'} && $config{'autorefresh'} ne "0") {
    $header .= '<meta HTTP-EQUIV="refresh" CONTENT="' . $config{'autorefresh'} . '">' . "\n";
  };

  response(200, $response, $header);
}; 
# vim: set noai ts=2 sw=2 et:
