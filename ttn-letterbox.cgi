#!/usr/bin/perl -w -T
#
# TheThingsNetwork HTTP integration for letterbox-sensor (v1+v2)
# - receives payload via POST from TTN
# - serves a small web page with status of letterbox sensor(s)
#   - directly called CGI
#   - included with SSI
#
# See also
#  https://github.com/hierle/letterbox-sensor
#  https://github.com/hierle/letterbox-sensor-v2
#
# Initial:
# (P) & (C) 2019-2019 Alexander Hierle <alex@hierle.com>
#
# Major extensions:
# (P) & (C) 2019-2024 Dr. Peter Bieringer <pb@bieringer.de>
#
# License: GPLv3
#
# Authors:  Alexander Hierle (hie)
#           Dr. Peter Bieringer (bie)
#
#
# Compatibility of letterbox-sensor
#   - supports version 1+2 sending "full" / "empty"
#   - supports planned future version sending also "emptied" / "filled"
#
# Preparation
#   - installation of following usually not by default installed Perl modules (EL8/Fedora35)
#       perl-Data-UUID
#       perl-URI-Encode
#       perl-Apache-Htpasswd (for user authentication)
#       perl-Authen-Passphrase or perl-Crypt-SaltedHash (for user authentication)
#       perl-LWP-Protocol-https (for user CAPTCHA verification)
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
#     - default: 0 (no debug)  1 (normal debug)  2 (some tracing)
#   - threshold.<dev_id>=<value>
#     - default: received in JSON from sensor
#   - delta.warn=<minutes>
#     - default: 45
#   - delta.crit=<minutes>
#     - default: 90
#   - alias.<dev_id>="Alias Name"
#
# Access control
#   - CGI honors for POST requests X-TTN-AUTH header which can be configured manually on TTN controller side
#     - on device autoregistration, password will be also stored in device list, allowed chars: [:alnum:]\.\-\+%
#     - in case device is already registered without password, watch for hint in log
#   - GET requests are currently NOT protected
#
# Supported Query String parameters (main, for modules see there)
#   QUERY_STRING from CGI env + HTTP_X_TTN_LETTERBOX_QUERY_STRING from mod_include
#   - dev_id=<dev_id>
#   - details=(on|off|l1)
#   - autoreload=(on|off)
#
# Supported "Accept"
#   text/plain: response in plain text
#   application/json: response in json text
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
# File: ttn.notify.list
# Contents: <dev_id>:<comma_separated_notification_token>
# Purpose: list of notification recipients defined with method
# Supported:
#       signal=<phone_number>[;<lang>] (by ttn-letterbox-notifyDbusSignal.pm)
#       email=<recipient>[;<lang>] (by ttn-letterbox-notifyEmail.pm)

#
# Changelog:
# 20191007/hie: initial
# 20191029/bie: major extension, improve output, add support for additional sensors, add some error catching
# 20191030/bie: add full/empty status support
# 20191031/bie: add filled/empty support (directly [future usage] and indirectly)
# 20191101/bie: add optional password protection capability for POST request, add support for config file
# 20191104/bie: add deltaLastChanged and threshold per dev_id in config, change color in case lastReceived is above limits
# 20191107/bie: fix+improve delta time calc+display
# 20191110/bie: implement hooks for additional modules (statistics), minor reorg
# 20191111/bie: add adjusted status filled/emptied also to content hash to be used by data update hooks, add query string handling, add additional buttons for switching graphics on/off
# 20191112/bie: rework button implementation
# 20191113/bie: implement auto-reload button
# 20191114/bie: add support for HTTP_TTN_LETTERBOX_QUERY_STRING (SSI/mod_include), change color of Reload button
# 20191115/bie: cosmetic name change
# 20191116/bie: rename HTTP_TTN_LETTERBOX_QUERY_STRING to HTTP_X_TTN_LETTERBOX_QUERY_STRING
# 20191117/bie: implement hooks for authentication, cosmetics, reorg
# 20191123/bie: cosmetics, minor bugfixes
# 20191126/bie: add support for plain and json output
# 20191214/bie: add translation support for "de"
# 20200107/bie: use only major language token for translation support
# 20200213/bie: improve layout for Mobile browers
# 20200828/bie: fix issues on EL8 and add various META HTTP-EQUIV to avoid local brower caching
# 20201109/bie: fix german translation
# 20210627/bie: add module and extended support for ttn-letterbox-notifyDbusSignal.pm
# 20210628/bie: add module and extended support for ttn-letterbox-notifyEmail.pm
# 20211001/bie: adjust German translation
# 20211030/bie: add support for v3 API, extend debugging, add payload validator
# 20211109/bie: fix payload validator for "tempC" (supporting also negative values)
# 20220217/bie: fix "counter" related to v3 API
# 20220217/bie: add support for Salted Hash provided by Authen::Passphrase::SaltedDigest in case of Crypt::SaltedHash (only available on EPEL7) is not installed/available
# 20220218/bie: add missing 'init_device' hook for POST
# 20220219/bie: display '*undef* in case a raw data value is missing (e.g. sometimes 'snr' for unknown reason)
# 20220219/bie: include device hash into module hook 'get_graphics' calls
# 20220331/bie: define button height global, align button sizes
# 20220402/bie: adjust raw content in case of threshold is provided by config (fixes improper WebUI box status display)
# 20220415/bie: add additional "details" level "l1" with limited display of details
# 20220417/bie: extend query string=value pattern check
# 20220422/bie: add support for options (used for local testing/debugging)
# 20220424/bie: clean query string from URI in response if refresh_delay is given (e.g. logout)
# 20230923/bie: set counter to 0 in case neither 'counter' nor 'f_cnt' is set
# 20240117/bie: add support for letterbox-sensor-v2
# 20240118/bie: cosmetic extension of the "details" button
# 20240119/bie: add support for device alias, cosmetic extensions
# 20240123/bie: add support for letterbox-sensor-v2/extended-payload "datarate","txpower","changed","period"
#
# TODO:
# - lock around file writes
# - safety check on config file value parsing

use English;
use strict;
use warnings;
use CGI;
use POSIX qw(strftime);
use JSON;
use Date::Parse;
use I18N::LangTags::Detect;
use Getopt::Std;
use utf8;

# autodetection of supported modules for Salted Hash
my $HAVE_Crypt_SaltedHash = 0;
eval "use Crypt::SaltedHash";
if ($@) {
  $HAVE_Crypt_SaltedHash = 0;
  eval "use Authen::Passphrase::SaltedDigest";
  if ($@) {
    die "Missing one of the module supporting salted hashes: Crypt::SaltedHash Authen::Passphrase::SaltedDigest";
  };
} else {
  $HAVE_Crypt_SaltedHash = 1;
};

