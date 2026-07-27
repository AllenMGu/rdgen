import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .custom_config import build_custom_config
from .forms import GenerateForm
from .views import _generator_form, _server_public_key


REQUESTED_FIELDS = {
    "ui_mode",
    "platform",
    "version",
    "exename",
    "appname",
    "androidappid",
    "direction",
    "installation",
    "settings",
    "serverIP",
    "RS_PUB_KEY",
    "apiServer",
    "urlLink",
    "downloadLink",
    "updateLink",
    "compname",
    "passApproveMode",
    "permanentPassword",
    "unlockPin",
    "denyLan",
    "enableDirectIP",
    "autoClose",
    "hideSecuritySettings",
    "hideNetworkSettings",
    "hideServerSettings",
    "hideRemotePrinterSettings",
    "remove_preset_password_warning",
    "iconfile",
    "logofile",
    "privacy_wallpaper",
    "theme",
    "themeDorO",
    "image_quality",
    "custom_fps",
    "permissionsType",
    "enableKeyboard",
    "enableClipboard",
    "enableFileTransfer",
    "enableTCP",
    "enableRemoteRestart",
    "enableRecording",
    "enableBlockingInput",
    "enableRemoteModi",
    "enableCamera",
    "enableTerminal",
    "delayFix",
    "defaultManual",
    "overrideManual",
    "allowHostnameAsId",
    "disable_check_update",
    "hide_powered_by_me",
    "enable_udp_punch",
    "enable_ipv6_punch",
    "enable_file_copy_paste",
    "hide_account",
    "hideProxySettings",
    "hideWebsocketSettings",
    "hidecm",
    "enableAudio",
    "enablePrinter",
    "removeWallpaper",
    "cycleMonitor",
    "xOffline",
    "hide_chat_voice",
    "collapse_toolbar",
    "privacy_mode",
    "hide_username_on_card",
    "view_style",
    "hide_sensitive_ui",
    "hideTray",
    "hidePassword",
    "hideMenuBar",
    "hideQuit",
    "addcopy",
    "applyprivacy",
    "passpolicy",
    "hideService_Start_Stop",
    "allow_numeric_one_time_password",
    "no_uninstall",
    "disable_install",
    "allowD3dRender",
    "viewOnly",
    "use_texture_render",
    "pre_elevate_service",
    "sync_init_clipboard",
}


class GenerateFormTests(SimpleTestCase):
    def test_all_requested_json_fields_are_supported(self):
        self.assertEqual(set(), REQUESTED_FIELDS - set(GenerateForm.base_fields))

    def test_1_4_9_json_payload_is_valid(self):
        request = RequestFactory().post(
            "/generator",
            data=json.dumps(
                {
                    "platform": "windows",
                    "version": "1.4.9",
                    "exename": "example",
                    "appname": "ExampleDesk",
                    "direction": "both",
                    "installation": "installationY",
                    "settings": "settingsN",
                    "serverIP": "rustdesk.example.com",
                    "RS_PUB_KEY": "QUJDRA==",
                    "apiServer": "https://rustdesk.example.com",
                    "theme": "system",
                    "themeDorO": "default",
                    "passApproveMode": "password-click",
                    "permissionsType": "custom",
                    "image_quality": "balanced",
                    "custom_fps": "30",
                    "view_style": False,
                    "privacy_wallpaper": {},
                }
            ),
            content_type="application/json",
        )
        form, is_json = _generator_form(request)
        self.assertTrue(is_json)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual("", form.cleaned_data["view_style"])
        self.assertEqual("", form.cleaned_data["privacy_wallpaper"])

    @override_settings(RUSTDESK_PUBLIC_KEY_FILE="/server/id_ed25519.pub")
    @patch("rdgenerator.views.Path.read_text")
    def test_reads_integrated_server_public_key(self, read_text):
        read_text.return_value = "S2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="
        self.assertEqual(read_text.return_value, _server_public_key())


class CustomConfigTests(SimpleTestCase):
    def test_maps_requested_options_to_rustdesk_schema(self):
        config = build_custom_config(
            {
                "appname": "CutiaRustDesk",
                "direction": "both",
                "installation": "installationY",
                "settings": "settingsN",
                "permanentPassword": "example-only",
                "permissionsType": "custom",
                "enableKeyboard": True,
                "enableClipboard": True,
                "enableFileTransfer": True,
                "enableAudio": False,
                "enableTCP": True,
                "enableRemoteRestart": True,
                "enableRecording": True,
                "enableBlockingInput": True,
                "enableRemoteModi": True,
                "enablePrinter": False,
                "enableCamera": True,
                "enableTerminal": True,
                "denyLan": True,
                "enableDirectIP": True,
                "autoClose": True,
                "hidecm": False,
                "removeWallpaper": False,
                "remove_preset_password_warning": True,
                "hideSecuritySettings": True,
                "hideNetworkSettings": True,
                "hideServerSettings": True,
                "hideRemotePrinterSettings": True,
                "allowHostnameAsId": True,
                "disable_check_update": True,
                "hide_powered_by_me": True,
                "enable_udp_punch": True,
                "enable_ipv6_punch": True,
                "enable_file_copy_paste": True,
                "image_quality": "balanced",
                "custom_fps": 30,
                "allow_numeric_one_time_password": False,
                "defaultManual": "custom-setting=custom-value",
            }
        )

        self.assertEqual("CutiaRustDesk", config["app-name"])
        self.assertEqual("Y", config["disable-settings"])
        self.assertEqual("example-only", config["password"])
        defaults = config["default-settings"]
        self.assertEqual("N", defaults["enable-lan-discovery"])
        self.assertEqual("Y", defaults["direct-server"])
        self.assertEqual("Y", defaults["remove-preset-password-warning"])
        self.assertEqual("Y", defaults["hide-security-settings"])
        self.assertEqual("N", defaults["enable-check-update"])
        self.assertEqual("Y", defaults["enable-udp-punch"])
        self.assertEqual("Y", defaults["enable-file-copy-paste"])
        self.assertEqual("balanced", defaults["image-quality"])
        self.assertEqual("30", defaults["custom-fps"])
        self.assertEqual("custom-value", defaults["custom-setting"])
