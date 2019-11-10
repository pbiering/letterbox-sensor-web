#!/bin/perl -w -T
#
# TheThingsNetwork HTTP letter box sensor statistics extension
#
# (P) & (C) 2019-2019 Dr. Peter Bieringer <pb@bieringer.de>
#
# License: GPLv3
#
# Authors:  Dr. Peter Bieringer (bie)
#
# digitFontPattern/paint taken from http://ip.bieringer.de/cgn-test.html
#
# 20191101/bie: initial version
# 20191102/bie: major enhancement, support receivestatus and time+status
# 20191105/bie: paint x/y numbers
# 20191108/bie: enable as plugin module
# 20191109/bie: add hooks for inline graphics
# 20191110/bie: add scaling and description

use strict;
use warnings;
use Image::Xpm;
use GD;
use JSON;
use Date::Parse;
use MIME::Base64;

## globals
our %hooks;
our %config;


## prototyping
sub statistics_init();
sub statistics_init_device($);
sub statistics_get_graphics($);
sub statistics_store_data($$$);


## hooks
$hooks{'statistics'}->{'init'} = \&statistics_init;
$hooks{'statistics'}->{'init_device'} = \&statistics_init_device;
$hooks{'statistics'}->{'get_graphics'} = \&statistics_get_graphics;
$hooks{'statistics'}->{'store_data'} = \&statistics_store_data;


## statistics
my @statistics = ("boxstatus", "receivedstatus");


## small charset for digits encoded in 15 bit
my @statistics_digitFontPattern = (0x7b6f, 0x2492, 0x73e7, 0x79e7, 0x49ed, 0x79cf, 0x7bcf, 0x4927, 0x7bef, 0x79ef);


## statistics_sizes
my %statistics_sizes = (
  'boxstatus' => {
      'xmax' => 96, # every 15 min
      'ymax' => 100, # 100 days
      'xgrid' => 4,
      'ygrid' => 5,
      'xdiv' => 4,
      'ydiv' => 1,
      'xscale' => 3,
      'yscale' => 3,
      ,'ltext' => "Days (rollover)",
      ,'ttext' => "Hour Of Day (UTC)",
      'dborder' => 8, # description border
      'lborder' => 13,
      'rborder' => 5,
      'tborder' => 11,
      'bborder' => 5
  },
  'receivedstatus' => {
      'xmax' => 48, # every 30 min
      'ymax' => 100, # 100 days
      'xgrid' => 2,
      'ygrid' => 5,
      'xdiv' => 2,
      'ydiv' => 1,
      'xscale' => 3,
      'yscale' => 3,
      ,'ltext' => "Days (rollover)",
      ,'btext' => "Counter (rollover)",
      ,'rtext' => "Counter (rollover)",
      ,'ttext' => "Hour Of Day (UTC)",
      'dborder' => 8, # description border
      'lborder' => 13,
      'rborder' => 21,
      'tborder' => 11,
      'bborder' => 11
  }
);


## colors
my $color_ticks = "#101010";

my $color_number = "#000000";

my $color_white = "#FFFFFF";
my $color_black = "#000000";

my $color_clear = "#FFFFFF";

my $color_border = "#A0A0A0";

my $color_receivestatus_ok = "#CCFF66";
my $color_receivestatus_gap = "#FF0000";

my %colors_boxstatus = (
  'full'    => '#6FEF00',# green
  'empty'   => '#C8C8C8', # grey
  'filled'  => '#FFFF00', # yellow
  'emptied' => '#FF8080' # pink
);

my %colors_infostore_set = (
  0 => "#010101",
  1 => "#020202"
);


## paint digit
sub statistics_paintDigit($$$$$) {
	my $image = $_[0];
	my $x = $_[1];
	my $y = $_[2];
	my $d = $_[3];
	my $col = $_[4];

	my $pattern = $statistics_digitFontPattern[$d];
  	my $bit;

        for (my $yd = 0; $yd < 5; $yd++) {
                for (my $xd = 0; $xd < 3; $xd++) {
                        $bit = $yd * 3 + $xd;
                        if ($pattern & (1 << $bit)) {
				$image->xy($x + $xd, $y + $yd, $col);
                        };
                };
        };
};