push @INC, ".";

# global hooks
our %hooks;

# features
our %features;

# notify
our @notify_list;

# optional modules
my @module_list;

push @module_list, "ttn-letterbox-userauth.pm";
push @module_list, "ttn-letterbox-statistics.pm";
push @module_list, "ttn-letterbox-rrd.pm";
push @module_list, "ttn-letterbox-notifyDbusSignal.pm";
push @module_list, "ttn-letterbox-notifyEmail.pm";

for my $module (@module_list) {
  if (-e $module && -r $module) {
    require $module;
  };
};

# name of program
my $program = "ttn-letterbox.cgi";

# prototyping
sub response($$;$$$$$);
sub letter($);
sub logging($);
sub deltatime_string($);
sub req_post();
sub req_get();
sub translate($);

# global config (can be overwritten/extended by config file)
our %config = (
  'autoregister'  => 0,     # autoregister devices
  'autorefresh'   => 900,   # (seconds) of HTML autorefreshing
  'delta.warn'    => 45,    # (minutes) when color of deltaLastReceived turns orange
  'delta.crit'    => 75,    # (minutes) when color of deltaLastReceived turns red
  'button.height' => 50,    # button height in px
  'button.width'  => 100,   # button width  in px
  'debugmask'     => 0,     # debug mask (0x1: log raw JSON/POST)
  'debug'         => 0      # debug
);

# translations
our %translations;
my @languagesSupported = ( 'en', 'de' );
our $language = "en"; # default

# global data
our %querystring;
our $datadir;
our $conffile;
our $mobile = 0;

# set time strings
my $nowstr = strftime "%Y-%m-%dT%H:%M:%SZ", gmtime(time);
my $today = strftime "%Y%m%d", gmtime(time);

# defines from environment
my $reqm = $ENV{'REQUEST_METHOD'};

# payload validator
my %payload_validator = (
  'box'       => { 'pattern' => '(full|empty|filled|emptied)', 'required' => 1 }, # mandatory (v1+v2)
  'sensor1'   => { 'pattern' => '[0-9]+' , 'required' => 0 }, # new in v2
  'sensor2'   => { 'pattern' => '[0-9]+' , 'required' => 0 }, # new in v2
  'sensor'    => { 'pattern' => '[0-9]+' , 'required' => 1 }, # only in v1, will be filled with max(sensor1,sensor2) in v2
  'temp'      => { 'pattern' => '[0-9]+' , 'required' => 1 }, # n/a in v2 but will be filled with dummy value
  'tempC'     => { 'pattern' => '[0-9-]+', 'required' => 1 }, # n/a in v2 but will be filled with dummy value
  'threshold' => { 'pattern' => '[0-9]+' , 'required' => 1 }, # mandatory (v1+v2)
  'voltage'   => { 'pattern' => '[0-9.]+', 'required' => 1 }, # mandatory (v1+v2)
  'txpower'   => { 'pattern' => '[0-7]'  , 'required' => 0 }, # optional (v2 "extrainfo")
  'datarate'  => { 'pattern' => '[0-7]'  , 'required' => 0 }, # optional (v2 "extrainfo")
  'changed'   => { 'pattern' => '[0-1]'  , 'required' => 0 }, # optional (v2 "extrainfo")
  'period'    => { 'pattern' => '[0-9]+' , 'required' => 0 }, # optional (v2 "extrainfo")
);

# details depending on detail level
my @details_on = ("rssi", "snr", "tempC", "counter", "txpower", "datarate", "period", "changed", "hardwareSerial"); # only displayed in case of "details" == "on"
my @details_l1 = ("voltage", "threshold"); # only displayed in case of "details" == "l1" || "on"


####################
## option handling (for testing)
####################
sub help() {
  print qq{
Usage:
    -c <FILE>   config file
    -h|-?       this online help
};
};

my %opts;
if (! getopts('h\?c:', \%opts)) {
  print "Error in command line arguments (see -h|?)\n";
  exit 1;
};

if (defined $opts{'h'} || defined $opts{'?'}) {
  help();
  exit 0;
};

# config file
if (defined $opts{'c'}) {
  if (! -e $opts{'c'}) {
    logging("provided config file by option -c <FILE> is not existing: ". $opts{'c'});
    exit 1;
  };
  $conffile = $opts{'c'};
};


####################
## basic error check
####################

# default
if (!defined $ENV{'SERVER_NAME'}) {
  $ENV{'SERVER_NAME'} = "UNDEFINED";
  response(500, "major problem found", "", "'SERVER_NAME' not defined in environment");
  exit;
};

if (!defined $ENV{'DOCUMENT_ROOT'}) {
  response(500, "major problem found", "", "'DOCUMENT_ROOT' not defined in environment");
  exit;
};

my $confdir = $ENV{'DOCUMENT_ROOT'} . "/../conf"; # default
$datadir = $ENV{'DOCUMENT_ROOT'} . "/ttn"; # default

# read optional config
$conffile = $confdir . "/ttn-letterbox.conf" if (! defined $conffile);

if (-e $conffile) {
  if (! -r $conffile) {
    response(500, "major problem found", "", "config file exists but not readable: $conffile");
    exit;
  };
  # read key value
  open CONFF, '<', $conffile or die;
  while (my $line = <CONFF>) {
    chomp($line);
    if ($line =~ /^([A-Za-z0-9-\.]+)=([^"]*)$/o) {
      $config{$1} = $2;
      # strip quotes
    } elsif ($line =~ /^([A-Za-z0-9-\.]+)="([^"]*)"$/o) {
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
} else {
  # store in config hash
  $config{'datadir'} = $datadir;
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

# notification file
my $notifyfile =  "$datadir/ttn.notify.list";

# list of seen devices
my $devfile =  "$datadir/ttn.devices.list";

# filetemplates per DEV_ID
my $rawfile_template =  "$datadir/ttn.DEV_ID.$today.raw.log";
my $lastfile_template = "$datadir/ttn.DEV_ID.last.raw.status";
my $filledfile_template = "$datadir/ttn.DEV_ID.filled.time.status";
my $emptiedfile_template = "$datadir/ttn.DEV_ID.emptied.time.status";

# list and order of info rows in output
my @info_array = ('timeNow', 'deltaLastChanged', 'deltaLastReceived', 'timeLastReceived', 'timeLastFilled', 'timeLastEmptied', 'sensor', 'threshold', 'tempC', 'voltage', 'rssi', 'snr', 'counter', 'txpower', 'datarate', 'changed', 'period', 'hardwareSerial');

# definitions
my %dev_hash;

# translations
$translations{'timeNow'}->{'de'} = "Aktuelle Uhrzeit";
$translations{'deltaLastChanged'}->{'de'} = "Zeit seit letzter Änderung";
$translations{'deltaLastReceived'}->{'de'} = "Zeit seit letzter Übermittlung";
$translations{'timeLastReceived'}->{'de'} = "Uhrzeit der letzten Übermittlung";
$translations{'timeLastFilled'}->{'de'} = "Uhrzeit der letzten Füllung";
$translations{'timeLastEmptied'}->{'de'} = "Uhrzeit der letzten Leerung";
$translations{'letterbox'}->{'de'} = "Briefkasten";
$translations{'boxstatus'}->{'de'} = "Briefkasten-Status";
$translations{'status'}->{'de'} = "Status";
$translations{'EMPTY'}->{'de'} = "LEER";
$translations{'EMPTIED'}->{'de'} = "GELEERT";
$translations{'FILLED'}->{'de'} = "GEFÜLLT";
$translations{'FULL'}->{'de'} = "VOLL";
$translations{'hosted on'}->{'de'} = "bereitgestellt durch";
$translations{'redirect in'}->{'de'} = "weitergeleitet in";
$translations{'Letterbox Sensor Status'}->{'de'} = "Briefkasten Sensor Status";
$translations{'Reload'}->{'de'} = "Neu laden";
$translations{'Autoreload'}->{'de'} = "Autom neu laden";
$translations{'automatic refresh active every'}->{'de'} = "automatisches Auffrischen aktiv alle";
$translations{'seconds'}->{'de'} = "Sekunden";
$translations{'Graphics'}->{'de'} = "Grafik";
$translations{'hrs'}->{'de'} = "Std";
$translations{'mins'}->{'de'} = "Min";
$translations{'days'}->{'de'} = "Tage";
$translations{'More'}->{'de'} = "Mehr";


####################
## init hook
####################
for my $module (sort keys %hooks) {
  if (defined $hooks{$module}->{'init'}) {
    $hooks{$module}->{'init'}->();
  };
};


###########
## START ##
###########

my @languageUserWants = I18N::LangTags::Detect::detect();
logging("accepted languages: " . join(" ", @languageUserWants)) if ($config{'debug'} > 0);
my %languages = map { $_ => 1 } @languagesSupported;
for my $l (@languageUserWants) {
  $l =~ s/-.*//og; # cut everything behind "-"
  logging("check language: " . $l) if ($config{'debug'} > 0);
  if (defined($languages{$l})) {
    $language = $l;
    logging("selected language: " . $language) if ($config{'debug'} > 0);
    last;
  };
};


## detect mobile browers
if (defined $ENV{'HTTP_USER_AGENT'} && $ENV{'HTTP_USER_AGENT'} =~ /Mobile/) {
  $mobile = 1;
};


## handle web request
if (defined $reqm && $reqm eq "POST") { # POST data
  req_post();
  exit;

} elsif (defined $reqm && $reqm eq "GET") { # GET request
  # hook for authentication
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'auth_check'}) {
      $hooks{$module}->{'auth_check'}->();
    };
  };

  req_get();
  exit;

} elsif (defined $reqm && $reqm eq "HEAD") { # HEAD request
  response(200, "OK");
  exit;

} elsif (defined $reqm) { # not supported method
  response(400, "unsupported request method", "", "request method: $reqm");
  exit;
};


##############
##############
# Main functions
##############
##############

##############
# Hash functions
##############
## Generate (hardcoded SHA-512)
## returns salted SHA-512 hashed password
sub generate_salted_password($) {
  my $plain = $_[0];
  my $crypt;

  if ($HAVE_Crypt_SaltedHash) {
    my $csh = Crypt::SaltedHash->new(algorithm => 'SHA-512');
    $csh->add($plain);
    $crypt = $csh->generate;
  } else {
    # Fallback
    my $ppr = Authen::Passphrase::SaltedDigest->new(algorithm => 'SHA-512', salt_random => 4, passphrase => $plain);
    $crypt = "{SSHA512}" . MIME::Base64::encode_base64($ppr->hash . $ppr->salt, '')
  };

  return($crypt);
};

## Validate
# returns: 1->validated 0->nomatch
sub validate_salted_password($$) {
  my $crypt = $_[0];
  my $plain = $_[1];

  if ($HAVE_Crypt_SaltedHash) {
    if (Crypt::SaltedHash->validate($crypt, $plain)) {
      return 1;
    } else {
      return 0;
    };
  } else {
    # Fallback
    if ($crypt !~ /^{SSHA512}(.*)$/o) {
      die "validate_salted_password: crypt string contains unsupported hash method: $crypt";
    };

    $crypt = $1; # payload (Base64 encoded)
    $crypt = MIME::Base64::decode_base64($crypt); # convert into binary
    $crypt = unpack "H*", $crypt; # convert into hex string
    # create object, hex encoded SHA512 has 128 chars
    my $ppr = Authen::Passphrase::SaltedDigest->new(algorithm => 'SHA-512', salt_hex => substr($crypt, 128), hash_hex => substr($crypt, 0, 128));

    # final validation
    if ($ppr->match($plain)) {
      return 1;
    } else {
      return 0;
    };
  };
};

##############
## query string parser
## default: QUERY_STRING,REDIRECT_QUERY_STRING,HTTP_X_TTN_LETTERBOX_QUERY_STRING
## optional: given querystring
## optional2: given hash to store
##############
sub parse_querystring(;$$) {
  ## simple query string parser
  my $qs;

  if (! defined $_[0]) {
    $qs = $ENV{'QUERY_STRING'};
    if (!defined $qs) {
      # try from redirect
      $qs = $ENV{'REDIRECT_QUERY_STRING'};
    };

    # append optional TTN_LETTERBOX_QUERY_STRING (e.g. provided by SSI/mod_include)
    if (defined $ENV{'HTTP_X_TTN_LETTERBOX_QUERY_STRING'}) {
      if (defined $qs && length($qs) > 0) {
        $qs .= "&" . $ENV{'HTTP_X_TTN_LETTERBOX_QUERY_STRING'};
      } else {
        $qs = $ENV{'HTTP_X_TTN_LETTERBOX_QUERY_STRING'};
      };
    };
  } else {
    $qs = $_[0];
  };

  if (defined $qs) {
    foreach my $query_stringlet (split /[\?\&]/, $qs) {
      if ($query_stringlet !~ /^([[:alnum:]_\-]+)=([[:alnum:].\-:=\/\$%+_]+)$/o) {
        # ignore improper stringlet
        next;
      };

      if (defined $_[1]) {
        $_[1]->{$1} = $2;
      } else {
        # store in global querystring hash
        $querystring{$1} = $2;
      };
    };
  };
};


