"""Parses arguments for mkchromecast.

This is intended to be moved to `bin/mkchromecast` eventually, since it defines
the command-line interface.
"""
# This file is part of Mkchromecast.

import argparse
import os

from mkchromecast import constants
from mkchromecast.resolution import resolutions


def invalid_arg(error_msg: str):
    """Returns a lambda that will raise an ArgumentTypeError when called.

    Args:
        error_msg: The error message that will be used to construct the
            ArgumentTypeError.
    """

    def raise_arg_type_error(_value):
        raise argparse.ArgumentTypeError(error_msg)
    return raise_arg_type_error


Parser = argparse.ArgumentParser(
    description="""
    This is a program to cast your macOS audio, or Linux audio to your Google
    Cast devices.

    It is written in Python, and it can stream via node.js, ffmpeg, parec
    (Linux pulseaudio users), or ALSA (Linux users). Mkchromecast is capable of
    using lossy and lossless audio formats provided that ffmpeg or parec is
    installed.  Additionally, a system tray menu is available.

    Linux users that have installed the debian package need to launch the
    command `mkchromecast`, e.g.:

        mkchromecast

    whereas, installation from source needs users to go inside the cloned git
    repository and execute:

        mkchromecast

    The two examples above will make Mkchromecast streams with node.js (or
    parec in Linux) together with mp3 audio coding format at a sample rate of
    44100Hz and an average bitrate of 192k (defaults). These defaults can be
    changed using the --sample-rate and -b flags. It is useful to modify these
    parameters when your wireless router is not very powerful, or in the case
    you don't want to degrade the sound quality. For more information visit the
    wiki and the FAQ https://github.com/muammar/mkchromecast/wiki/.


    """,
    formatter_class=argparse.RawTextHelpFormatter,
)

# All of the "do this action" arguments.
_ActionGroupContainer = Parser.add_argument_group(
    title='Actions',
    description=('Optional actions that mkchromecast can perform.  These are '
                 'mutually-exclusive.'),
)
_ActionGroup = _ActionGroupContainer.add_mutually_exclusive_group()

Parser.add_argument(
    "--alsa-device",
    type=str,
    default=None,
    help="""
    Set the ALSA device name. This option is useful when you are using pure
    ALSA in your system.

    Example:
        mkchromecast --encoder-backend ffmpeg --alsa-device hw:2,1

    It only works for the ffmpeg backend, and it is not useful for pulseaudio
    users. For more information read the README.Debian file shipped in the
    Debian package or https://github.com/muammar/mkchromecast/wiki/ALSA.
    """,
)

Parser.add_argument(
    "-b",
    "--bitrate",
    type=int,
    default=192,
    help="""
    Set the audio encoder's bitrate. The default is set to be 192k average
    bitrate.  Will be ignored for lossless codecs like flac or wav.

    Example:

    ffmpeg:
        mkchromecast --encoder-backend ffmpeg -c ogg -b 128

    node:
        mkchromecast  -b 128

    This option works with all backends. The example above sets the average
    bitrate to 128k.
    """,
)

Parser.add_argument(
    "--chunk-size",
    type=int,
    default=64,
    help="""
    Set the chunk size base for streaming in the Flask server. Default to 64.
    This option only works when using the ffmpeg backend. This number is the
    base to set both the buffer_size (defined by 2 * chunk_size**2) in Flask
    server and the frame_size (defined by 32 * chunk_size).

    Example:

    ffmpeg:
        mkchromecast --encoder-backend ffmpeg -c ogg -b 128 --chunk-size 2048

    """,
)

Parser.add_argument(
    "-c",
    "--codec",
    type=str,
    default="mp3",
    help="""
    Set the audio codec.

    Example:
        mkchromecast --encoder-backend ffmpeg -c ogg

    Possible codecs:
        - mp3  [192k]   MPEG Audio Layer III (default)
        - ogg  [192k]   Ogg Vorbis
        - aac  [192k]   Advanced Audio Coding (AAC)
        - wav  [HQ]     Waveform Audio File Format
        - flac [HQ]     Free Lossless Audio Codec

    This option only works for the ffmpeg and parec backends.
    """,
)

Parser.add_argument(
    "--command",
    type=str,
    default=None,
    help="""
    Set an ffmpeg command for streaming video.

    Example:
        python3 mkchromecast.py --video --command 'ffmpeg -re -i \
        /path/to/myvideo.mp4 -map_chapters -1 -vcodec libx264 -preset ultrafast \
        -tune zerolatency -maxrate 10000k -bufsize 20000k -pix_fmt yuv420p -g \
        60 -f mp4 -max_muxing_queue_size 9999 -movflags \
        frag_keyframe+empty_moov pipe:1'

    Note that for the output you have to use pipe:1 to stream. This option only
    works for the ffmpeg backend.
    """,
)

