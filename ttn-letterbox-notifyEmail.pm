#!/bin/perl -w -T
#
# TheThingsNetwork HTTP letter box sensor notification via E-Mail
#
# (P) & (C) 2021-2024 Dr. Peter Bieringer <pb@bieringer.de>
#
# License: GPLv3
#
# Authors:  Dr. Peter Bieringer (bie)
#
# Required system features
#   - available Perl module MIME::Lite
#     successfully tested on EL8 using RPM perl-MIME-Lite using
#      smtp via localhost (but this has delays on script response)
#
# Required configuration:
#   - enable sending messages (otherwise dry-run)
#       notifyEmail.enable=1
#
#   - sender E-Mail address (must be permitted to send)
#       EXAMPLE:
#       notifyEmail.sender=postmaster@domain.example
#
# Optional configuration:
#   - control debug
#       notifyEmail.enable=1
#
# Honors entries starting with "email=" from "@notify_list" provided by main CGI
#
# Changelog:
# 20210628/bie: initial version (based on ttn-letterbox-notifyEmail.pm)
# 20210820/bie: log empty recipent list only on debug level
# 20211001/bie: adjust German translation
# 20211030/bie: add support for v3 API
# 20220218/bie: remove support of debug option by environment
# 20220421/bie: return earlier from notifyEmail_init when not enabled
# 20240119/bie: add support for device alias, cosmetics
# 20240326/bie: add Unicode chars for clock and part of day, remove seconds from timestamp
#
# TODO: implement faster mail delivery methods like "mailx"

use strict;
use warnings;
use utf8;
use Encode;

require MIME::Lite;

## globals
our %hooks;
our %config;
our %features;
our %translations;
our $language;
our @notify_list;


## prototyping
sub notifyEmail_init();
sub notifyEmail_store_data($$$);


## hooks
$hooks{'notifyEmail'}->{'init'} = \&notifyEmail_init;
$hooks{'notifyEmail'}->{'store_data'} = \&notifyEmail_store_data;

## translations
$translations{'emptied'}->{'de'} = "GELEERT";
$translations{'filled'}->{'de'} = "GEFÜLLT";
$translations{'at'}->{'de'} = "am";
$translations{'At'}->{'de'} = "Am";

## active status (= passed all validity checks)
my $notifyEmail_active = 0;
my $notifyEmail_enable = 0;

# clock icons 0000 -> 11:30
my @icon_clock = (
  "🕛", "🕧", "🕐", "🕜", "🕑", "🕝",
  "🕒", "🕞", "🕓", "🕟", "🕔", "🕠",
  "🕕", "🕡", "🕖", "🕢", "🕗", "🕣",
  "🕘", "🕤", "🕙", "🕥", "🕚", "🕦"
);

# day icon
my @icon_day = (
  "🌆" , # night
  "🌅" , # sunrise
  "🌞" , # day
  "🌇" , # sunset
);


############
## init module
############
sub notifyEmail_init() {
  # set feature
  $features{'notify'} = 1;

  if (defined $config{'notifyEmail.debug'} && $config{'notifyEmail.debug'} eq "0") {
    undef $config{'notifyEmail.debug'};
  };

  logging("notifyEmail/init: called") if defined $config{'notifyEmail.debug'};

  if (! defined $config{'notifyEmail.enable'}) {
    logging("notifyEmail/init/NOTICE: missing entry in config file: notifyEmail.enable -> notifications not enabled") if defined $config{'notifyEmail.debug'};
    $config{'notifyEmail.enable'} = "0";
  };

  if ($config{'notifyEmail.enable'} ne "1") {
    logging("notifyEmail/init/NOTICE: notifyEmail.enable is not '1' -> notifications not enabled") if defined $config{'notifyEmail.debug'};
    return 0;
  } else {
    $notifyEmail_enable = 1;
  };

  if (! defined $config{'notifyEmail.sender'}) {
    logging("notifyEmail/init/ERROR: missing entry in config file: notifyEmail.sender");
    return 0;
  };

  if ($config{'notifyEmail.sender'} !~ /^[0-9a-z\.\-\+]+\@[0-9a-z\.\-]+$/o) {
    logging("notifyEmail/init/ERROR: notifyEmail.sender is not a valid E-Mail address: " . $config{'notifyEmail.sender'});
    return 0;
  };

  $notifyEmail_active = 1;
};