##############
## handling POST request
##############
sub req_post() {
  # receive POST data
  my @lines;
  while (<STDIN>) {
    push @lines, $_;
  };

  if ($config{'debugmask'} & 0x1) {
    logging("raw POST data: @lines");
  };

  # check contents
  if (scalar(@lines) > 1) {
    response(500, "too many lines received via POST request");
    exit;
  };

  # hook for authentication
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'auth_verify'}) {
      # can stay in module or return if not responsible or only tweaking content
      $hooks{$module}->{'auth_verify'}->($lines[0]);
    };
  };

  # decode JSON
  my $content = eval{ decode_json($lines[0])};
  if ($@) {
    response(500, "unsupported POST data", "", "POST request does not contain valid JSON content");
    exit;
  };

  # extract & check dev_id
  my $dev_id;
  $dev_id = $content->{'end_device_ids'}->{'device_id'}; # v3 (default)
  $dev_id = $content->{'dev_id'} if (! defined $dev_id); # v2 (fallback)

  if (! defined $dev_id) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'dev_id' not found");
    exit;
  };
  if ($dev_id !~ /^([a-zA-Z0-9-]+)$/o) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'dev_id' contains illegal chars");
    exit;
  };
  $dev_id = $1; # to avoid complain in tainted mode

  logging("POST/dev_id check passed: $dev_id") if ($config{'debug'} > 1);

  # extract & check hardware_serial
  my $hardware_serial;
  $hardware_serial = $content->{'end_device_ids'}->{'dev_eui'}; # v3 (default)
  $hardware_serial = $content->{'hardware_serial'} if (! defined $hardware_serial); # v2 (fallback)

  if (! defined $hardware_serial) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'hardware_serial' not found");
    exit;
  };
  if ($hardware_serial !~ /^([A-F0-9-]{16})$/o) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'hardware_serial' contains illegal chars/improper length");
    exit;
  };

  logging("POST/hardware_serial check passed: $hardware_serial") if ($config{'debug'} > 1);

  ## check payload anchor in JSON
  my $metadata;
  $metadata = $content->{'uplink_message'}->{'rx_metadata'}[0]; # v3 (default)
  $metadata = $content->{'metadata'}->{'gateways'}[0] if (! defined $metadata); # v2 (fallback)

  if (! defined $metadata) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'metadata' (v2) or 'rx_metadata' (v3) not detected");
    exit;
  };

  ## check payload anchor in JSON
  my $payload;
  $payload = $content->{'uplink_message'}->{'decoded_payload'}; # v3 (default)
  $payload = $content->{'payload_fields'} if (! defined $payload); # v2 (fallback)

  if (! defined $payload) {
    response(500, "unsupported POST data", "", "POST request does contain valid JSON but 'payload_fields' (v2) or 'decoded_payload' (v3) not detected");
    exit;
  };

  ## letterbox-sensor-v2 handling
  # v2 has 2 sensors, highest value has precedence
  if (defined $payload->{'sensor1'} && defined $payload->{'sensor2'}) {
    $payload->{'sensor'} = $payload->{'sensor1'};
    $payload->{'sensor'} = $payload->{'sensor2'} if $payload->{'sensor2'} > $payload->{'sensor1'};
    logging("POST/payload 'sensor' aggregated from 'sensor1' & 'sensor2' (new capability of letterbox-sensor-v2)") if ($config{'debug'} > 1);
  };
  # v2 has no temperature sensor so far, preset with 0
  if (!defined $payload->{'temp'}) {
    logging("POST/payload 'temp' preset to 0 (missing support in letterbox-sensor-v2)") if ($config{'debug'} > 1);
    $payload->{'temp'} = 0;
  };
  if (!defined $payload->{'tempC'}) {
    logging("POST/payload 'temp' preset to 0 (missing support in letterbox-sensor-v2)") if ($config{'debug'} > 1);
    $payload->{'tempC'} = 0;
  };

  for my $key (keys %payload_validator) {
    if (!defined $payload->{$key}) {
      if ($payload_validator{$key}->{'required'} == 1) {
        response(500, "unsupported POST data", "", "POST request does contain valid JSON but required payload is missing '$key'");
        exit;
      } else {
        next;
      };
    };

    if ($payload->{$key} !~ /^$payload_validator{$key}->{'pattern'}$/) {
      response(500, "unsupported POST data", "", "POST request does contain valid JSON but payload key '$key' contains invalid content '$payload->{$key}'");
      exit;
    };
  };

  logging("POST/payload check passed") if ($config{'debug'} > 1);

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

  logging("POST/auth check passed") if ($config{'debug'} > 1);

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
            # password defined and given, crypt string is starting with : from regex above
            if (validate_salted_password(substr($3, 1), $auth)) {
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
            my $crypt = generate_salted_password($auth);
            logging("request received with password, strongly recommend to replace entry in $devfile with $dev_id:$hardware_serial:" . $crypt);
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
    logging("POST/autoregister") if ($config{'debug'} > 1);

    if (defined $config{'autoregister'} && $config{'autoregister'} eq "1") {
      my $line = $dev_id . ":" . $hardware_serial;

      if (defined $auth) {
        $line .= ":" . generate_salted_password($auth);
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
    $payload->{'threshold'} = $threshold;

    my $sensor = $payload->{'sensor'};
    my $box = $payload->{'box'};

    # overwrite box status with given threshold
    if (($sensor < $threshold) && ($box =~ /^(full|filled)$/o)) {
      $lines[0] =~ s/("box":)"(full|filled)"/$1"empty"/o; # adjust raw content
      $payload->{'box'} = "empty";
    } elsif (($sensor >= $threshold) && ($box =~ /^(empty|emptied)$/o)) {
      $lines[0] =~ s/("box":)"(empty|emptied)"/$1"full"/o; # adjust raw content
      $payload->{'box'} = "full";
    };
  };

  # init in case of lastfilled/lastemptied is missing
  if ($payload->{'box'} =~ /^(full|filled)$/o) {
    if (! -e $filledfile) {
      $filledtime_write = 1;
    };
  };

  if ($payload->{'box'} =~ /^(empty|emptied)$/o) {
    if (! -e $emptiedfile) {
      $emptiedtime_write = 1;
    };
  };

  ## state adjustments empty->filled->full->emptied->empty
  if (-e $filledfile && -e $emptiedfile) {
    # files are existing, retrieve contents
    open FILLEDF, "<", $filledfile or die;
    my $filledtime_ut = str2time(<FILLEDF>);
    close FILLEDF;

    open EMPTIEDF, "<", $emptiedfile or die;
    my $emptiedtime_ut = str2time(<EMPTIEDF>);
    close EMPTIEDF;

    if ($payload->{'box'} eq "filled") {
      # support for future
      $filledtime_write = 1;
    } elsif ($payload->{'box'} eq "emptied") {
      # support for future
      $emptiedtime_write = 1;
    } elsif ($payload->{'box'} eq "full") {
      # box is full
      if ($filledtime_ut < $emptiedtime_ut) {
        # box was empty last time
        $filledtime_write = 1;
        # adjust status
        $lines[0] =~ s/("box":)"full"/$1"filled"/o; # adjust raw content
        $payload->{'box'} = "filled";
      };
    } elsif ($payload->{'box'} eq "empty") {
      # box is empty
      if ($emptiedtime_ut < $filledtime_ut) {
        # box was full last time
        $emptiedtime_write = 1;
        # adjust status
        $lines[0] =~ s/("box":)"empty"/$1"emptied"/o; # adjust raw content
        $payload->{'box'} = "emptied";
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

  # preparation for features
  if (defined $features{'notify'}) {
    # read notification list
    if (! -e $notifyfile) {
      logging("notification feature supported, but UNSUABLE, config file is not existing: " . $notifyfile);
      # file is not existing, not that critical
    } else {
      if (open NOTIFYF, '<', $notifyfile) {
        while (my $line = <NOTIFYF>) {
          chomp($line);
          if ($line !~ /^([^:]+):([^:]+)$/o) {
            next;
          };
          if (defined $1 && $1 eq $dev_id) {
            # dev_id found
            if (defined $2) {
              #logging("notification feature supported and ENABLED for $dev_id: $2");
              @notify_list = split(/,/, $2);
            };
          };
        };
        close NOTIFYF;
      } else {
        logging("notification feature supported but UNUSABLE, config file is existing, but can't be read: " . $notifyfile);
      };
    };
  };

  logging("POST/main finished, call now modules") if ($config{'debug'} > 1);

  ####################
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'init_device'}) {
      logging("POST/call now module/init_device: $module") if ($config{'debug'} > 1);
      $hooks{$module}->{'init_device'}->($dev_id);
    };
  };

  ####################
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'store_data'}) {
      logging("POST/call now module/store_data: $module") if ($config{'debug'} > 1);
      $hooks{$module}->{'store_data'}->($dev_id, $nowstr, $content);
    };
  };

  response(200, "OK");
};


