import os
import random
import string
import uuid
from contextlib import contextmanager

description = (
    "pushes a git revision from the local repository to the remote one"
)

BRANCH = "branch"
TAG = "tag"


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
        help="annotation message of the reference "
        "(ignored if REF_TYPE is not '{0}')".format(TAG),
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


@contextmanager
def git_config(repo, config):
    # Backup git configuration sections that we need to modify:
    config_backup = {}
    for scope, sections in config.items():
        with repo.config_reader(config_level=scope) as reader:
            scope_backup = {}
            config_backup[scope] = scope_backup
            for section, options in sections.items():
                section_backup = None
                if reader.has_section(section):
                    if section_backup is None:
                        section_backup = {}
                        scope_backup[section] = section_backup
                    for option in options.keys():
                        if reader.has_option(section, option):
                            section_backup[option] = reader.get_values(
                                section, option
                            )

    try:
        # Apply the required modifications of the git configuration:
        for scope, sections in config.items():
            with repo.config_writer(config_level=scope) as writer:
                for section, options in sections.items():
                    for option, value in options.items():
                        writer.set_value(section, option, value)
        yield
    except Exception:
        raise
    finally:
        # Restore git configuration from the backup:
        for scope, sections in config.items():
            with repo.config_writer(config_level=scope) as writer:
                scope_backup = config_backup[scope]
                for section, options in sections.items():
                    if section in scope_backup:
                        section_backup = scope_backup[section]
                        for option in options.keys():
                            writer.remove_option(section, option)
                            if option in section_backup:
                                for value in section_backup[option]:
                                    writer.add_value(section, option, value)
                    else:
                        writer.remove_section(section)


@contextmanager
def git_ref_exists_and_unique(repo, ref_type, ref_name, commit, **kwargs):
    def backup_ref(name, refs):
        # Finds a reference with the specified name in the provided collection
        # and returns a newly created lightweight tag with a random name that
        # points to the reference. If the reference is not found in the
        # collection, return None.
        for r in refs:
            if r.name == name:
                return repo.create_tag(uuid.uuid4(), r.path, None)
        return None

    # Back up references with conflicting names:
    tag_backup = backup_ref(ref_name, repo.tags)
    branch_backup = backup_ref(ref_name, repo.branches)

    # Back up the current head:
    head_backup = None
    if not repo.head.is_detached:
        head_backup = repo.head.reference

    try:
        # Detach the head:
        if head_backup:
            repo.head.reference = repo.commit(head_backup.commit)

        # Delete references with conflicting names:
        if tag_backup:
            repo.delete_tag(ref_name)
        if branch_backup:
            repo.delete_head(ref_name, force=True)

        # Create the requested reference:
        if ref_type == TAG:
            repo.create_tag(ref_name, commit, kwargs.get("message", None))
        elif ref_type == BRANCH:
            repo.create_head(ref_name, commit)
        else:
            raise AssertionError(
                "unexpected reference type {0}".format(ref_type)
            )

        yield
    except Exception:
        raise
    finally:
        # Delete the requested reference:
        if ref_type == TAG:
            repo.delete_tag(ref_name)
        elif ref_type == BRANCH:
            repo.delete_head(ref_name, force=True)

        # Restore the conflicting references:
        if tag_backup:
            repo.create_tag(ref_name, tag_backup, force=True)
            repo.delete_tag(tag_backup)
        if branch_backup:
            repo.create_head(ref_name, branch_backup, force=True)
            repo.delete_tag(branch_backup)

        # Re-attach the head:
        if head_backup is not None:
            repo.head.reference = head_backup


@contextmanager
def tmp_git_remote(repo, remote_url):
    remote_name = uuid.uuid4().hex
    remote = repo.create_remote(remote_name, remote_url)
    yield remote
    if remote_name in repo.remotes:
        repo.delete_remote(repo.remote(remote_name))


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

    # Annotated tags require the committer information:
    if args.ref_type == TAG and args.ref_message:
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

        with git_ref_exists_and_unique(
            repo, args.ref_type, ref_name, commit, message=args.ref_message
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
