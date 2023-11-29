description = "deletes a git reference from GitLab repository"

BRANCH = "branch"
TAG = "tag"


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument("--token", required=True, help="GitLab access token")
    ref_types = [TAG, BRANCH]
    parser.add_argument(
        "--ref-type",
        required=True,
        metavar="REF_TYPE {{{0}}}".format(",".join(ref_types)),
        choices=ref_types,
        help="type of the reference to delete",
    )
    parser.add_argument(
        "--ref-name",
        required=True,
        help="name of the reference to delete",
    )


def cmd(args):
    # Local import of a non-standard package, which makes it possible to get the
    # help message even if the package is not available:
    import gitlab

    server = gitlab.Gitlab(
        url=args.server_url,
        private_token=args.token,
    )

    project = server.projects.get(args.project_name)

    if args.ref_type == BRANCH:
        project.branches.delete(args.ref_name)
    elif args.ref_type == TAG:
        project.tags.delete(args.ref_name)
    else:
        raise AssertionError(
            "unexpected reference type {0}".format(args.ref_type)
        )