##############
## handling GET request
##############
sub req_get() {
  parse_querystring();

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

    if (defined $querystring{'dev_id'} && $querystring{'dev_id'} ne $dev_id) {
      # skip if not matching explicity given one
      next;
    };

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

    my $hardware_serial_last;
    $hardware_serial_last = $content->{'end_device_ids'}->{'dev_eui'}; # v3 (default)
    $hardware_serial_last = $content->{'hardware_serial'} if (! defined $hardware_serial); # v2 (fallback)
    if ($hardware_serial ne $hardware_serial_last) {
      response(500, "major problem found", "", $hardware_serial . "(" . length($hardware_serial) . "/" . $devfile . ") not matching " . $hardware_serial_last . " (" . length($hardware_serial_last) . "/" . $lastfile . ")");
      exit;
    };

    my $payload_last;
    $payload_last = $content->{'uplink_message'}->{'decoded_payload'}; # v3 (default)
    $payload_last = $content->{'payload_fields'} if (! defined $payload_last); # v2 (fallback)

    ## letterbox-sensor-v2 handling
    # v2 has 2 sensors, highest value has precedence
    if (defined $payload_last->{'sensor1'} && defined $payload_last->{'sensor2'}) {
      $payload_last->{'sensor'} = $payload_last->{'sensor1'};
      $payload_last->{'sensor'} = $payload_last->{'sensor2'} if $payload_last->{'sensor2'} > $payload_last->{'sensor1'};
    };

    my $sensor = $payload_last->{'sensor'};
    my $threshold = $payload_last->{'threshold'};
    my $voltage = $payload_last->{'voltage'};
    my $tempC = $payload_last->{'tempC'};
    my $period = $payload_last->{'period'};
    my $txpower = $payload_last->{'txpower'};
    my $datarate = $payload_last->{'datarate'};
    my $changed = $payload_last->{'changed'};
    my $period = $payload_last->{'period'};

    my $metadata_last;
    $metadata_last = $content->{'uplink_message'}->{'rx_metadata'}[0]; # v3 (default)
    $metadata_last = $content->{'metadata'}->{'gateways'}[0] if (! defined $metadata_last); # v2 (fallback)
    my $time = $metadata_last->{'time'};
    my $rssi = $metadata_last->{'rssi'};
    my $snr = $metadata_last->{'snr'};

    # overwrite threshold if given
    if (defined $config{"threshold." . $dev_id}) {
      $threshold = $config{"threshold." . $dev_id};
    };

    # create array with additional information
    my $time_ut = str2time($time);
    my $timeReceived_ut = str2time($timeReceived);

    # store in hash
    $dev_hash{$dev_id}->{'box'} = $payload_last->{'box'};

    my $timeLastChange;

    if (defined $filledtime_ut) {
      $dev_hash{$dev_id}->{'info'}->{'timeLastFilled'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($filledtime_ut));
      $dev_hash{$dev_id}->{'values'}->{'timeLastFilled'} = $filledtime_ut;
      $timeLastChange = $filledtime_ut;
    } else {
      $dev_hash{$dev_id}->{'info'}->{'timeLastFilled'} = "n/a";
      $dev_hash{$dev_id}->{'values'}->{'timeLastFilled'} = 0;
    };

    if (defined $emptiedtime_ut) {
      $dev_hash{$dev_id}->{'info'}->{'timeLastEmptied'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($emptiedtime_ut));
      $dev_hash{$dev_id}->{'values'}->{'timeLastEmptied'} = $emptiedtime_ut;
      if (defined $timeLastChange && $emptiedtime_ut > $timeLastChange) {
        # only overwrite if > $filledtime_ut
        $timeLastChange = $emptiedtime_ut;
      };
    } else {
      $dev_hash{$dev_id}->{'info'}->{'timeLastEmptied'} = "n/a";
      $dev_hash{$dev_id}->{'values'}->{'timeLastEmptied'} = 0;
    };

    $dev_hash{$dev_id}->{'info'}->{'timeNow'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime(time));
    $dev_hash{$dev_id}->{'values'}->{'timeNow'} = time;
    if (defined $timeLastChange) {
      $dev_hash{$dev_id}->{'info'}->{'deltaLastChanged'} = deltatime_string(time - $timeLastChange);
      $dev_hash{$dev_id}->{'values'}->{'deltaLastChanged'} = time - $timeLastChange;
    };

    my $deltaLastReceived = time - $timeReceived_ut;

    $dev_hash{$dev_id}->{'values'}->{'deltaLastReceived'} = $deltaLastReceived;
    $dev_hash{$dev_id}->{'info'}->{'deltaLastReceived'} = deltatime_string($deltaLastReceived);
    $dev_hash{$dev_id}->{'info'}->{'timeLastReceived'} = strftime("%Y-%m-%d %H:%M:%S %Z", localtime($timeReceived_ut));
    $dev_hash{$dev_id}->{'values'}->{'timeLastReceived'} = $timeReceived_ut;
    $dev_hash{$dev_id}->{'info'}->{'sensor'} = $sensor;
    $dev_hash{$dev_id}->{'info'}->{'threshold'} = $threshold;
    $dev_hash{$dev_id}->{'info'}->{'tempC'} = $tempC;
    $dev_hash{$dev_id}->{'info'}->{'voltage'} = $voltage;
    $dev_hash{$dev_id}->{'info'}->{'rssi'} = $rssi;
    $dev_hash{$dev_id}->{'info'}->{'snr'} = $snr;
    $dev_hash{$dev_id}->{'info'}->{'counter'} = 0; # default in case neither 'counter' nor 'f_cnt' is set
    $dev_hash{$dev_id}->{'info'}->{'counter'} = $content->{'counter'} if defined ($content->{'counter'}); # v2
    $dev_hash{$dev_id}->{'info'}->{'counter'} = $content->{'uplink_message'}->{'f_cnt'} if defined ($content->{'uplink_message'}->{'f_cnt'}); # v3
    $dev_hash{$dev_id}->{'info'}->{'hardwareSerial'} = $hardware_serial;
    $dev_hash{$dev_id}->{'info'}->{'txpower'} = $txpower;
    $dev_hash{$dev_id}->{'info'}->{'datarate'} = $datarate;
    $dev_hash{$dev_id}->{'info'}->{'changed'} = $changed;
    $dev_hash{$dev_id}->{'info'}->{'period'} = $period;
    # mask hardware_serial
    $dev_hash{$dev_id}->{'info'}->{'hardwareSerial'} =~ s/(..)....(..)/$1****$2/g;

    ####################
    for my $module (sort keys %hooks) {
      if (defined $hooks{$module}->{'init_device'}) {
        $hooks{$module}->{'init_device'}->($dev_id);
      };
    };

    ####################
    for my $module (sort keys %hooks) {
      if (defined $hooks{$module}->{'get_graphics'}) {
        if (defined $querystring{$module} && $querystring{$module} eq "on") {
          my %graphics = $hooks{$module}->{'get_graphics'}->($dev_id, \%querystring, \%{$dev_hash{$dev_id}});
          for my $type (keys %graphics) {
            $dev_hash{$dev_id}->{'graphics'}->{$type} = $graphics{$type};
          };
        };
      };
    };
  };

  # create output
  if (defined $ENV{'HTTP_ACCEPT'} && $ENV{'HTTP_ACCEPT'} =~ /^(text\/plain|application\/json)$/o) {
    letter_text(\%dev_hash, $1);
  } else {
    letter(\%dev_hash);
  };
};


