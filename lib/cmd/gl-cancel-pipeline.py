from common import info, warn

description = "cancels a GitLab CI pipeline"


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument("--token", required=True, help="GitLab access token")
    parser.add_argument(
        "--pipeline-id",
        required=True,
        metavar="PIPELINE_ID",
        help="ID of the pipeline",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="do not fail if PIPELINE_ID could not be cancelled "
        "(default: '%(default)s')",
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
    pipeline = project.pipelines.get(args.pipeline_id, lazy=True)

    try:
        pipeline.cancel()
        info(
            "Pipeline '{0}' is successfully cancelled".format(args.pipeline_id)
        )
    except Exception:
        if args.force:
            warn("Failed to cancel pipeline '{0}'".format(args.pipeline_id))
        else:
            raise
