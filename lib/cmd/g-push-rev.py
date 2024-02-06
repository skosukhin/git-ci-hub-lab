import base64
import os
import random
import string
import uuid

from common import (
    TAG,
    BRANCH,
    git_config,
    git_ref_exists_and_unique,
    tmp_git_remote,
    SIGNING_FORMAT_NONE,
    SIGNING_FORMAT_SSH,
)

description = (
    "pushes a git revision from the local repository to the remote one"
)


def setup_parser(parser):
    parser.add_argument(
        "--local-path",
        default=".",
        help="local repository path (default: '%(default)s')",
    )
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
    parser.add_argument(
        "--rev-id",
        default="HEAD",
        help="ID of the revision to push as understood by git-rev-parse "
        "(default: '%(default)s')",
    )
    ref_types = [TAG, BRANCH]
    parser.add_argument(
        "--ref-type",
        metavar="REF_TYPE {{{0}}}".format(",".join(ref_types)),
        choices=ref_types,
        default=TAG,
        help="type of the reference to be used to push REV_ID to the remote "
        "repository (default: '%(default)s')",
    )
    parser.add_argument(
        "--ref-name",
        help="name of the reference to be used to push REV_ID to the remote "
        "repository "
        "(default: arbitrary combination of REF_TYPE and SHA-1 of REV_ID)",
    )
    parser.add_argument(
        "--ref-message",
        help="annotation message of the reference (defaults to 'signed' if "
        "REF_TYPE is '{0}' and REF_SIGNING_FORMAT is not '{1}', "
        "ignored if REF_TYPE is not '{0}')".format(TAG, SIGNING_FORMAT_NONE),
    )
    signing_formats = [SIGNING_FORMAT_NONE, SIGNING_FORMAT_SSH]
    parser.add_argument(
        "--ref-signing-format",
        metavar="REF_SIGNING_FORMAT {{{0}}}".format(",".join(signing_formats)),
        choices=signing_formats,
        default=SIGNING_FORMAT_NONE,
        help="format to be used to sign the reference "
        "(ignored if REF_TYPE is not '{0}', default '%(default)s')".format(TAG),
    )
    parser.add_argument(
        "--ref-signing-key",
        help="base64-encoded key to be used to sign the reference "
        "(ignored if REF_TYPE is not '{0}' or REF_SIGNING_FORMAT is '{1}', "
        "default: $GCHL_REF_SIGNING_KEY)".format(TAG, SIGNING_FORMAT_NONE),
    )
    parser.add_argument(
        "--force-push",
        action="store_true",
        help="force push the reference to the remote repository "
        "(default: '%(default)s')",
    )
    parser.add_argument(
        "--safe-path",
        action="store_true",
        help="add a temporary entry to the 'safe' section in the global git "
        "configuration scope for the LOCAL_PATH , which might be required when "
        "the local repository is created by a different user "
        "(default: '%(default)s')",
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

    # Annotated and signed tags require the committer information:
    if args.ref_type == TAG and (
        args.ref_message or args.ref_signing_format != SIGNING_FORMAT_NONE
    ):
        required_config["repository"]["user"] = {
            "name": "g-push-rev",
            "email": "g-push-rev@git-ci-hub-lab",
        }

    if args.safe_path:
        required_config["global"]["safe"]["directory"] = os.path.abspath(
            args.local_path
        )

    repo = Repo.init(args.local_path, mkdir=False)

    with git_config(repo, required_config):
        commit = repo.commit(args.rev_id)
        ref_name = args.ref_name
        if not ref_name:
            ref_name = "gchl-{0}-{1}".format(args.ref_type, commit.hexsha[:8])

        # TODO: make it more generic
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                print("ref-name={0}".format(ref_name), file=f)

        ref_message = args.ref_message
        if not ref_message and args.ref_signing_format != SIGNING_FORMAT_NONE:
            ref_message = "signed"

        ref_signing_key = args.ref_signing_key or os.environ.get(
            "GCHL_REF_SIGNING_KEY", None
        )
        if ref_signing_key:
            ref_signing_key = base64.b64decode(ref_signing_key)
        with git_ref_exists_and_unique(
            repo,
            args.ref_type,
            ref_name,
            commit,
            ref_message=ref_message,
            ref_signing_format=args.ref_signing_format,
            ref_signing_key=ref_signing_key,
        ):
            with tmp_git_remote(repo, args.remote_url) as remote:
                if args.password is not None:
                    os.environ[password_variable] = args.password
                try:
                    remote.push(
                        ref_name, force=args.force_push
                    ).raise_if_error()
                except Exception:
                    raise
                finally:
                    if args.password is not None:
                        os.environ.pop(password_variable, None)
