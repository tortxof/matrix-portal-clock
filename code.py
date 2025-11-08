import os
import time
import board
import displayio
import terminalio
from adafruit_matrixportal.matrixportal import MatrixPortal
from adafruit_matrixportal.network import Network
from adafruit_display_text.label import Label

HEADERS = {
    "X-Timezone": os.getenv("APP_TIMEZONE"),
    "X-Location": os.getenv("APP_LOCATION"),
}

REQUEST_TIMEOUT = 0.5

GET_TIME_INTERVAL = 300
GET_MOTD_INTERVAL = 10

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

WEEKDAYS = [
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
]

text_color = 0x101010

matrixportal = MatrixPortal(status_neopixel=board.NEOPIXEL, bit_depth=4, debug=False)
network = Network()
display = matrixportal.graphics.display

# Time tracking using only monotonic_ns()
time_offset_ns = 0  # Nanoseconds offset from monotonic_ns() to real time
time_is_set = False  # Whether we have synchronized time from server

# DST transition tracking
next_dst_change_timestamp = None  # Unix timestamp when next DST change occurs
dst_offset_change_sec = None  # Seconds to add to time_offset_ns when DST changes

top_label = Label(terminalio.FONT, color=text_color, text=" " * 10)
mid_label = Label(terminalio.FONT, color=text_color, text=" " * 10)
bot_label = Label(terminalio.FONT, color=text_color, text=" " * 10)

top_label.anchor_point = (0, 0)
mid_label.anchor_point = (0, 0)
bot_label.anchor_point = (0, 0)

top_label.anchored_position = (2, 0)
mid_label.anchored_position = (2, 10)
bot_label.anchored_position = (2, 20)

root_group = displayio.Group()
root_group.append(top_label)
root_group.append(mid_label)
root_group.append(bot_label)


def render_datetime(now):
    if now.tm_sec % 10 < 5:
        top_label.text = "%04d-%02d-%02d" % (now.tm_year, now.tm_mon, now.tm_mday)
    else:
        top_label.text = "%s %s %02d" % (
            WEEKDAYS[now.tm_wday],
            MONTHS[now.tm_mon - 1],
            now.tm_mday,
        )
    mid_label.text = " %02d:%02d:%02d" % (now.tm_hour, now.tm_min, now.tm_sec)


def get_precise_time():
    """Get current time with nanosecond precision using only monotonic_ns()."""
    global time_offset_ns, next_dst_change_timestamp, dst_offset_change_sec
    
    if not time_is_set:
        # Time not yet set, return epoch
        return time.localtime(0), 0

    # Current real time in nanoseconds = monotonic_ns() + offset
    current_time_ns = time.monotonic_ns() + time_offset_ns
    
    # Check if DST transition has occurred
    if next_dst_change_timestamp is not None and dst_offset_change_sec is not None:
        current_timestamp_check = current_time_ns // 1_000_000_000
        if current_timestamp_check >= next_dst_change_timestamp:
            # Apply DST offset change
            time_offset_ns += dst_offset_change_sec * 1_000_000_000
            # Clear DST transition data so we don't apply it again
            next_dst_change_timestamp = None
            dst_offset_change_sec = None
            # Recalculate with new offset
            current_time_ns = time.monotonic_ns() + time_offset_ns
    
    # Convert to seconds and remaining nanoseconds
    current_timestamp = current_time_ns // 1_000_000_000
    remaining_ns = current_time_ns % 1_000_000_000
    
    current_time = time.localtime(current_timestamp)
    return current_time, remaining_ns


def delay_sec_change():
    while True:
        now, ns = get_precise_time()
        yield now
        last_sec = now.tm_sec
        while get_precise_time()[0].tm_sec == last_sec:
            time.sleep(0.1)


def get_local_time():
    global time_offset_ns, time_is_set, next_dst_change_timestamp, dst_offset_change_sec
    try:
        # Measure network latency
        request_start_ns = time.monotonic_ns()
        response = network.requests.get(
            "%s%s" % (os.getenv("SERVER_ORIGIN"), "/time"),
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        request_end_ns = time.monotonic_ns()
    except Exception:
        pass
    else:
        data = response.json()
        # Expecting: [year, mon, day, hour, min, sec, wday, yday, isdst, microseconds, next_dst_change, dst_offset_change]
        time_struct = time.struct_time(data[:9])
        microseconds = data[9] if len(data) > 9 else 0

        # Account for network latency (estimate one-way delay as half of round-trip time)
        round_trip_ns = request_end_ns - request_start_ns
        one_way_latency_ns = round_trip_ns // 2

        # Convert server time to nanoseconds
        server_timestamp_sec = time.mktime(time_struct)
        server_time_ns = (server_timestamp_sec * 1_000_000_000) + (microseconds * 1_000)
        
        # Add latency adjustment
        server_time_ns += one_way_latency_ns
        
        # Calculate offset: real_time_ns = monotonic_ns() + offset
        # Therefore: offset = real_time_ns - monotonic_ns()
        time_offset_ns = server_time_ns - request_end_ns
        time_is_set = True
        
        # Parse DST transition info if provided
        if len(data) > 10 and data[10] is not None:
            next_dst_change_timestamp = data[10]
        else:
            next_dst_change_timestamp = None
            
        if len(data) > 11 and data[11] is not None:
            dst_offset_change_sec = data[11]
        else:
            dst_offset_change_sec = None
        
        return True
    return False


def get_motd():
    try:
        response = network.requests.get(
            "%s%s" % (os.getenv("SERVER_ORIGIN"), "/motd"),
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except Exception:
        pass
    else:
        try:
            response_data = response.json()
        except Exception:
            pass
        else:
            bot_label.text = response_data[0].center(10)
            bot_label.color = response_data[1]
            return True
    return False


display.root_group = root_group

last_time_update = last_motd_update = 0

bot_label.text = "connecting"
network.connect()
if get_local_time():
    last_time_update = time.monotonic()
bot_label.text = ""
if get_motd():
    last_motd_update = time.monotonic()

while True:
    for now in delay_sec_change():
        render_datetime(now)
        if (
            time.monotonic() > last_time_update + GET_TIME_INTERVAL
            or last_time_update == 0
        ):
            if get_local_time():
                last_time_update = time.monotonic()
        if time.monotonic() > last_motd_update + GET_MOTD_INTERVAL:
            if get_motd():
                last_motd_update = time.monotonic()
