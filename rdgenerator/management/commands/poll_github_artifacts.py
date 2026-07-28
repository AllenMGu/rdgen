import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from rdgenerator.github_artifacts import TERMINAL_FAILURES, sync_github_run
from rdgenerator.models import GithubRun


class Command(BaseCommand):
    help = "Poll GitHub Actions and download completed EXE/MSI artifacts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Poll all active builds once and exit.",
        )

    def handle(self, *args, **options):
        interval = max(10, int(settings.GITHUB_POLL_INTERVAL))
        terminal = TERMINAL_FAILURES | {"success"}
        while True:
            active_runs = GithubRun.objects.exclude(status__in=terminal)
            for github_run in active_runs.iterator():
                try:
                    sync_github_run(github_run)
                except (OSError, ValueError, requests.RequestException) as exc:
                    self.stderr.write(
                        f"rdgen poll failed for {github_run.uuid}: {exc}"
                    )
            if options["once"]:
                return
            time.sleep(interval)
