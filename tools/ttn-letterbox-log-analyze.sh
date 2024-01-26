#!/bin/bash
#
# TTN / letterbox-sensor / Analysis Script
#
# (P) & (C) 2024-2024 by Dr. Peter Bieringer <pb@bieringer.de>
#
# 20240122/bie: initial (mode=freq)
# 20240126/bie: add online help
# 20240126/bie: add mode=last


## online help
help() {
	cat <<END
$(basename "$0") -M <mode> [-h|?] <logfiles>
    <mode>
	freq	frequency usage statistics
	last	display last entry in log in human readable format
END
}

while getopts "M:h?" opt; do
	case $opt in
	    M)
		mode="$OPTARG"
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
esac
