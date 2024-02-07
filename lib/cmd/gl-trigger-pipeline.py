import os

from common import info, warn

description = "triggers a GitLab CI pipeline"


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument(
        "--token", required=True, help="GitLab pipeline trigger token"
    )
    parser.add_argument(
        "--ref-name",
        help="name of the reference (tag or branch) "
        "to trigger the pipeline for",
        required=True,
    )
    parser.add_argument(
        "--expected-sha",
        help="expected prefix of the commit SHA-1 of the triggered pipeline "
        "(default: `%(default)s`)",
        default="",
    )


def cmd(args):
    # Local import of a non-standard package, which makes it possible to get the
    # help message even if the package is not available:
    import gitlab

    server = gitlab.Gitlab(url=args.server_url)

    project = server.projects.get(args.project_name, lazy=True)
    pipeline = project.trigger_pipeline(args.ref_name, args.token)
    info(
        "Pipeline for `{0}` ({1}): {2}".format(
            args.ref_name, pipeline.web_url, pipeline.status
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
            "Pipeline SHA `{0}` does not match the expected SHA `{1}`".format(
                pipeline.sha, args.expected_sha
            )
        )
        pipeline.cancel()
        exit(1)
