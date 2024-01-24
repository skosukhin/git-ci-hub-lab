import os
import random
import string
import tempfile
import uuid

from common import TAG, BRANCH, git_config, tmp_git_remote

description = "deletes a git reference from the remote repository"


def setup_parser(parser):
    parser.add_argument(
        "--remote-url", required=True, help="remote repository URL"
    )
    parser.add_argument(
        "--username",
        default="token",
        help="remote repository username (default: '%(default)s')",
    )
    parser.add_argument(
        "--password",
        help="remote repository password (default: $GCHL_PASSWORD)",
    )
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


def cmd(args):
    # Local import of a non-standard package, which makes it possible to get the
    # help message even if the package is not available:
    from git import Repo

    # Name for the credential section in the git configuration:
    credential_section_name = 'credential "{0}"'.format(args.remote_url)

    # Required modifications of the git configuration:
    required_config = {
        "repository": {credential_section_name: {"username": args.username}}
    }

    # Default environment variable with the password to the remote repository:
    password_variable = "GCHL_PASSWORD"

    # If the password is provided, generate a temporary environment variable
    # name:
    if args.password is not None:
        password_variable = "{0}{1}".format(
            # The first symbol must be a letter:
            random.choice(string.ascii_lowercase),
            # The rest is a UUID without the hyphens:
            uuid.uuid4().hex[1:],
        )
    required_config["repository"][credential_section_name]["helper"] = (
        '"!f() {{'
        ' test \\"${{1}}\\" = get && echo \\"password=${{{0}}}\\"; '
        '}}; f"'.format(password_variable)
    )

    with tempfile.TemporaryDirectory(prefix="ghcl-") as d:
        repo = Repo.init(d, mkdir=False)
        with git_config(repo, required_config):
            with tmp_git_remote(repo, args.remote_url) as remote:
                if args.password is not None:
                    os.environ[password_variable] = args.password
                try:
                    if args.ref_type == BRANCH:
                        namespace = "heads"
                    elif args.ref_type == TAG:
                        namespace = "tags"
                    else:
                        raise AssertionError(
                            "unexpected reference type {0}".format(
                                args.ref_type
                            )
                        )

                    remote.push(
                        ":refs/{0}/{1}".format(namespace, args.ref_name)
                    ).raise_if_error()
                except Exception:
                    raise
                finally:
                    if args.password is not None:
                        os.environ.pop(password_variable, None)
