# RDGen, a RustDesk client generator to use with your self-hosted RustDesk server

The client generator is currently hosted [here](https://rdgen.crayoneater.org).
If you would like to host the generator yourself, see [here](setup.md)

## Features

- Embed server and key into client
- Custom app name
- Custom icon/logo
- Set default settings for the client
- Support for rustdesk advanced settings (https://rustdesk.com/docs/en/self-host/client-configuration/advanced-settings/)

## Generate RustDesk clients from command line instead of using a web browser

Save your configuration from the rdgen web interface, or generate your own, then use that json file with [@AlekseyLapunov's rdgen-cli](https://github.com/AlekseyLapunov/rdgen-cli) to build from the command line on Windows, Linux, or MacOS like this: `python rdgen-cli -f my_config.json --set-version 1.4.5 --set-platform windows -s https://rdgen.crayoneater.org`

## Notes

- Icons should be square (256x256 recommended)
- Avoid special characters or non-English characters in app name and file name
- Build time is currently 30 - 45 minutes

## JSON API and custom source forks

`POST /generator` accepts either the browser form or an
`application/json` object. The JSON API accepts the same field names used by
saved generator configurations and returns HTTP `202` with the build UUID and
GitHub workflow details.

Set these environment variables when builds should use a RustDesk fork:

```text
RUSTDESK_REPOSITORY=owner/rustdesk
RUSTDESK_REF=master
```

`RUSTDESK_REF` may be a branch, tag, or full commit SHA. If it is omitted,
rdgen uses `master` for a fork and the selected release tag for the upstream
`rustdesk/rustdesk` repository.

The server public key is accepted as either `key` or `RS_PUB_KEY`. A custom
server address without a public key is rejected instead of silently embedding
RustDesk's public-server key. An integrated deployment may set
`RUSTDESK_PUBLIC_KEY_FILE` to a readable `id_ed25519.pub`; that key is used
when the JSON field is empty.

## Stored build artifacts

Windows builds use an outbound-only transfer flow:

1. rdgen uploads the encrypted build input as an unreferenced Git blob and
   dispatches GitHub Actions with the blob SHA.
2. GitHub Actions downloads and decrypts that blob, compiles the client, and
   uploads the EXE/MSI as an Actions Artifact named `rdgen-<build-uuid>`.
3. `python manage.py poll_github_artifacts` polls active workflow runs and
   downloads the matching artifact into `ARTIFACT_ROOT`.
4. After the EXE/MSI files are safely stored, the poller immediately deletes
   the GitHub Actions Artifact. A failed delete remains in cleanup status and
   is retried on the next polling cycle without downloading the files again.

The generator host therefore does not need a public callback address. Its
fine-grained GitHub token needs repository permissions `Actions: read and
write` and `Contents: read and write`. The Actions permission dispatches and
polls runs; the Contents permission creates the encrypted input blob.

Completed clients are stored below `ARTIFACT_ROOT` (default: `./exe`) using
this layout:

```text
<ARTIFACT_ROOT>/<build-uuid>/<generated-file>
```

Open `/artifacts` to list and download every saved client. Files are streamed
from disk and are not automatically deleted. Protect the generator and
artifact pages with reverse-proxy authentication.

Set `GITHUB_POLL_INTERVAL` to control polling frequency in seconds (default
`60`, minimum effective interval `10`). The integrated S6 image runs this
poller automatically.
