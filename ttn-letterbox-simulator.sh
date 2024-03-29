#/bin/bash
#
# Letterbox simulator to test server application
#
# (P) & (C) 2019-2022 Dr. Peter Bieringer <pb@bieringer.de>
#
# License: GPLv3
#
# 2019xxxx/pbiering: initial version
# 20210627/pbiering: add support for options, major extension
# 20211030/pbiering: add support for v3 API and change to default (https://www.thethingsindustries.com/docs/reference/data-formats/)
# 20211030/pbiering: optionally overwrite decoded payload defaults by environment
# 20220402/pbiering: add support for optional -E|-F <sensor>

program=$(basename $0)
version="3.0.0"

counter_file="./$(basename $0 .sh).counter"

hw_serial="0000000000000000"
sensor_full=500
sensor_empty=25

help() {
	cat <<END
$program -U <url> -H <auth-header> -D <device-id> -B <box-status> [...]

 Mandatory
  -U <url>             URL to post simulation data, e.g. https://my.iot.domain.example/cgi-bin/ttn-letterbox-test.cgi
  -H <auth-header>     authentication header, e.g. "X-TTN-AUTH: MySeCrEt"
  -D <device-id>       device ID
  -B <box-status>      box status to submit (full|empty|filled|emptied)

 Optional:
  -C <counter-file>    fetch/store counter value of sensors (default: $counter_file.<device-id>)
  -S <serial>          hardware serial (default: $hw_serial)
  -F <sensor-full>     overwrite sensor value for 'full'  (default: $sensor_full)
  -E <sensor-empty>    overwrite sensor value for 'empty' (default: $sensor_empty)
  -d                   debug
  -r                   real-run (otherwise only print what will be done)
  -2                   switch to v2 API (legacy)
END
}

while getopts "E:F:C:A:U:D:B:r2dh?" opt; do
	case $opt in
	    C)
		counter_file="$OPTARG"
		;;
	    A)
		auth_header="$OPTARG"
		;;
	    U)
		url="$OPTARG"
		;;
	    D)
		device_id="$OPTARG"
		;;
	    S)
		hw_serial="$OPTARG"
		;;
	    B)
		box_status="$OPTARG"
		;;
	    F)
		sensor_full="$OPTARG"
		;;
	    E)
		sensor_empty="$OPTARG"
		;;
	    d)
		debug=1
		;;
	    r)
		real_run=1
		;;
	    2)
		ttnv2=1
		;;
	    ?|h)
		help
		exit 1
		;;
	    *)
		echo "ERROR : invalid option: -$OPTARG" >&2
		exit 1
		;;
	esac
done

shift $[ OPTIND - 1 ]

## failsafe checks
if [ -z "$url" ]; then
	echo "ERROR : mandatory URL is missing (-U ...)" >&2
	exit 1
fi

if [ -z "$auth_header" ]; then
	echo "ERROR : mandatory authentication header is missing (-A ...)" >&2
	exit 1
fi

if [ -z "$device_id" ]; then
	echo "ERROR : mandatory device-id is missing (-D ...)" >&2
	exit 1
fi

if [ -z "$box_status" ]; then
	echo "ERROR : mandatory box-status is missing (-B ...)" >&2
	exit 1
fi


# generate final counter file name
counter_file="$counter_file.$device_id"

if [ ! -e "$counter_file" ]; then
	echo "NOTICE: default/provided counter file is not existing: $counter_file (create now)" >&2
	touch $counter_file
fi

if [ ! -f "$counter_file" ]; then
	echo "ERROR : default/provided counter file is not a real file: $counter_file" >&2
	exit 1
fi

if [ ! -r "$counter_file" ]; then
	echo "ERROR : default/provided counter file is not readable: $counter_file" >&2
	exit 1
fi

if [ ! -w "$counter_file" ]; then
	echo "ERROR : default/provided counter file is not writable: $counter_file" >&2
	exit 1
fi


## read counter
counter=$(cat $counter_file)
if [ -z "$counter" ]; then
	counter=0
fi

[ "$debug" = "1" ] && echo "DEBUG : counter fetched from file ($counter_file): $counter"

counter=$[ $counter + 1 ]
if [ "$real_run" = "1" ]; then
	[ "$debug" = "1" ] && echo "DEBUG : counter stored to file ($counter_file): $counter"
	echo -n "$counter" >$counter_file
	if [ $? -ne 0 ]; then
		echo "ERROR : can't update counter file: $counter_file" >&2
		exit 1
	fi
else
	echo "NOTICE: real-run (-r) not seleced, don't update counter file: $counter_file" >&2
fi

case $box_status in
    full|filled)
	sensor=$sensor_full
	;;
    empty|emptied)
	sensor=$sensor_empty
	;;
esac

