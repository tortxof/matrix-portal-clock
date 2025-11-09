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

# Globals
server_timestamp_ms = 0
current_tz_offset_s = 0
next_tz_change_ms = None
next_tz_offset_s = None
local_offset_ms = 0

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


def get_timestamp_ms():
    return local_offset_ms + (time.monotonic_ns() // 1_000_000)


def get_localtime():
    global current_tz_offset_s, next_tz_change_ms, next_tz_offset_s

    now_ms = get_timestamp_ms()

    if next_tz_change_ms is not None and next_tz_offset_s is not None:
        if now_ms >= next_tz_change_ms:
            current_tz_offset_s = next_tz_offset_s
            next_tz_change_ms = None
            next_tz_offset_s = None

    localtime_now_ms = now_ms + (current_tz_offset_s * 1000)

    return time.localtime(localtime_now_ms // 1000)


def delay_sec_change():
    while True:
        now = get_localtime()
        yield now
        last_sec = now.tm_sec
        while get_localtime().tm_sec == last_sec:
            time.sleep(0.1)


def fetch_time():
    global server_timestamp_ms, current_tz_offset_s, next_tz_change_ms, next_tz_offset_s, local_offset_ms

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
        return False

    try:
        data = response.json()
    except Exception:
        return False

    server_timestamp_ms = data[0]
    current_tz_offset_s = data[1]
    next_tz_change_ms = data[2]
    next_tz_offset_s = data[3]

    one_way_latency_ns = (request_end_ns - request_start_ns) // 2

    local_request_time_ns = request_start_ns + one_way_latency_ns
    local_offset_ms = server_timestamp_ms - (local_request_time_ns // 1_000_000)

    return True


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

while not fetch_time():
    time.sleep(1.0)

last_time_update = time.monotonic()

bot_label.text = ""
if get_motd():
    last_motd_update = time.monotonic()

while True:
    for now in delay_sec_change():
        render_datetime(now)
        if time.monotonic() > last_time_update + GET_TIME_INTERVAL:
            if fetch_time():
                last_time_update = time.monotonic()
        if time.monotonic() > last_motd_update + GET_MOTD_INTERVAL:
            if get_motd():
                last_motd_update = time.monotonic()
