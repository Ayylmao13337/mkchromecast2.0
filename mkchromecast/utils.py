# This file is part of mkchromecast.

import json
import os
import psutil
import socket
import subprocess
from typing import List, Optional
from urllib.parse import urlparse

from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import messages


def quantize_sample_rate(codec: str,
                         sample_rate: int,
                         limit_to_48k: bool = False) -> int:
    """Takes an arbitrary sample rate and aligns it to a standard value.

    It does this by rounding up to the next standard value, while staying below
    a reasonable maximum for the specified codec.

    Args:
        codec: The name of the codec in use.
        sample_rate: The original sample rate.

    Returns:
        An integer sample rate that has been aligned to the closest standard
        value.
    """
    # The behavior as implemented here differs from the legacy behavior.
    # The audio.py legacy behavior excluding no96k codecs was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100   Sample rates < 44100 would jump to 48000.
    #  43000 < x <= 72000  --> 48000
    #  72000 < x <= 90000  --> 88200
    #  90000 < x <= 96000  --> 96000
    #  96000 < x <= 176000 --> 176000
    # 176000 < x           --> 192000
    #
    # For no96k codecs (ogg and mp3), it was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100
    #  43000 < x <= 72000  --> 48000
    #  72000 < x <= 90000  --> 88200   Illegal sample rate for ogg or mp3.
    #  90000 < x <= 96000  --> 48000
    #  96000 < x <= 176000 --> 48000
    # 176000 < x           --> 48000
    #
    # The node.py legacy behavior was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100
    #  43000 < x <= 72000  --> 48000
    #  72000 < x           --> 48000 for no96k, x (unbounded) otherwise.

    # Target rates must be sorted in increasing order.
    target_rates: List[int]
    if limit_to_48k:
        target_rates = constants.MAX_48K_SAMPLE_RATES
    else:
        target_rates = constants.sample_rates_for_codec(codec)

    if sample_rate in target_rates:
        return sample_rate

    for target_rate in target_rates:
        if sample_rate < target_rate:
            # Because we're traversing in increasing order, the first time we
            # find a target_rate that's greater than the sample rate, we know
            # that's the next-largest value, so we can return that immediately.
            messages.print_samplerate_warning(codec)
            return target_rate

    # If we make it to this point, sample_rate is above the max target_rate, so
    # we just clamp to the max target_rate.
    messages.print_samplerate_warning(codec)
    print(colors.warning("Sample rate set to maximum!"))
    return target_rates[-1]


def clamp_bitrate(codec: str, bitrate: Optional[int]) -> int:
    # Legacy logic (also used str for bitrate rather than int):
    # if bitrate == "192" -> "192k"
    # elif bitrate == "None" -> pass
    # else
    #   if codec == "mp3" and bitrate > 320 -> "320" + warning
    #   elif codec == "ogg" and bitrate > 500 -> "500" + warning
    #   elif codec == "aac" and bitrate < 500 -> "500" + warning
    #   else -> bitrate + "k"

    if bitrate is None:
        print(colors.warning("Setting bitrate to default of "
                             f"{constants.DEFAULT_BITRATE}"))
        return constants.DEFAULT_BITRATE

    if bitrate <= 0:
        print(colors.warning(f"Bitrate of {bitrate} was invalid; setting to "
                             f"{constants.DEFAULT_BITRATE}"))
        return constants.DEFAULT_BITRATE

    max_bitrate_for_codec: dict[str, int] = {
        "mp3": 320,
        "ogg": 500,
        "aac": 500,
    }
    max_bitrate: Optional[int] = max_bitrate_for_codec.get(codec, None)

    if max_bitrate is None:
        # codec bitrate is unlimited.
        return bitrate

    if bitrate > max_bitrate:
        print(colors.warning(
            f"Configured bitrate {bitrate} exceeds max {max_bitrate} for "
            f"{codec} codec; setting to max."
        ))
        return max_bitrate

    return bitrate


def terminate() -> None:
    """Unwind through the owner's finally blocks instead of killing the interpreter."""
    raise RuntimeError("Casting could not be started; see the preceding diagnostic")


def del_tmp(debug: bool = False) -> None:
    """Compatibility no-op: sessions no longer create global /tmp files."""


def is_installed(name, path, debug) -> bool:
    PATH = path
    iterate = PATH.split(":")
    for item in iterate:
        verifyif = str(item + "/" + name)
        if os.path.exists(verifyif) is False:
            continue
        else:
            if debug is True:
                print("Program %s found in %s." % (name, verifyif))
            return True
    return False


def check_url(url):
    try:
        result = urlparse(url)
        _ = result.port  # Validate malformed and out-of-range ports.
        return (result.scheme in {"http", "https"} and bool(result.hostname)
                and not any(c.isspace() for c in url))
    except (TypeError, ValueError):
        return False


def writePidFile() -> None:
    """Retained for older launchers; no filesystem IPC is required."""


def checkmktmp() -> None:
    """Retained for older launchers; never delete another session's files."""


def probe_media(name):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(name)], capture_output=True, text=True,
        timeout=30, check=True,
    )
    return json.loads(result.stdout)


def check_file_info(name, what=None):
    video = next((s for s in probe_media(name).get("streams", [])
                  if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("The input contains no video stream")
    if what == "bit-depth":
        return video.get("pix_fmt")
    if what == "resolution":
        return f"{video['height']}p"
    return video


def get_effective_ip(platform, host_override=None, fallback_ip="127.0.0.1"):
    if host_override is None:
        return resolve_ip(platform, fallback_ip=fallback_ip)
    else:
        return host_override


def resolve_ip(platform, fallback_ip):
    if platform == "Linux":
        resolved_ip = _resolve_ip_linux()
    else:
        resolved_ip = _resolve_ip_nonlinux()
    if resolved_ip is None:
        resolved_ip = fallback_ip
    return resolved_ip


def _resolve_ip_linux():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return _get_first_network_ip_by_netifaces()


def _resolve_ip_nonlinux():
    return _resolve_ip_linux()


def _get_first_network_ip_by_netifaces():
    # Retain the helper name without the unmaintained dependency.
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family == socket.AF_INET and not address.address.startswith("127."):
                return address.address
    return None


def address_for_receiver(host):
    """Choose the route's source address without sending application data."""
    for family, kind, proto, _, destination in socket.getaddrinfo(
            host, 8009, type=socket.SOCK_DGRAM):
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.connect(destination)
                return sock.getsockname()[0]
        except OSError:
            continue
    raise OSError(f"No route to receiver {host}")


def http_url(host, port, path="/stream"):
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{authority}:{port}{path}"