##############
# helper functions
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
    return sprintf("%d " . translate("mins"), int($delta / 60));
  } elsif ($delta < 3600 * 24) {
    return sprintf("%d " . translate("hrs") . " %d " . translate("mins"), int($delta / 3600), int($delta / 60) % 60);
  } else {
    return sprintf("%d " . translate("days") . " %d " . translate("hrs"), int($delta / 3600 / 24), int($delta / 60 / 60) % 24);
  };
};


## print HTTP response
sub response($$;$$$$$) {
  my $status = $_[0];
  my $message = $_[1] || "";
  my $header = $_[2] || "";
  my $error = $_[3] || "";
  my $cookie = $_[4];
  my $refresh_delay = $_[5];
  my $quiet = $_[6];

  my %cgi_headers = (
    -status => $status,
    -expires => 'now'
  );

  $cgi_headers{'-cookie'} = $cookie if (defined $cookie);

  if (defined $ENV{'REQUEST_URI'}) {
    my $url = $ENV{'REQUEST_URI'};
    $url =~ s/\?.*$//o; # strip query string from URI
    $cgi_headers{'-Refresh'} = $refresh_delay . ";url=" . $url if (defined $refresh_delay);
  };

  if (defined $ENV{'HTTP_ACCEPT'} && $ENV{'HTTP_ACCEPT'} =~ /^(text\/plain|application\|json)$/o) {
    $cgi_headers{'-Type'} = $1 . "; charset=utf-8";
  };

  # Header
  print CGI::header(%cgi_headers);

  # sleep to avoid DoS
  my $sleep = 0.1 * (1 + rand(1));
  if ($status ne "200") {
    # increase sleep time in case of error
    $sleep += 3;
    # log to error log
    my $log = $message;
    $log = $error if length($error) > 0;
    logging($log);
  };
  sleep($sleep);

  if ((defined $ENV{'SERVER_PROTOCOL'} && $ENV{'SERVER_PROTOCOL'} eq "INCLUDED")
    ||(defined $ENV{'HTTP_ACCEPT'} && $ENV{'HTTP_ACCEPT'} =~ /^(text\/plain|application\|json)$/o)
  ) {
    # called by SSI (embedded in HTML)
    print "$message";
  } else {
    # directly called
    print "<!DOCTYPE html>\n<html>\n<head>\n";
    print " <title>TTN " . translate("Letterbox Sensor Status") . " - " . $ENV{'SERVER_NAME'} . "</title>\n";
    print " <META NAME=\"viewport\" CONTENT=\"width=device-width, initial-scale=1\">\n";
    print " <META HTTP-EQUIV=\"Content-Type\" content=\"text/html; charset=utf-8\">\n";
    print " <META HTTP-EQUIV=\"PRAGMA\" CONTENT=\"NO-CACHE\">\n";
    print " <META HTTP-EQUIV=\"CACHE-CONTROL\" CONTENT=\"NO-CACHE\">\n";
    print " <META HTTP-EQUIV=\"EXPIRES\" CONTENT=\"0\">\n";
    print "$header";
    print "</head>\n";
    print "<body style=\"font-family: sans-serif\">\n";
    print "<font size=\"+1\">TTN " . translate("Letterbox Sensor Status") . "</font>\n";
    print "<br />\n";
    print "<font size=\"-1\">" . translate("hosted on") . " " . $ENV{'SERVER_NAME'} . "</font>\n";
    print "<br />\n";

    print "$message";

    if (defined $refresh_delay && ! defined $quiet) {
      print "<br />\n";
      print "<font size=\"-1\">" . translate("redirect in") . " " . $refresh_delay . " " . translate("seconds") . "</font>\n";
    };

    print "</body>\n</html>\n";
  };
};


