import os
import time

from common import PIPELINE_FINAL_STATUSES, PIPELINE_SUCCESS, info, warn

description = "creates a GitLab CI pipeline"


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument("--token", required=True, help="GitLab access token")
    parser.add_argument(
        "--ref-name",
        help="name of the reference (tag or branch) "
        "to create the pipeline for",
        required=True,
    )
    parser.add_argument(
        "--expected-sha",
        help="expected prefix of the commit SHA-1 of the created pipeline "
        "(default: '%(default)s')",
        default="",
    )
    parser.add_argument(
        "--attach",
        action="store_true",
        help="wait for the created pipeline and report its final status "
        "(default: '%(default)s')",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=10,
        help="pipeline status poll timeout in seconds (default: '%(default)s')",
    )


def cmd(args):
    # Local import of a non-standard package, which makes it possible to get the
    # help message even if the package is not available:
    import gitlab

    server = gitlab.Gitlab(
        url=args.server_url,
        private_token=args.token,
    )

    project = server.projects.get(args.project_name, lazy=True)
    pipeline = project.pipelines.create({"ref": args.ref_name})
    info(
        "Pipeline for '{0}' (SHA: {1}): {2} ({3})".format(
            pipeline.ref,
            pipeline.sha[:8],
            pipeline.status,
            pipeline.web_url,
        )
    )

    # TODO: make it more generic
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.writelines(
                [
                    "pipeline-id={0}\n".format(pipeline.get_id()),
                    "pipeline-sha={0}\n".format(pipeline.sha),
                ]
            )

    if not pipeline.sha.startswith(args.expected_sha):
        warn(
            "Pipeline SHA '{0}' does not match the expected SHA '{1}'".format(
                pipeline.sha, args.expected_sha
            )
        )
        pipeline.cancel()
        exit(1)

    if args.attach:
        poll_timeout = 0 if args.poll_timeout < 0 else args.poll_timeout

        while pipeline.status not in PIPELINE_FINAL_STATUSES:
            time.sleep(poll_timeout)
            pipeline.refresh()
            for job in pipeline.jobs.list():
                info(
                    "\tjob '{0}': {1} ({2})".format(
                        job.name, job.status, job.web_url
                    )
                )

        info(
            "Pipeline for '{0}' (SHA: {1}): {2} ({3})".format(
                pipeline.ref,
                pipeline.sha[:8],
                pipeline.status,
                pipeline.web_url,
            )
        )

        exit(pipeline.status != PIPELINE_SUCCESS)