Parser.add_argument(
    "--control",
    action="store_true",
    default=False,
    help="""
    Control some actions of your Google Cast Devices. Use the 'u' and 'd' keys
    to perform volume up and volume down respectively, or press 'p' and 'r' to
    pause and resume cast process (only works with ffmpeg). Note that to kill
    the application using this option, you need to press the 'q' key or
    'Ctrl-c'.
    """,
)

Parser.add_argument(
    "--debug",
    action="store_true",
    help="""
    Option for debugging purposes.
    """,
)

_ActionGroup.add_argument(
    "-d",
    "--discover",
    action="store_true",
    default=False,
    help="""
    Use this option if you want to know the friendly name of a Google Cast
    device.
    """,
)

Parser.add_argument(
    "--display",
    type=str,
    default=os.environ.get("DISPLAY", ":0"),
    help="""
    Set the DISPLAY for X11 screen captures. Defaults to current environment
    value of DISPLAY or ':0' if DISPLAY is unset. Ignored under Wayland, where
    the monitor is chosen via the desktop portal picker.
    """,
)

Parser.add_argument(
    "--encoder-backend",
    type=str,
    default=None,
    choices=constants.ALL_BACKENDS,
    help="""
    Set the backend for all encoders.
    Possible backends:
        - node (default in macOS)
        - parec (default in Linux)
        - ffmpeg

    Example:
        mkchromecast --encoder-backend ffmpeg
    """,
)

Parser.add_argument(
    "--hijack",
    action="store_true",
    default=False,
    help="""
    This flag monitors if connection with google cast has been lost, and try to
    hijack it.
    """,
)

Parser.add_argument(
    "--host",
    type=str,
    default=None,
    help="""
    Set the ip of the local host. This option is useful if the local ip of your
    computer is not being detected correctly, or in the case you have more than
    one network device available.

    Example:
        mkchromecast --encoder-backend ffmpeg --host 192.168.1.1

    You can pass it to all available backends.
    """,
)

_ActionGroup.add_argument(
    "-i",
    "--input-file",
    type=str,
    default=None,
    help="""
    Stream a file.

    Example:
        mkchromecast -i /path/to/file.mp4
    """,
)

Parser.add_argument(
    "--loop",
    action="store_true",
    default=False,
    help="""
    Loop video indefinitely while streaming
    """,
)

Parser.add_argument(
    "--mtype",
    type=str,
    default=None,
    help="""
    MIME type for --source-url or a custom --command. Generated media sets
    its own type. Example: --source-url https://example.org/music.mp3
    --mtype audio/mpeg
    """,
)

Parser.add_argument(
    "-n",
    "--name",
    type=str,
    default=None,
    help="""
    Use this option if you know the name of the Google Cast you want to
    connect.

    Example:
        mkchromecast -n mychromecast
    """,
)

Parser.add_argument(
    "--notifications",
    action="store_true",
    help="""
    Use this flag to enable the notifications.
    """,
)

Parser.add_argument(
    "-p",
    "--port",
    type=int,
    default=5000,
    help="""
    Set the listening port for local webserver.

    Example:

    ffmpeg:
        mkchromecast --encoder-backend ffmpeg -p 5100

    """,
)


_ActionGroup.add_argument(
    "-r",
    "--reset",
    action="store_true",
    help="""
    When the application fails, and you have no audio in your computer, use
    this option to reset the computer's audio.
    """,
)


Parser.add_argument(
    "--resolution",
    type=str,
    default=None,
    help="""
    Set the resolution of the streamed video. The following resolutions are
    supported:

    """
    + "\n".join("    - {0} ({2}).".format(k, *v) for k, v in resolutions.items()),
)

Parser.add_argument(
    "-s",
    "--select-device",
    action="store_true",
    help="""
    If you have more than one Google Cast device use this option.
    """,
)

Parser.add_argument(
    "--sample-rate",
    type=int,
    default=44100,
    help="""
    Set the sample rate. The default sample rate obtained from avfoundation
    audio device input in ffmpeg using BlackHole for macOS is 44100Hz (in
    Linux can be 44100Hz or 48000Hz). You can change this in the Audio MIDI
    Setup in the "BlackHole 16ch" audio device. You need to change the
    "Format" in both input/output from 44100Hz to maximum 96000Hz.  I think
    that more than 48000Hz is not necessary, but this is up to the users'
    preferences.

    Note that re-sampling to higher sample rates is not a good idea. It was
    indeed an issue in the chromecast audio. See: https://goo.gl/yNVODZ.

    Example:

    ffmpeg:
        mkchromecast --encoder-backend ffmpeg -c ogg -b 128 --sample-rate 32000

    node:
        mkchromecast -b 128 --sample-rate 32000

    This option works for both backends. The example above sets the sample rate
    to 32000Hz, and the bitrate to 128k.

    Which sample rate to use?

        - 192000Hz: maximum sampling rate supported in google cast audio
          without using High Dynamic Range. Only supported by aac, wav and flac
          codecs.
        - 96000Hz: maximum sampling rate supported in google cast audio using
          High Dynamic Range. Only supported by aac, wav and flac codecs.
        - 48000Hz: sampling rate of audio in DVDs.
        - 44100Hz: sampling rate of audio CDs giving a 20 kHz maximum
          frequency.
        - 32000Hz: sampling rate of audio quality a little below FM radio
          bandwidth.
        - 22050Hz: sampling rate of audio quality of AM radio.

    For more information see: http://wiki.audacityteam.org/wiki/Sample_Rates.
    """,
)