## letterbox HTML generation
sub letter($) {
  my $dev_hash_p = shift;

  my %dev_hash;

  my $response = "";
  my $bg;
  my $fc;

  my $has_graphics = 0;
  my $querystring_copy;
  my $toggle_color;

  my $button_size   = "width:" . $config{'button.width'} . "px;height:" . $config{'button.height'} . "px;";
  my $button_size09 = "width:" . int($config{'button.width'} * 0.9) . "px;height:" . $config{'button.height'} . "px;";
  my $button_size14 = "width:" . int($config{'button.width'} * 1.4) . "px;height:" . $config{'button.height'} . "px;";

  ## button row #1
  $response .= "<table border=\"0\" cellspacing=\"0\" cellpadding=\"2\"><!-- button row #1 -->\n";
  $response .= " <tr>\n";

  # print reload button
  $response .= "  <td>\n";
  $response .= "   <form method=\"get\">\n";
  $response .= "    <input type=\"submit\" value=\"" . translate("Reload") . "\" style=\"background-color:#DEB887;" . $button_size . "\">\n";
  for my $key (sort keys %querystring) {
    $response .= "    <input type=\"text\" name=\"" . $key . "\" value=\"" . $querystring{$key} . "\" hidden>\n";
  };
  $response .= "   </form>\n";
  $response .= "  </td>\n";

  # print autoreload=on|off button
  $querystring_copy = { %querystring };
  $querystring{'autoreload'} = "off" if (!defined $querystring{'autoreload'} || $querystring{'autoreload'} !~ /^(on|off)$/o);
  if ($querystring{'autoreload'} eq "off") {
    $querystring_copy->{'autoreload'} = "on";
    $toggle_color = "#E0E0E0";
  } else {
    $querystring_copy->{'autoreload'} = "off";
    $toggle_color = "#E0E000";
  };
  $response .= "  <td>\n";
  $response .= "   <form method=\"get\">\n";
  $response .= "    <input type=\"submit\" value=\"" . translate("Autoreload") . "\" style=\"background-color:" . $toggle_color . ";" . $button_size14 . "\">\n";
  for my $key (sort keys %$querystring_copy) {
    $response .= "    <input type=\"text\" name=\"" . $key . "\" value=\"" . $querystring_copy->{$key} . "\" hidden>\n";
  };
  $response .= "   </form>\n";
  $response .= "  </td>\n";

  # print details=on|off|l1 button
  $querystring_copy = { %querystring };
  $querystring{'details'} = "off" if (!defined $querystring{'details'} || $querystring{'details'} !~ /^(on|off|l1)$/o);
  if ($querystring{'details'} eq "off") {
    $querystring_copy->{'details'} = "l1";
    $toggle_color = "#E0E0E0";
  } elsif ($querystring{'details'} eq "l1") {
    $querystring_copy->{'details'} = "on";
    $toggle_color = "#00A0A0";
  } elsif ($querystring{'details'} eq "on") {
    $querystring_copy->{'details'} = "off";
    $toggle_color = "#00E000";
  };
  $response .= "  <td>\n";
  $response .= "   <form method=\"get\">\n";
  $response .= "    <input type=\"submit\" value=\"";
  if ($querystring{'details'} eq "l1") {
    $response .= translate("More") . " ";
  };
  $response .= "Details\" style=\"background-color:" . $toggle_color . ";" . $button_size09 . "\">\n";

  for my $key (sort keys %$querystring_copy) {
    $response .= "    <input type=\"text\" name=\"" . $key . "\" value=\"" . $querystring_copy->{$key} . "\" hidden>\n";
  };
  $response .= "   </form>\n";
  $response .= "  </td>\n";

  $response .= " </tr>\n";
  $response .= "</table>\n";

  ## button row #2
  $response .= "<table border=\"0\" cellspacing=\"0\" cellpadding=\"2\"><!-- button row #2 -->\n";
  $response .= " <tr>\n";

  # html action per module
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'html_actions'}) {
      $response .= $hooks{$module}->{'html_actions'}->(\%querystring);
    };
  };

  $response .= " </tr>\n";
  $response .= "</table>\n";

  ## autorefresh
  if (defined $ENV{'SERVER_PROTOCOL'} && $ENV{'SERVER_PROTOCOL'} eq "INCLUDED") {
    $response .= "<br />\n";
  } elsif (defined $config{'autorefresh'} && $config{'autorefresh'} ne "0" && $querystring{'autoreload'} eq "on") {
    $response .= "<font color=grey size=-2>" . translate("automatic refresh active every") . " " . $config{'autorefresh'} . " " . translate("seconds") . "</font>\n";
    $response .= "<br />\n";
  } else {
    $response .= "<br />\n";
  };

  # hook for authentication (display)
  for my $module (sort keys %hooks) {
    if (defined $hooks{$module}->{'auth_show'}) {
      my $text = $hooks{$module}->{'auth_show'}->();
      if (defined $text) {
        $response .= "<font color=grey size=-2>" . $text . "</font>\n";
        $response .= "<br />\n";
      };
    };
  };

  # hook for authentication (acl)
  for my $dev_id (sort keys %$dev_hash_p) {
    my $acl_found = 0;
    for my $module (sort keys %hooks) {
      if (defined $hooks{$module}->{'auth_check_acl'}) {
        $acl_found = 1;
        if ($hooks{$module}->{'auth_check_acl'}->($dev_id) > 0) {
          # warn("add after acl check dev_id=" . $dev_id);
          $dev_hash{$dev_id} = $$dev_hash_p{$dev_id};
        };
      };
    };

    if ($acl_found == 0) {
      # no ACL hook active
      $dev_hash{$dev_id} = $$dev_hash_p{$dev_id};
    };
  };

  if (scalar(keys %dev_hash) == 0) {
    # no devices in list or permitted
    $response .= "<font color=\"red\">no devices found or permitted</font>";
    response(200, $response, undef);
    exit 0;
  };

  $response .= "<table border=\"1\" cellspacing=\"0\" cellpadding=\"2\">\n";

  $response .= " <tr>";

  $response .= "<th align=\"left\">" . translate("letterbox") . "</th>";

  # row 1
  for my $dev_id (sort keys %dev_hash) {
    $response .= "<th align=\"center\">";
    if (defined $config {"alias." . $dev_id}) {
      $response .= "<font size=+1><b>". $config {"alias." . $dev_id} . "</b></font>";
      $response .= "<br />";
      $response .= "<font size=-1>". $dev_id . "</font>";
    } else {
      $response .= "<font size=+1><b>". $dev_id . "</b></font>";
    };
    $response .= "</th>";
  };
  $response .= "</tr>\n";

  # row 2
  $response .= " <tr>";
  $response .= "<td>" . translate("status") . "</td>";
  for my $dev_id (sort keys %dev_hash) {
    if (defined $bg_colors{$dev_hash{$dev_id}->{'box'}}) {
      # set bgcolor if defined
      $bg = " bgcolor=" . $bg_colors{$dev_hash{$dev_id}->{'box'}};
    };
    $response .= "<td" . $bg . " align=\"center\"><font size=+3><b>" . translate(uc($dev_hash{$dev_id}->{'box'})) . "</b></font></td>";
  };
  $response .= "</tr>\n";

  # row 3+
  for my $info (@info_array) {
    next if ((! defined $querystring{'details'} || $querystring{'details'} eq "off") && $info !~ /^(time|delta)/o);

    if ($querystring{'details'} eq "l1") {
      next if grep /^$info$/, @details_on;
    };

    $response .= " <tr>";
    $response .= "<td><font size=-1>" . translate($info) . "</font></td>";

    for my $dev_id (sort keys %dev_hash) {
      # no bgcolor
      $bg = "";
      # no fontcolor
      $fc = "";
      if ($info =~ /(Filled|Emptied)/o) {
        # set predefined bgcolor
        $bg = " bgcolor=" . $bg_colors{lc($1)};
        # no fontcolor
        $fc = "";
      } elsif ($info =~ /Last(Received|Changed)/o) {
        if (defined $bg_colors{$dev_hash{$dev_id}->{'box'}}) {
          # set bgcolor if defined
          $bg = " bgcolor=" . $bg_colors{$dev_hash{$dev_id}->{'box'}};
        };
        if ($dev_hash{$dev_id}->{'values'}->{'deltaLastReceived'} >= $config{"delta.crit"} * 60) {
          # disable bgcolor
          $bg = "";
          # activate fontcolor
          $fc = " color=red";
        } elsif ($dev_hash{$dev_id}->{'values'}->{'deltaLastReceived'} >= $config{"delta.warn"} * 60) {
          # disable bgcolor
          $bg = "";
          # activate fontcolor
          $fc = " color=orange";
        };
      };

      my $value = $dev_hash{$dev_id}->{'info'}->{$info};
      $value = "*undef*" if (! defined $value);
      $response .= "<td" . $bg . " align=\"right\"><font size=-1" . $fc . ">" . $value . "</font></td>";

      # check for optional graphics
      if (defined $dev_hash{$dev_id}->{'graphics'}) {
        $has_graphics = 1;
      };
    };
    $response .= "</tr>\n";
  };

  if ($has_graphics == 1) {
    # get list of types
    my %types;
    for my $dev_id (sort keys %dev_hash) {
      my $graphics_p = $dev_hash{$dev_id}->{'graphics'};
      for my $type (keys %$graphics_p) {
        $types{$type} = 1;
      };
    };

    # print optional graphics
    for my $type (sort keys %types) {
      $response .= " <tr>";
      $response .= "<td><font size=-1>" . translate("Graphics") . ":<br />" . translate($type) . "</font></td>";
      for my $dev_id (sort keys %dev_hash) {
        $response .= "\n  <td align=\"center\">\n";
        if (defined $dev_hash{$dev_id}->{'graphics'}) {
          my $graphics_p = $dev_hash{$dev_id}->{'graphics'};
          my $line = $$graphics_p{$type};
          $response .= "   " . $line . "\n";
        };
        $response .= "  </td>";
      };
      $response .= "\n </tr>\n";
    };
  };

  $response .= "</table>\n";

  # autoreload header
  my $header;
  if (defined $config{'autorefresh'} && $config{'autorefresh'} ne "0" && $querystring{'autoreload'} eq "on") {
    $header = ' <META HTTP-EQUIV="refresh" CONTENT="' . $config{'autorefresh'} . '">' . "\n";
  };

  response(200, $response, $header);
};


