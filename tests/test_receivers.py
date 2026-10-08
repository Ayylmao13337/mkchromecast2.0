from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import Mock, patch
from mkchromecast.cast import Casting, AvailableDevice
from mkchromecast.constants import OpMode


def settings():
    return SimpleNamespace(host=None, device_id=None, device_name=None, select_device=False,
                           operation=OpMode.AUDIOCAST, discovery_timeout=.01, tries=1, debug=False, port=5000)


class CastOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.conf = settings()
        self.cast = Casting(self.conf)
        self.addCleanup(self.cast.close)

    def test_discovery_lists_uuid_without_connecting(self):
        identity = uuid4()
        browser = Mock(devices={identity: SimpleNamespace(friendly_name='TV', host='192.0.2.1')})
        with patch('mkchromecast.cast.zeroconf.Zeroconf'), patch('mkchromecast.cast.pychromecast.CastBrowser', return_value=browser), patch('mkchromecast.cast.pychromecast.get_chromecast_from_cast_info') as connect:
            self.conf.device_id = str(identity)
            self.cast.initialize_cast()
            self.assertEqual(str(identity), self.cast.available_devices[0].id)
            connect.assert_not_called()
            self.cast.close()
            browser.stop_discovery.assert_called_once()

    def test_duplicate_names_require_uuid(self):
        self.cast._devices = [AvailableDevice(0, 'TV', 'Gcast', 'a'), AvailableDevice(1, 'TV', 'Gcast', 'b')]
        self.conf.device_name = 'TV'
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.cast.get_devices()

    def test_stop_does_not_interrupt_another_sender(self):
        device = Mock()
        self.cast.cast = device
        self.cast.ip = '192.0.2.10'
        for content, calls in [('https://other.example/video.mp4', 0), ('http://192.0.2.10:5000/stream', 1)]:
            self.cast._owns_media = True
            device.media_controller.status.content_id = content
            self.cast.stop_cast()
            self.assertEqual(calls, device.media_controller.stop.call_count)
        device.quit_app.assert_not_called()

    def test_uuid_selection_connects_and_routes_to_selected_receiver(self):
        self.cast._devices = [AvailableDevice(0, 'TV', 'Gcast', 'a')]
        self.cast._by_id = {'a': object()}
        self.conf.device_id = 'a'
        device = Mock()
        device.socket_client.host = '192.0.2.1'
        with patch('mkchromecast.cast.pychromecast.get_chromecast_from_cast_info', return_value=device), patch('mkchromecast.utils.address_for_receiver', return_value='192.0.2.10'):
            self.cast.get_devices()
            self.assertEqual('192.0.2.10', self.conf.host)
            device.wait.assert_called_once_with(timeout=30)
        self.cast.close()
        device.disconnect.assert_called_once_with(timeout=5)


class SonosTests(unittest.TestCase):
    def test_coordinator_and_owned_uri(self):
        from mkchromecast.sonos import SonosCasting
        from mkchromecast.media import MediaPlan
        conf = settings()
        conf.device_id = 'RINCON_1'
        receiver = SonosCasting(conf)
        zone = Mock(uid='RINCON_1', player_name='Kitchen', ip_address='192.0.2.2')
        receiver._zones = {zone.uid: zone}
        with patch('mkchromecast.utils.address_for_receiver', return_value='192.0.2.10'):
            receiver.get_devices()
        self.assertIs(zone.group.coordinator, receiver.cast)
        receiver.plan = MediaPlan('audio/mpeg')
        receiver.play_cast()
        receiver.cast.play_uri.assert_called_once_with('http://192.0.2.10:5000/stream', title='Mkchromecast', force_radio=True, timeout=10)
        receiver.cast.get_current_track_info.return_value = {'uri': 'another-track'}
        receiver.stop_cast()
        receiver.cast.stop.assert_not_called()
        receiver.set_volume(1.7)
        self.assertEqual(100, receiver.cast.volume)