## store data
sub notifyEmail_store_data($$$) {
  my $dev_id = $_[0];
  my $timeReceived = $_[1];
  my $content = $_[2];

  return if ($notifyEmail_active != 1); # nothing to do

  my $payload;
  $payload = $content->{'uplink_message'}->{'decoded_payload'}; # v3 (default)
  $payload = $content->{'payload_fields'} if (! defined $payload); # v2 (fallback)
  my $status = $payload->{'box'};

  logging("notifyEmail/store_data: called with sensor=$dev_id boxstatus=$status") if defined $config{'notifyEmail.debug'};

  if ($status =~ /^(filled|emptied)$/o) {
    # filter list
    logging("notifyEmail/store_data: notification list: " . join(' ', @notify_list)) if defined $config{'notifyEmail.debug'};
    my @notify_list_filtered = grep /^email=/, @notify_list;

    logging("notifyEmail/store_data: notification list filtered: " . join(' ', @notify_list_filtered)) if defined $config{'notifyEmail.debug'};

    if (scalar(@notify_list_filtered) == 0) {
      logging("notifyEmail/store_data: no related entry found in notification list") if defined $config{'notifyEmail.debug'};
      return 0;
    };

    logging("notifyEmail/store_data: notification list: " . join(' ', @notify_list_filtered)) if defined $config{'notifyEmail.debug'};

    foreach my $receiver (@notify_list_filtered) {
      $receiver =~ s/^email=//o; # remove prefix
      if ($receiver !~ /^([0-9a-z\.\-\+]+\@[0-9a-z\.\-]+)(;[a-z]{2})?$/o) {
        logging("notifyEmail/store_data: notification receiver not a valid E-Mail address + optional language token (SKIP): " . $receiver);
        next;
      };

      my $recipient = $1;

      if (defined $2) {
        $language = $2;
        $language =~ s/^;//o; # remove separator
      };

      my $icon = "";
      if ($status =~ /^(filled)$/o) {
        $icon = "📬 ";
      } elsif ($status =~ /^(emptied)$/o) {
        $icon = "📪 ";
      };

      # time and day icons
      my $hour   = int(strftime("%H", localtime(str2time($timeReceived))));
      my $minute = int(strftime("%M", localtime(str2time($timeReceived))));

      my $index_day = 0;
      $index_day++    if ($hour >= 6);
      $index_day++    if ($hour >= 8);
      $index_day++    if ($hour >= 18);
      $index_day = 0  if ($hour >= 20);

      $hour -= 12 if ($hour >= 12);
      my $index_clock = ($hour * 60 + $minute) / 30; # 0-23

      $icon .= $icon_day[$index_day] . $icon_clock[$index_clock];

      my $subject = translate("letterbox") . " ";
      $subject .= $icon . " ";
      if (defined $config {"alias." . $dev_id}) {
        $subject .= $config {"alias." . $dev_id};
      } else {
        $subject .= $dev_id;
      };
      $subject .= " " . translate($status) . " " . translate("at") . " " . strftime("%Y-%m-%d %H:%M %Z", localtime(str2time($timeReceived)));

      my $data;
      if (defined $config {"alias." . $dev_id}) {
        $data .= "Sensor: " . $config {"alias." . $dev_id} . " (" . $dev_id . ")\n";
      } else {
        $data .= "Sensor: " . $dev_id . "\n";
      }
      $data .= translate("boxstatus") . ": " . translate($status) . "\n";
      $data .= translate("at") . ": " . strftime("%Y-%m-%d %H:%M:%S %Z", localtime(str2time($timeReceived))) . "\n";

      logging("notifyEmail/store_data: send notification: $dev_id/$status/$receiver") if defined $config{'notifyEmail.debug'};

      if ($notifyEmail_enable != 1) {
        logging("notifyEmail/store_data/NOTICE: would send E-Mail via MIME::Lite to (if enabled): $recipient");
         # skip
      } else {
        logging("notifyEmail/store_data: call MIME::Lite now with recipient $recipient") if defined $config{'notifyEmail.debug'};
        # action
        my $msg = MIME::Lite->new(
          From     => $config{'notifyEmail.sender'},
          To       => $recipient,
          Subject  => encode("MIME-Header", $subject),
          Data     => $data,
          Encoding => 'base64',
        );

        $msg->send("smtp", "localhost"); # delays end of script
        my $rc = $?;

        logging("notifyEmail/store_data: result of called MIME::Lite: $rc") if defined $config{'notifyEmail.debug'};

        if ($rc == 0) {
          logging("notifyEmail: notification SUCCESS: $dev_id/$status/$receiver");
        } else {
          logging("notifyEmail: notification PROBLEM: $dev_id/$status/$receiver (rc=" . $rc . ")");
        };
      };
    };
  };
};

return 1;

# vim: set noai ts=2 sw=2 et:
