import uuid
from contextlib import contextmanager

BRANCH = "branch"
TAG = "tag"


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