echo "NOTICE: box_status=$box_status sensor=$sensor counter=$counter" >&2

# default data (TODO: make optional if required)
timestamp=$(date -u "+%s")
datetime=$(date -u "+%FT%T.%NZ")

temp="${temp:-244}"
tempC="${tempC:-19}"
threshold="${threshold:-30}"
voltage="${voltage:-3.242}"

gtw_id="eui-b827ebff00000000" # dummy
frequency="868.3"
channel="1"
rssi="-27"
snr="8.5"
rf_chain="1"
latitude="0.0000"
longitude="0.0000"
altitude="0"
downlink_url="https://integrations.thethingsnetwork.org/ttn-eu/api/v2/down/my-letterbox-sensor/my-letterbox-sensor?key=TEST"

user_agent="$program/$version"

print_request() {
	# TODO: calculate "payload_raw" according to provided values

	if [ "$ttnv2" = "1" ]; then
	cat <<END
{"app_id":"$device_id","dev_id":"$device_id","hardware_serial":"$hw_serial","port":1,"counter":$counter,"payload_raw":"/6oMgQIe9A==","payload_fields":{"box":"$box_status","sensor":$sensor,"temp":$temp,"tempC":$tempC,"threshold":$threshold,"voltage":$voltage},"metadata":{"time":"$datetime","frequency":$frequency,"modulation":"LORA","data_rate":"SF7BW125","coding_rate":"4/5","gateways":[{"gtw_id":"$gtw_id","timestamp":$timestamp,"time":"$datetime","channel":$channel,"rssi":$rssi,"snr":$snr,"rf_chain":$rf_chain,"latitude":$latitude,"longitude":$longitude,"altitude":$altitude}]},"downlink_url":"$downlink_url"}
END

	else # ttnv2
	cat <<END
{"end_device_ids":{"device_id":"$device_id","application_ids":{"application_id":"letterbox-sensor"},"dev_eui":"$hw_serial","join_eui":"000000000000","dev_addr":"00000000"},"correlation_ids":["as:up:00000000000000000000000000","gs:conn:00000000000000000000000000","gs:up:host:00000000000000000000000000","gs:uplink:00000000000000000000000000","ns:uplink:00000000000000000000000000","rpc:/ttn.lorawan.v3.GsNs/HandleUplink:00000000000000000000000000","rpc:/ttn.lorawan.v3.NsAs/HandleUplink:00000000000000000000000000"],"received_at":"$datetime","uplink_message":{"f_port":1,"f_cnt":15234,"frm_payload":"/5EKHwMeCQ==","decoded_payload":{"box":"$box_status","sensor":"$sensor","temp":$temp,"tempC":"$tempC","threshold":$threshold,"voltage":"$voltage"},"decoded_payload_warnings":[],"rx_metadata":[{"gateway_ids":{"gateway_id":"$gtw_id","eui":"0000000000000000"},"time":"$datetime","timestamp":$timestamp,"rssi":$rssi,"channel_rssi":$rssi,"snr":$snr,"location":{"latitude":$latitude,"longitude":$longitude,"altitude":$altitude,"source":"SOURCE_REGISTRY"},"uplink_token":"000000000000000000000000000000000000000000000000000000000000000000000000000000000"}],"settings":{"data_rate":{"lora":{"bandwidth":125000,"spreading_factor":7}},"data_rate_index":5,"coding_rate":"4/5","frequency":"$frequency","timestamp":$timestamp,"time":"$datetime"},"received_at":"$datetime","consumed_airtime":"0.056576s","network_ids":{"net_id":"000013","tenant_id":"ttn","cluster_id":"ttn-eu1"}}}
END
	fi # ttnv2
}

if [ "$ttnv2" = "1" ]; then
	user_agent="$user_agent (APIv2)"
else
	user_agent="$user_agent (APIv3)"
fi

if [ "$real_run" = "1" ]; then
	if [ "$debug" = "1" ]; then
		echo "INFO  : URL to call: $url"
		echo "INFO  : AuthHeader : $auth_header"
		echo "INFO  : UserAgent  : $user_agent"
		echo "INFO  : Request BEGIN"
		print_request
		echo "INFO  : Request END"
	fi
	print_request | curl -A "$user_agent" -H "$auth_header" --data @- $url
	rc=$?

	if [ $rc -ne 0 ]; then
		echo "ERROR : call not successful (rc=$rc)"
	else
		echo "INFO  : call successful"
	fi
else
	echo "NOTICE: dry-run mode active by default (missing: -r)" >&2
	echo "INFO  : URL to call: $url"
	echo "INFO  : AuthHeader : $auth_header"
	echo "INFO  : UserAgent  : $user_agent"
	echo "INFO  : Request BEGIN"
	print_request
	echo "INFO  : Request END"
fi
