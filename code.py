import os
import time
import board
import rtc
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

# High-precision time tracking
rtc_microseconds = 0  # Microseconds component from server
rtc_set_time_ns = 0  # monotonic_ns() when RTC was set
rtc_base_timestamp = 0  # Unix timestamp when RTC was set

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
    """Get current time with microsecond precision."""
    if rtc_set_time_ns == 0:
        # RTC not yet set, return basic time
        return time.localtime(), 0

    # Calculate elapsed time since RTC was set
    elapsed_ns = time.monotonic_ns() - rtc_set_time_ns
    # Convert microseconds from server to nanoseconds and add elapsed time
    total_ns = (rtc_microseconds * 1_000) + elapsed_ns

    # Extract additional seconds from nanoseconds
    additional_seconds = total_ns // 1_000_000_000
    remaining_ns = total_ns % 1_000_000_000

    # Calculate current time from base timestamp plus elapsed seconds
    current_timestamp = rtc_base_timestamp + additional_seconds
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
    global rtc_microseconds, rtc_set_time_ns, rtc_base_timestamp
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
        # Expecting: [year, mon, day, hour, min, sec, wday, yday, isdst, microseconds]
        time_struct = time.struct_time(data[:9])
        rtc.RTC().datetime = time_struct
        rtc_microseconds = data[9] if len(data) > 9 else 0

        # Account for network latency (estimate one-way delay as half of round-trip time)
        round_trip_ns = request_end_ns - request_start_ns
        one_way_latency_ns = round_trip_ns // 2

        # Adjust the microseconds by adding the latency
        rtc_microseconds += one_way_latency_ns // 1_000  # Convert ns to microseconds

        # Handle overflow if microseconds >= 1 second
        if rtc_microseconds >= 1_000_000:
            additional_seconds = rtc_microseconds // 1_000_000
            rtc_microseconds = rtc_microseconds % 1_000_000
            # Adjust the time struct for additional seconds
            adjusted_timestamp = time.mktime(time_struct) + additional_seconds
            time_struct = time.localtime(adjusted_timestamp)
            rtc.RTC().datetime = time_struct

        rtc_set_time_ns = time.monotonic_ns()
        rtc_base_timestamp = time.mktime(time_struct)
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