## paint number (maximal 5 digits)
sub statistics_paintNumber($$$$$) {
	my $image = $_[0];
	my $x = $_[1];
	my $y = $_[2];
	my $num = $_[3];
	my $col = $_[4];
        my $mask = 10000;
        my $d;
        my $xd = 0;

        if ($num == 0) {
                statistics_paintDigit($image, $x, $y, $num, $col);
        } else {
                while ($mask > $num) {
                        $mask /= 10;
                };

                while ($mask >= 1) {
                        $d = int($num / $mask);
                        statistics_paintDigit($image, $x + $xd, $y, $d, $col);
                        $num -= $d * $mask;
                        $mask /= 10;
                        $xd += 4;
                };
        };
};

### create new XPM
sub statistics_xpm_create($$) {
  my $file = $_[0];
  my $type = $_[1];

  my $i;

  # get values
  my $xmax = $statistics_sizes{$type}->{'xmax'};
  my $ymax = $statistics_sizes{$type}->{'ymax'};
  my $xdiv = $statistics_sizes{$type}->{'xdiv'};
  my $ydiv = $statistics_sizes{$type}->{'ydiv'};
  my $xgrid = $statistics_sizes{$type}->{'xgrid'};
  my $ygrid = $statistics_sizes{$type}->{'ygrid'};
  my $lborder = $statistics_sizes{$type}->{'lborder'};
  my $rborder = $statistics_sizes{$type}->{'rborder'};
  my $tborder = $statistics_sizes{$type}->{'tborder'};
  my $bborder = $statistics_sizes{$type}->{'bborder'};

  # add border
  my $width = $xmax + $lborder + $rborder;
  my $height = $ymax + $tborder + $bborder;

	logging("Create new picture: " . $file) if defined $config{'statistics'}->{'debug'};

	# new picture
	$i = Image::Xpm->new(-width => $width, -height => $height);

	# fill background with border color
  #logging("DEBUG : new picture: border background") if defined $config{'statistics'}->{'debug'};
	$i->rectangle(0, 0, $width - 1, $height - 1, $color_black);
	$i->rectangle(1, 1, $width - 2, $height - 2, $color_border, 1);

	# fill background of graphics with  color
  #logging("DEBUG : new picture: graphics background") if defined $config{'statistics'}->{'debug'};
  $i->rectangle($lborder, $tborder, $width - $rborder - 1, $height - $bborder - 1, $color_white, 1);

	# draw x ticks minor
	for (my $x = 0; $x < $xmax; $x += $xgrid) {
		$i->xy($x + $lborder, $tborder - 1 , $color_ticks); # top
		$i->xy($x + $lborder, $height - $bborder + 0 , $color_ticks); # bottom
	};

	# draw x ticks major
	for (my $x = 0; $x < $xmax; $x += $xgrid * 12) {
		$i->xy($x + $lborder, $tborder - 3 , $color_ticks); # top
		$i->xy($x + $lborder, $height - $bborder + 2 , $color_ticks); # bottom
	};

  # draw x top number
	for (my $x = 0; $x < $xmax; $x += $xgrid * 6) {
		statistics_paintNumber($i, $x + $lborder - 1, 2, int($x / $xdiv), $color_number);
	  # draw x ticks number
		$i->xy($x + $lborder, $tborder - 2 , $color_ticks);
		$i->xy($x + $lborder, $height - $bborder + 1 , $color_ticks);
	};

	# draw y ticks minor
	for (my $y = 0; $y < $ymax; $y += $ygrid) {
		$i->xy(0 + $lborder - 1, $y + $tborder, $color_ticks); # left
		$i->xy($width - $rborder , $y + $tborder, $color_ticks); # right
	};

	# draw y ticks major
	for (my $y = 0; $y < $ymax; $y += $ygrid * 10) {
		$i->xy(0 + $lborder - 3, $y + $tborder, $color_ticks); # left
		$i->xy($width - $rborder + 2, $y + $tborder, $color_ticks); # right
	};

  # draw y left number
	for (my $y = 0; $y < $ymax; $y += $ygrid * 2) {
		statistics_paintNumber($i, 2, $y + $tborder - 1, int($y / $ydiv), $color_number);
	  # draw y ticks number
		$i->xy(0 + $lborder - 2, $y + $tborder, $color_ticks);
		$i->xy($width - $rborder + 1, $y + $tborder, $color_ticks);
	};

  if ($type eq "receivedstatus") {
    # draw x bottom number
    for (my $x = 0; $x < $xmax; $x += $xgrid * 6) {
      statistics_paintNumber($i, $x + $lborder - 1, $height - $bborder + 4, $x, $color_number);
    };

    # draw y right number
    for (my $y = 0; $y < $ymax; $y += $ygrid * 2) {
      statistics_paintNumber($i, $width - $rborder + 4, $y + $tborder - 1, $y * $xmax, $color_number);
    };
  };


  # reset infostore
	statistics_set_infostore($i, 0);

	$i->save($file);

	logging("Created new picture: " . $file) if defined $config{'statistics'}->{'debug'};
};