## letterbox text/json generation
sub letter_text($$) {
  my $dev_hash_p = $_[0];
  my $format = $_[1];

  my %dev_hash;

  my %result;
  my @device_info;

  my $response;
  my @response_text;

  # hook for authentication (acl)
  for my $dev_id (sort keys %$dev_hash_p) {
    my $acl_found = 0;
    for my $module (sort keys %hooks) {
      if (defined $hooks{$module}->{'auth_check_acl'}) {
        $acl_found = 1;
        if ($hooks{$module}->{'auth_check_acl'}->($dev_id) > 0) {
          # warn("add after acl check dev_id=" . $dev_id);
          $dev_hash{$dev_id} = $$dev_hash_p{$dev_id};
        };
      };
    };

    if ($acl_found == 0) {
      # no ACL hook active
      $dev_hash{$dev_id} = $$dev_hash_p{$dev_id};
    };
  };

  if (scalar(keys %dev_hash) == 0) {
    # no devices in list or permitted
    $result{'statusText'} = "no devices found or permitted";
    $result{'statusCode'} = 401;
  } else {
    $result{'statusText'} = "devices found";
    $result{'statusCode'} = 200;

    for my $dev_id (sort keys %dev_hash) {
      push @device_info, $dev_hash{$dev_id};
      for my $key (sort keys %{$dev_hash{$dev_id}}) {
        if (ref($dev_hash{$dev_id}->{$key}) eq 'HASH') {
          for my $subkey (sort keys %{$dev_hash{$dev_id}->{$key}}) {
            push @response_text, "device." . $dev_id . "." . $key . "." . $subkey . "=\"" . $dev_hash{$dev_id}->{$key}->{$subkey} . "\"";
          };
        } else {
            push @response_text, "device." . $dev_id . "." . $key . "=\"" . $dev_hash{$dev_id}->{$key} . "\"";
        };
      };
    };

    $result{'devices'} = \@device_info;
  };

  push @response_text, "statusText=\"" . $result{'statusText'} . "\"";
  push @response_text, "statusCode=" . $result{'statusCode'};

  if ($format eq "application/json") {
    # encode to json
    #$response = encode_json(\%result);
    my $json = JSON->new->allow_nonref;
    $response = $json->pretty->encode(\%result);
  } else {
    $response = join("\n", @response_text);
    $response .= "\n";
  };

  response(200, $response, undef);
};


## Translation function
sub translate($) {
  if (defined $translations{$_[0]}->{$language}) {
    return $translations{$_[0]}->{$language};
  } else {
    return $_[0];
  };
};

# vim: set noai ts=2 sw=2 et:
