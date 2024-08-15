import base64
import os
import random
import string
import uuid

from common import (
    BRANCH,
    SIGNING_FORMAT_NONE,
    SIGNING_FORMAT_SSH,
    TAG,
    git_config,
    git_keep_head,
    git_ref_exists_and_unique,
    git_remote,
    git_signing,
    info,
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
        metavar="REV_ID",
        default="HEAD",
        help="ID of the revision to push as understood by git-rev-parse "
        "(default: '%(default)s')",
    )
    signing_formats = [SIGNING_FORMAT_NONE, SIGNING_FORMAT_SSH]
    parser.add_argument(
        "--rev-signing-format",
        metavar="REV_SIGNING_FORMAT {{{0}}}".format(",".join(signing_formats)),
        choices=signing_formats,
        default=SIGNING_FORMAT_NONE,
        help="format to be used to sign REV_ID before pushing it to the remote "
        "repository (default '%(default)s')",
    )
    parser.add_argument(
        "--rev-signing-key",
        help="base64-encoded key to be used to sign REV_ID before pushing it "
        "to the remote repository (ignored if REV_SIGNING_FORMAT is '{0}', "
        "default: $GCHL_REV_SIGNING_KEY)".format(SIGNING_FORMAT_NONE),
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
    from git import RemoteProgress, Repo

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
    name_needed = args.ref_type == TAG and (
        args.ref_message or args.ref_signing_format != SIGNING_FORMAT_NONE
    )
    # Signed commits require the committer information:
    name_needed = name_needed or args.rev_signing_format != SIGNING_FORMAT_NONE

    if name_needed:
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

        with git_keep_head(repo):
            ref_name = args.ref_name
            if not ref_name:
                ref_name = "gchl-{0}-{1}".format(
                    args.ref_type, commit.hexsha[:8]
                )

            rev_signing_format = args.rev_signing_format
            if rev_signing_format != SIGNING_FORMAT_NONE:
                rev_signing_key = args.rev_signing_key or os.environ.get(
                    "GCHL_REV_SIGNING_KEY", None
                )
                if rev_signing_key:
                    rev_signing_key = base64.b64decode(rev_signing_key)
                with git_signing(repo, rev_signing_format, rev_signing_key):
                    repo.head.reference = commit
                    # TODO: handle erroneous zero exit code from git, which
                    #  happens when ssh-keygen is unable to find the key
                    repo.git.commit(amend=True, no_edit=True, gpg_sign=True)
                    commit = repo.head.commit

            ref_message = args.ref_message
            if (
                not ref_message
                and args.ref_signing_format != SIGNING_FORMAT_NONE
            ):
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
                with git_remote(repo, args.remote_url) as remote:
                    if args.password is not None:
                        os.environ[password_variable] = args.password
                    try:

                        class Progress(RemoteProgress):
                            def update(
                                self,
                                op_code,
                                cur_count,
                                max_count=None,
                                message="",
                            ):
                                info(self._cur_line)

                        remote.push(
                            ref_name, force=args.force_push, progress=Progress()
                        ).raise_if_error()

                        # TODO: make it more generic
                        if "GITHUB_OUTPUT" in os.environ:
                            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                                f.writelines(
                                    [
                                        "ref-name={0}\n".format(ref_name),
                                        "ref-commit={0}\n".format(commit),
                                    ]
                                )
                    finally:
                        if args.password is not None:
                            os.environ.pop(password_variable, None)
