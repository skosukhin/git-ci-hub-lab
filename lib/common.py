import tempfile
import uuid
from contextlib import contextmanager

BRANCH = "branch"
TAG = "tag"

SIGNING_FORMAT_NONE = "none"
SIGNING_FORMAT_SSH = "ssh"


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
def git_signing(repo, signing_format=SIGNING_FORMAT_NONE, signing_key=None):
    if signing_format == SIGNING_FORMAT_NONE:
        yield
        return

    signing_config = {"repository": {"gpg": {"format": signing_format}}}

    if signing_format == SIGNING_FORMAT_SSH:
        with tempfile.NamedTemporaryFile(
            prefix="ghcl-", suffix=uuid.uuid4().hex
        ) as key_file:
            signing_config["repository"].update(
                {"user": {"signingkey": key_file.name}}
            )
            with git_config(repo, signing_config):
                try:
                    key_file.write(signing_key)
                    key_file.flush()
                    yield
                finally:
                    key_file.close()
    else:
        raise AssertionError(
            "unexpected signing format {0}".format(signing_format)
        )


@contextmanager
def git_keep_head(repo):
    do_stash = repo.is_dirty() or bool(repo.untracked_files)
    if do_stash:
        repo.git.stash("push", "--all")
    if repo.head.is_detached:
        head_backup = repo.head.commit
    else:
        head_backup = repo.head.reference
    try:
        yield
    finally:
        repo.head.reference = head_backup
        if do_stash:
            repo.git.stash("pop", "--index")


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

    def cleanup_and_restore():
        if tag_backup:
            repo.create_tag(ref_name, tag_backup, force=True)
            repo.delete_tag(tag_backup)
        if branch_backup:
            repo.create_head(ref_name, branch_backup, force=True)
            repo.delete_tag(branch_backup)

    try:
        # Delete references with conflicting names:
        if tag_backup:
            repo.delete_tag(ref_name)
        if branch_backup:
            if (
                not repo.head.is_detached
                and repo.head.reference.name == ref_name
            ):
                repo.head.reference = repo.head.commit
            repo.delete_head(ref_name, force=True)
    except Exception:
        cleanup_and_restore()
        raise

    try:
        # Create the requested reference:
        if ref_type == TAG:
            ref_signing_format = kwargs.get(
                "ref_signing_format", SIGNING_FORMAT_NONE
            )
            with git_signing(
                repo, ref_signing_format, kwargs.get("ref_signing_key", None)
            ):
                # TODO: handle erroneous zero exit code from git, which happens
                #  when ssh-keygen is unable to find the key
                repo.create_tag(
                    ref_name,
                    commit,
                    kwargs.get("ref_message", None),
                    sign=(ref_signing_format != SIGNING_FORMAT_NONE),
                )
        elif ref_type == BRANCH:
            repo.create_head(ref_name, commit)
        else:
            raise AssertionError(
                "unexpected reference type {0}".format(ref_type)
            )

        yield
    finally:
        # Delete the requested reference:
        if ref_type == TAG:
            repo.delete_tag(ref_name)
        elif ref_type == BRANCH:
            repo.delete_head(ref_name, force=True)
        cleanup_and_restore()


@contextmanager
def git_remote(repo, remote_url):
    remote_name = uuid.uuid4().hex
    remote = repo.create_remote(remote_name, remote_url)
    yield remote
    if remote_name in repo.remotes:
        repo.delete_remote(repo.remote(remote_name))
