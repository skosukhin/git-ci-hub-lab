description = "cancels a GitLab CI pipeline"


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument("--token", required=True, help="GitLab access token")
    parser.add_argument(
        "--pipeline-id", required=True, help="ID of the pipeline"
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

    pipeline.cancel()
