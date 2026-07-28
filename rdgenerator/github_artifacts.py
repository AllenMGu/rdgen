import os
import re
import secrets
import shutil
import zipfile
from pathlib import Path

import requests
from django.conf import settings


SUPPORTED_OUTPUTS = {".exe", ".msi"}
SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
TERMINAL_FAILURES = {
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "timed_out",
}


def _headers():
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.GHBEARER}",
        "X-GitHub-Api-Version": "2026-03-10",
    }


def _api_url(path):
    return (
        f"https://api.github.com/repos/{settings.GHUSER}/"
        f"{settings.REPONAME}{path}"
    )


def _valid_output_name(value):
    name = str(value or "")
    return bool(
        name
        and Path(name).name == name
        and SAFE_OUTPUT_NAME.fullmatch(name)
        and Path(name).suffix.lower() in SUPPORTED_OUTPUTS
    )


def _has_downloaded_outputs(build_id):
    directory = Path(settings.ARTIFACT_ROOT) / str(build_id)
    return directory.is_dir() and any(
        path.is_file()
        and not path.is_symlink()
        and _valid_output_name(path.name)
        for path in directory.iterdir()
    )


def _request_json(path):
    response = requests.get(
        _api_url(path),
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _download_artifact(archive_url, build_id):
    response = requests.get(
        archive_url,
        headers=_headers(),
        stream=True,
        timeout=(30, 900),
    )
    response.raise_for_status()

    artifact_root = Path(settings.ARTIFACT_ROOT)
    artifact_root.mkdir(parents=True, exist_ok=True)
    destination = artifact_root / str(build_id)
    token = secrets.token_hex(8)
    staging = artifact_root / f".{build_id}.{token}.download"
    archive_path = artifact_root / f".{build_id}.{token}.zip"
    staging.mkdir()
    try:
        with archive_path.open("wb") as target:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    target.write(chunk)

        saved = []
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                name = Path(member.filename).name
                if member.is_dir() or not _valid_output_name(name):
                    continue
                output = staging / name
                with archive.open(member) as source, output.open("wb") as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                saved.append(name)
        if not saved:
            raise ValueError("GitHub artifact did not contain an EXE or MSI")
        destination.mkdir(parents=True, exist_ok=True)
        for name in saved:
            os.replace(staging / name, destination / name)
        return saved
    finally:
        archive_path.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def sync_github_run(github_run):
    if not github_run.github_run_id:
        return False
    if _has_downloaded_outputs(github_run.uuid):
        if github_run.status != "success":
            github_run.status = "success"
            github_run.save(update_fields=["status"])
        return True

    run = _request_json(f"/actions/runs/{github_run.github_run_id}")
    if run.get("status") != "completed":
        status = run.get("status") or "in_progress"
        if github_run.status != status:
            github_run.status = status
            github_run.save(update_fields=["status"])
        return False

    conclusion = run.get("conclusion") or "failure"
    if conclusion != "success":
        github_run.status = conclusion
        github_run.save(update_fields=["status"])
        return False

    payload = _request_json(
        f"/actions/runs/{github_run.github_run_id}/artifacts?per_page=100"
    )
    expected_name = f"rdgen-{github_run.uuid}"
    artifact = next(
        (
            item
            for item in payload.get("artifacts", [])
            if item.get("name") == expected_name and not item.get("expired")
        ),
        None,
    )
    if not artifact:
        if github_run.status != "artifact_pending":
            github_run.status = "artifact_pending"
            github_run.save(update_fields=["status"])
        return False

    github_run.status = "downloading_artifacts"
    github_run.save(update_fields=["status"])
    _download_artifact(artifact["archive_download_url"], github_run.uuid)
    github_run.status = "success"
    github_run.save(update_fields=["status"])
    return True