_ActionGroup.add_argument(
    "--screencast",
    action="store_true",
    default=False,
    help="""
    Use this flag to cast your Desktop Google cast devices. It is only working
    with ffmpeg. You may want to you use the --resolution option together with
    this flag.

    Examples:

        mkchromecast --video --screencast
    """,
)

Parser.add_argument(
    "--capture-backend", choices=("auto", "cinnamon"), default="auto",
    help="Screen capture: auto (X11/Wayland) or experimental Cinnamon compositor capture.",
)

Parser.add_argument(
    "--seek",
    type=str,
    default=None,
    help="""
    Option to seeking when casting video. The format to set the time is
    HH:MM:SS.

    Example:
        mkchromecast --video -i "/path/to/file.mp4" --seek 00:23:00

    """,
)

Parser.add_argument(
    "--segment-time",
    type=int,
    default=None,
    help="""
    Unsupported legacy option. The live HTTP pipeline does not implement
    segmented streaming; supplying this option reports an error.

    """,
)

_ActionGroup.add_argument(
    "--source-url",
    type=str,
    default=None,
    help="""
    This option allows you to pass any source URL to your Google Cast device.
    You have to specify the codec with -c flag when using it.

    Example:

    Source URL, port and extension:
        mkchromecast --source-url http://192.99.131.205:8000/pvfm1.ogg -c ogg --control

    Source URL, no port, and extension:
        mkchromecast --source-url http://example.com/name.ogg -c ogg --control

    Source URL without extension:
        mkchromecast --source-url http://example.com/name -c aac --control

    Supported source URLs are:

        - http://url:port/name.mp3
        - http://url:port/name.ogg
        - http://url:port/name.mp4 (use the aac codec)
        - http://url:port/name.wav
        - http://url:port/name.flac

    .m3u or .pls are not yet available.
    """,
)

Parser.add_argument(
    "--subtitles",
    type=str,
    default=None,
    help="""
    Set subtitles.
    """,
)

_ActionGroup.add_argument(
    "-t",
    "--tray",
    action="store_true",
    help="""
    This option let you launch Mkchromecast as a systray menu (beta).
    """,
)

Parser.add_argument(
    "--tries",
    type=int,
    default=None,
    help="""
    Limit the number of times the underlying socket associated with your
    Chromecast objects will retry connecting
    """,
)

Parser.add_argument(
    "--update",
    type=invalid_arg("Argument dropped."),
    help="Do not use.  Argument dropped.",
)

_ActionGroup.add_argument(
    "-v",
    "--version",
    action="store_true",
    help="""
    Show the version""",
)

Parser.add_argument(
    "--vcodec",
    type=str,
    default="libx264",
    help="""
    Set a custom vcodec for ffmpeg when capturing screen.  Defaults to libx264
    """,
)

# TODO(xsdg): Probably best to replace this with --suppress-video.  Otherwise,
# we should either auto-detect audio-only usecases, or always send video.
Parser.add_argument(
    "--video",
    action="store_true",
    default=False,
    help=r"""
    Use this flag to cast video to your Google cast devices. It is only working
    with ffmpeg.

    Examples:

    Cast a file:
        mkchromecast --video -i "/path/to/file.mp4"

    Cast from source-url:
        mkchromecast --source-url http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4 -c mp4 --control --video

    Cast a youtube-url:
        mkchromecast -y https://www.youtube.com/watch\?v\=VuMBaAZn3II --video

    """,
)
Parser.add_argument(
    "--volume",
    type=invalid_arg("Renamed to --control"),
    help="Do not use.  Renamed to --control.",
)

_ActionGroup.add_argument(
    "-y",
    "--youtube",
    type=str,
    default=None,
    help="""
    Stream from sources supported by yt-dlp. This option needs
    the yt-dlp package, and it also gives you access to all its
    supported websites such as Dailymotion and Vimeo.

    For a comprehensive list, check:
        https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md.

    Example:
        mkchromecast -y https://www.youtube.com/watch?v=NVvAJhZVBTc

    HTTP and HTTPS URLs are accepted.
        """,
)

Parser.add_argument(
    "--fps",
    type=str,
    default="25",
    help="""
    Frames per second to use when --screencast is used. Defaults to 25.
    """,
)

Parser.add_argument("--device-id", help="Stable Chromecast UUID or Sonos UID")
Parser.add_argument("--receiver", choices=["chromecast", "sonos"], default="chromecast",
                    help="Receiver family (Sonos requires the sonos extra)")
Parser.add_argument("--discovery-timeout", type=float, default=10.0)
Parser.add_argument("--startup-timeout", type=float, default=330.0,
                    help="Startup deadline including any desktop portal prompt")