## update XPM
sub statistics_xpm_update($$$$;$) {
  my $file = $_[0];
  my $type = $_[1];
  my $value = $_[2];
  my $data = $_[3];
  my $i = $_[4];

  # get values
  my $xmax = $statistics_sizes{$type}->{'xmax'};
  my $ymax = $statistics_sizes{$type}->{'ymax'};
  my $lborder = $statistics_sizes{$type}->{'lborder'};
  my $rborder = $statistics_sizes{$type}->{'rborder'};
  my $tborder = $statistics_sizes{$type}->{'tborder'};
  my $bborder = $statistics_sizes{$type}->{'bborder'};
  my $xgrid = $statistics_sizes{$type}->{'xgrid'};
  my $ygrid = $statistics_sizes{$type}->{'ygrid'};

  if (defined $file && ! defined $i) {
  	$i = Image::Xpm->new(-file => $file);
  };

  my $value_stored = statistics_get_infostore($i);

  if ($type eq "receivedstatus") {
    if (defined $value) {
      if ($value - 1 != $value_stored) {
        if ($value > $value_stored) {
          # fill gap
          for (my $c = $value_stored + 1; $c < $value; $c++) {
            $i->xy($lborder + ($c % $xmax), $tborder + (int($c / $xmax) % $ymax), $color_receivestatus_gap);
          };
        };
      };
      $i->xy($lborder + ($value % $xmax), $tborder + (int($value / $xmax) % $ymax), $color_receivestatus_ok);
      statistics_set_infostore($i, $value);

      logging("value: stored=" . $value_stored . " new=" . $value) if defined $config{'statistics'}->{'debug'};
    } else {
      logging("value: stored=" . $value_stored . " (nothing to do)") if defined $config{'statistics'}->{'debug'};
    };

    # clear at least next 5 lines
    for (my $g = $value + 1; $g < $value + $xmax * 3; $g++) {
        $i->xy($lborder + ($g % $xmax), $tborder + (int($g / $xmax) % $ymax), $color_clear);
    };
  } elsif ($type eq "boxstatus") {
    my $div = 60 * 15; # 15 min
    if (defined $value) {
      my $color = $colors_boxstatus{$data};

      my $value_mod = int($value / $div);

      $i->xy($lborder + ($value_mod % $xmax), $tborder + (int($value_mod / $xmax) % $ymax), $color);

      if (($value_stored > 0) && ($value_mod -1 > $value_stored)) {
        # fill gaps
        for (my $g = $value_stored + 1; $g < $value_mod; $g++) {
          $i->xy($lborder + ($g % $xmax), $tborder + (int($g / $xmax) % $ymax), $color);
        };
      };

      # clear at least next 5 lines
      for (my $g = $value_mod + 1; $g < $value_mod + $xmax * 3; $g++) {
          $i->xy($lborder + ($g % $xmax), $tborder + (int($g / $xmax) % $ymax), $color_clear);
      };

      statistics_set_infostore($i, $value_mod);

      logging("value: stored=" . $value_stored . " new=" . $value_mod . " color=" . $color . " status=" . $data) if defined $config{'statistics'}->{'debug'};
    } else {
      logging("value: stored=" . $value_stored . " (nothing to do)") if defined $config{'statistics'}->{'debug'};
    };
	};

  if (defined $file) {
  	$i->save;
  };
};


###(pixel in picture)
## store data into infostore
sub statistics_set_infostore($$) {
  my $i = shift;
  my $value = shift || 0;

  for (my $b = 0; $b < 32; $b++) {
    if (($value & 0x1) == 1) {
      $i->xy($b, 0, $colors_infostore_set{'1'});
    } else {
      $i->xy($b, 0, $colors_infostore_set{'0'});
    };
    $value >>= 1;
  };
};


## get data from infostore (pixel in picture)
sub statistics_get_infostore($;$) {
  my $i = $_[0];
  my $file = $_[1]; # optional

  if (! defined $i && defined $file) {
    # open file
	  $i = Image::Xpm->new(-file => $file);
  };

  my $value = 0;
  my $bit = 1;

  for (my $b = 0; $b < 32; $b++) {
    if ($i->xy($b, 0) eq $colors_infostore_set{'1'}) {
      $value += $bit;
    };
    $bit <<= 1;
  };
  return $value;
};

