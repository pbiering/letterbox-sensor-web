#!/bin/bash
#
# TTN / letterbox-sensor / Analysis Script
#
# (P) & (C) 2024-2024 by Dr. Peter Bieringer <pb@bieringer.de>
#
# 20240122/bie: initial (mode=freq)
# 20240126/bie: add online help
# 20240126/bie: add mode=last
# 20240215/bie: add mode=timedrift


## online help
help() {
	cat <<END
$(basename "$0") -M <mode> [-i <interval] [-h|?] <logfiles>
    <mode>
	freq		frequency usage statistics
	last		display last entry in log in human readable format
	timedrift	show time-drift


   <interval>		interval in seconds for 'timedrift'
END
}

while getopts "M:i:h?" opt; do
	case $opt in
	    M)
		mode="$OPTARG"
		;;
	    i)
		interval="$OPTARG"
		;;
	    h|\?)
		help
		exit 0
		;;
	esac
done

shift $[ $OPTIND - 1 ]

case $mode in
    freq)
	cat $* | cut -c 22- | jq .uplink_message.settings.frequency | sed 's/"//g' | sort | uniq -c | sort -k 2
	;;
    last)
	cat $* | cut -c 22- | tail -1 | jq .
	;;
    timedrift)
	timefirst=$(cat $* | cut -c 1-21 | sort | head -1)
	timelast=$(cat $* | cut -c 1-21 | sort | tail -1)
	echo "INFO  : timefirst='$timefirst' timelast='$timelast'"
	timefirst_ut=$(date '+%s' --date $timefirst)
	timelast_ut=$(date '+%s' --date $timelast)
	timedelta_sec=$[ $timelast_ut - $timefirst_ut ]
	echo "INFO  : timedelta_sec=$timedelta_sec"

	if [ -z "$interval" ]; then
		echo "WARN  : cannot calculate timedrift, missing option -i <interval>"
		exit 1
	fi

	events=$[ ($timedelta_sec + $interval * 60 - 1) / $interval / 60 ]
	echo "INFO  : events=$events"

	timedrift_sec=$[ $timedelta_sec - $interval * 60 * $events ]
	echo "NOTICE: timedrift_sec=$timedrift_sec"
	;;
esac
