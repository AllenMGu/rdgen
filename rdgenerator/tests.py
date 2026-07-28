import json
import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from .custom_config import build_custom_config
from .forms import GenerateForm
from .github_artifacts import sync_github_run
from .models import GithubRun
from .views import (
    _apply_default_permanent_password,
    _generator_form,
    _safe_artifact_name,
    _server_public_key,
    _upload_input_blob,
)


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

    @override_settings(DEFAULT_PERMANENT_PASSWORD="server-side-example")
    def test_uses_server_default_when_payload_password_is_empty(self):
        cleaned_data = _apply_default_permanent_password(
            {"permanentPassword": ""}
        )
        self.assertEqual(
            "server-side-example",
            cleaned_data["permanentPassword"],
        )

    @override_settings(DEFAULT_PERMANENT_PASSWORD="server-side-example")
    def test_payload_password_overrides_server_default(self):
        cleaned_data = _apply_default_permanent_password(
            {"permanentPassword": "request-example"}
        )
        self.assertEqual("request-example", cleaned_data["permanentPassword"])


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


class ArtifactStorageTests(SimpleTestCase):
    build_id = "6b5d395f-2478-4ca9-8383-34c0057deab8"

    def test_rejects_unauthorized_upload(self):
        with TemporaryDirectory() as artifact_root, override_settings(
            ARTIFACT_ROOT=Path(artifact_root),
            UPLOAD_TOKEN="test-upload-token",
        ):
            response = self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.build_id,
                    "file": SimpleUploadedFile("client.exe", b"binary"),
                },
            )
        self.assertEqual(401, response.status_code)

    def test_uploads_lists_and_streams_saved_artifact(self):
        with TemporaryDirectory() as artifact_root, override_settings(
            ARTIFACT_ROOT=Path(artifact_root),
            UPLOAD_TOKEN="test-upload-token",
        ):
            response = self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.build_id,
                    "file": SimpleUploadedFile("client.exe", b"binary"),
                },
                HTTP_AUTHORIZATION="Bearer test-upload-token",
            )
            self.assertEqual(201, response.status_code, response.content)
            saved = Path(artifact_root) / self.build_id / "client.exe"
            self.assertEqual(b"binary", saved.read_bytes())

            listing = self.client.get(f"/artifacts?build={self.build_id}")
            self.assertContains(listing, "client.exe")

            json_listing = self.client.get(
                f"/artifacts?build={self.build_id}&format=json"
            )
            self.assertEqual(200, json_listing.status_code)
            payload = json_listing.json()
            self.assertEqual("client.exe", payload["builds"][0]["artifacts"][0]["name"])
            self.assertEqual(
                (
                    f"/api/admin/rdgen/download?uuid={self.build_id}"
                    "&filename=client.exe"
                ),
                payload["builds"][0]["artifacts"][0]["download_url"],
            )

            download = self.client.get(
                f"/download?uuid={self.build_id}&filename=client.exe"
            )
            self.assertEqual(200, download.status_code)
            self.assertEqual(b"binary", b"".join(download.streaming_content))

    def test_rejects_unsafe_artifact_names(self):
        self.assertIsNone(_safe_artifact_name("../client.exe"))
        self.assertIsNone(_safe_artifact_name("client.txt"))


class GitHubInputBlobTests(SimpleTestCase):
    @override_settings(
        GHUSER="AllenMGu",
        REPONAME="rdgen",
        GHBEARER="test-token",
    )
    @patch("rdgenerator.views.requests.post")
    def test_uploads_encrypted_input_as_unreferenced_git_blob(self, post):
        response = Mock()
        response.json.return_value = {"sha": "a" * 40}
        response.raise_for_status.return_value = None
        post.return_value = response

        with TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.zip"
            path.write_bytes(b"encrypted")
            self.assertEqual("a" * 40, _upload_input_blob(path))

        request = post.call_args
        self.assertTrue(request.kwargs["json"]["content"])
        self.assertEqual("base64", request.kwargs["json"]["encoding"])
        self.assertNotIn(b"encrypted", str(request.kwargs).encode())


class GitHubArtifactPollingTests(TestCase):
    build_id = "6b5d395f-2478-4ca9-8383-34c0057deab8"

    @override_settings(
        GHUSER="AllenMGu",
        REPONAME="rdgen",
        GHBEARER="test-token",
    )
    @patch("rdgenerator.github_artifacts.requests.get")
    @patch("rdgenerator.github_artifacts._request_json")
    def test_downloads_matching_run_artifact_to_build_directory(
        self,
        request_json,
        get,
    ):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("CutiaRustDesk.exe", b"exe")
            output.writestr("CutiaRustDesk.msi", b"msi")
            output.writestr("ignored.txt", b"ignored")

        response = Mock()
        response.iter_content.return_value = [archive.getvalue()]
        response.raise_for_status.return_value = None
        get.return_value = response
        request_json.side_effect = [
            {"status": "completed", "conclusion": "success"},
            {
                "artifacts": [
                    {
                        "name": f"rdgen-{self.build_id}",
                        "expired": False,
                        "archive_download_url": "https://api.github.test/artifact.zip",
                    }
                ]
            },
        ]

        github_run = GithubRun.objects.create(
            id=1,
            uuid=self.build_id,
            status="in_progress",
            github_run_id=12345,
        )
        with TemporaryDirectory() as artifact_root, override_settings(
            ARTIFACT_ROOT=Path(artifact_root)
        ):
            self.assertTrue(sync_github_run(github_run))
            destination = Path(artifact_root) / self.build_id
            self.assertEqual(b"exe", (destination / "CutiaRustDesk.exe").read_bytes())
            self.assertEqual(b"msi", (destination / "CutiaRustDesk.msi").read_bytes())
            self.assertFalse((destination / "ignored.txt").exists())

        github_run.refresh_from_db()
        self.assertEqual("success", github_run.status)