############
## init module
############
sub statistics_init() {
  if (defined $ENV{'TTN_LETTERBOX_DEBUG_GRAPHICS'}) {
    $config{'statistics'}->{'debug'} = 1;
  };

  logging("statistics/init: called") if defined $config{'statistics'}->{'debug'};
};

## fill historical data of device
sub statistics_fill_device($$$) {
  my $dev_id = $_[0];
  my $file = $_[1];
  my $type = $_[2];

  my @logfiles;
  my %values;

  # read directory
  my $dir = $config{'datadir'};
  opendir (DIR, $dir) or die $!;
  while (my $entry = readdir(DIR)) {
    next unless (-f "$dir/$entry");
    next unless ($entry =~ /^ttn\.$dev_id\.[0-9]+\.raw.log$/);
    logging("DEBUG : logfile found: " . $entry) if defined $config{'statistics'}->{'debug'};
    push @logfiles, $entry;
  };

  # get data from logfiles
  foreach my $logfile (sort @logfiles) {
    open LOGF, '<', $dir . "/" . $logfile or die $!;
		while (<LOGF>) {
			my $line = $_;
			chomp($line);
			$line =~ s/^([^{]+) //g;
			my $timeReceived = $1;
			my $content = eval{ decode_json($line)};
			if ($@) {
				die("major problem found", "", "line not in JSON format");
			};

			if ($type eq "receivedstatus") {
				if (! defined $content->{'counter'}) {
					die("major problem found", "", "JSON don't contain 'counter'");
				};
				$values{$content->{'counter'}} = 1;

			} elsif ($type eq "boxstatus")  {
				if (! defined $content->{'payload_fields'}->{'box'}) {
					die("major problem found", "", "JSON don't contain 'box'");
				};
				my $timeReceived_ut = str2time($timeReceived);
				if (! defined $timeReceived_ut) {
					die("cannot parse time: " . $timeReceived);
				};

 				$values{$timeReceived_ut} = $content->{'payload_fields'}->{'box'};

        if (defined $config{"threshold." . $dev_id}) {
          if (($content->{'payload_fields'}->{'box'} eq "empty")
            && ($content->{'payload_fields'}->{'sensor'} >= $config{"threshold." . $dev_id})
          ) {
            # overwrite status by later adjusted threshold
  	        $values{$timeReceived_ut} = "full";
          } elsif (($content->{'payload_fields'}->{'box'} eq "full")
            && ($content->{'payload_fields'}->{'sensor'} < $config{"threshold." . $dev_id})
          ) {
            # overwrite status by later adjusted threshold
  	        $values{$timeReceived_ut} = "empty";
          };
        };
			};
    };
    close LOGF;
  };

  # store data from logfiles in xpm
	my $i = Image::Xpm->new(-file => $file);

	# loop
	for my $value (sort { $a <=> $b } keys %values) {
    statistics_xpm_update(undef, $type, $value, $values{$value}, $i);
	};

  # finally save
	$i->save;
};


## init device
sub statistics_init_device($) {
  my $dev_id = $_[0];

  logging("Called: init_device with dev_id=" . $dev_id) if defined $config{'statistics'}->{'debug'};

  for my $type (@statistics) {
    my $file = $config{'datadir'} . "/ttn." . $dev_id . "." . $type . ".xpm";

    logging("DEBUG : check for file: " . $file) if defined $config{'statistics'}->{'debug'};
    if (! -e $file) {
      logging("DEBUG : file missing, create now: " . $file) if defined $config{'statistics'}->{'debug'};
      statistics_xpm_create($file, $type);
    } else {
      logging("DEBUG : file already existing: " . $file) if defined $config{'statistics'}->{'debug'};
    };

    my $value = statistics_get_infostore(undef, $file);
    if ($value == 0) {
      logging("DEBUG : file already existing but empty: " . $file) if defined $config{'statistics'}->{'debug'};
      statistics_fill_device($dev_id, $file, $type);
    } else {
      logging("DEBUG : file already existing and has value: " . $file . "#" . $value) if defined $config{'statistics'}->{'debug'};
    };
  };
};


## store data
sub statistics_store_data($$$) {
  my $dev_id = $_[0];
  my $timeReceived = $_[1];
  my $content = $_[2];

  my %values;
  my $value;

  logging("statistics/store_data: called") if defined $config{'statistics'}->{'debug'};

  for my $type (@statistics) {
    my $file = $config{'datadir'} . "/ttn." . $dev_id . "." . $type . ".xpm";

    if ($type eq "receivedstatus") {
      if (! defined $content->{'counter'}) {
        die("major problem found", "", "JSON don't contain 'counter'");
      };
      $values{$content->{'counter'}} = 1;
      $value = $content->{'counter'};

    } elsif ($type eq "boxstatus")  {
      if (! defined $content->{'payload_fields'}->{'box'}) {
        die("major problem found", "", "JSON don't contain 'box'");
      };
      my $timeReceived_ut = str2time($timeReceived);
      if (! defined $timeReceived_ut) {
        die("cannot parse time: " . $timeReceived);
      };
      $values{$timeReceived_ut} = $content->{'payload_fields'}->{'box'};
      $value = $timeReceived_ut;
    };

    statistics_xpm_update($file, $type, $value, $values{$value}, undef);
  };
};

## get graphics
sub statistics_get_graphics($) {
  my $dev_id = $_[0];

  my %html;

  logging("Called: get_graphics with dev_id=" . $dev_id) if defined $config{'statistics'}->{'debug'};

  for my $type (@statistics) {
    my $file = $config{'datadir'} . "/ttn." . $dev_id . "." . $type . ".xpm";

    logging("DEBUG : check for file: " . $file) if defined $config{'statistics'}->{'debug'};
    if (! -e $file) {
      logging("DEBUG : file missing, skip: " . $file) if defined $config{'statistics'}->{'debug'};
    } else {
      logging("DEBUG : file existing, export graphics: " . $file) if defined $config{'statistics'}->{'debug'};
      my $image = GD::Image->newFromXpm($file);

      my $xscale = $statistics_sizes{$type}->{'xscale'};
      my $yscale = $statistics_sizes{$type}->{'yscale'};

      if (defined $ENV{'HTTP_USER_AGENT'} && $ENV{'HTTP_USER_AGENT'} =~ /Mobile/) {
        # scale down on mobile devices
        $xscale -= 1;
        $yscale -= 1;
      };

      my $width = $image->width * $xscale;
      my $height = $image->height * $yscale;

      my $lborder = $statistics_sizes{$type}->{'lborder'} * $xscale;
      my $rborder = $statistics_sizes{$type}->{'rborder'} * $xscale;
      my $tborder = $statistics_sizes{$type}->{'tborder'} * $yscale;
      my $bborder = $statistics_sizes{$type}->{'bborder'} * $yscale;

      my $xmax = $statistics_sizes{$type}->{'xmax'} * $yscale;
      my $ymax = $statistics_sizes{$type}->{'ymax'} * $yscale;

      my $dborder = $statistics_sizes{$type}->{'dborder'};
      my $border = $dborder;

      if ($type eq "receivedstatus") {
        $border += $dborder
      };

      my $image_scaled = GD::Image->new($width + $border, $height + $border);
      $image_scaled->copyResized($image, $dborder, $dborder, 0, 0, $width, $height, $image->width, $image->height);

      my $white = $image_scaled->colorAllocate(255,255,255);

      my $text;
      my $textsize = 5;

      $text = $statistics_sizes{$type}->{'ttext'};
      $image_scaled->string(gdTinyFont, $xmax / 2 + $lborder + $dborder - length($text)/2 * $textsize, 1, $text, $white);

      $text = $statistics_sizes{$type}->{'ltext'};
      $image_scaled->stringUp(gdTinyFont, 1, $ymax / 2 + $tborder + $dborder + length($text)/2 * $textsize, $text, $white);

      if ($type eq "receivedstatus") {
        $text = $statistics_sizes{$type}->{'btext'};
        $image_scaled->string(gdTinyFont, $xmax / 2 + $lborder + $dborder - length($text)/2 * $textsize, $height + $border - 9, $text, $white);

        $text = $statistics_sizes{$type}->{'rtext'};
        $image_scaled->stringUp(gdTinyFont, $width + $dborder - 2, $ymax / 2 + $tborder + $dborder + length($text)/2 * $textsize, $text, $white);
      };

      my $png_base64 = encode_base64($image_scaled->png(9), "");
      $html{$type} = '<img alt="' . $type . '" src="data:image/png;base64,' . $png_base64 . '">';
    };
  };
  return %html;
};