from common import BRANCH, TAG, GHCLAssertionError, info, warn

description = "deletes a git reference from GitLab repository"


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
        metavar="REF_NAME",
        help="name of the reference to delete",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="do not fail if REF_NAME could not be deleted "
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

    if args.ref_type == BRANCH:
        ref_manager = project.branches
    elif args.ref_type == TAG:
        ref_manager = project.tags
    else:
        raise GHCLAssertionError(
            "unexpected reference type {0}".format(args.ref_type)
        )

    try:
        ref_manager.delete(args.ref_name)
        info(
            "{0}{1} '{2}' is successfully deleted".format(
                args.ref_type[0].upper(), args.ref_type[1:], args.ref_name
            )
        )
    except Exception:
        if args.force:
            warn(
                "Failed to delete {0} '{1}'".format(
                    args.ref_type, args.ref_name
                )
            )
        else:
            raise
