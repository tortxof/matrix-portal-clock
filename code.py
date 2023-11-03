import os
import time
import board
import rtc
import displayio
import terminalio
from adafruit_matrixportal.matrixportal import MatrixPortal
from adafruit_matrixportal.network import Network
from adafruit_display_text.label import Label

REQUEST_TIMEOUT = 0.5

GET_TIME_INTERVAL = 3600
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
    if now.tm_sec % 20 < 10:
        top_label.text = "%04d-%02d-%02d" % (now.tm_year, now.tm_mon, now.tm_mday)
    else:
        top_label.text = "%s %s %02d" % (
            WEEKDAYS[now.tm_wday],
            MONTHS[now.tm_mon - 1],
            now.tm_mday,
        )
    mid_label.text = " %02d:%02d:%02d" % (now.tm_hour, now.tm_min, now.tm_sec)


def delay_sec_change():
    while True:
        now = time.localtime()
        yield now
        last_sec = now.tm_sec
        while time.localtime().tm_sec == last_sec:
            time.sleep(0.1)


def get_local_time():
    try:
        response = network.requests.get(
            "%s%s" % (os.getenv("SERVER_ORIGIN"), "/time"), timeout=REQUEST_TIMEOUT
        )
    except Exception:
        pass
    else:
        rtc.RTC().datetime = time.struct_time(response.json())
        return True
    return False


def get_motd():
    try:
        response = network.requests.get(
            "%s%s" % (os.getenv("SERVER_ORIGIN"), "/motd"), timeout=REQUEST_TIMEOUT
        )
    except Exception:
        pass
    else:
        try:
            response_data = response.json()
        except ValueError:
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
