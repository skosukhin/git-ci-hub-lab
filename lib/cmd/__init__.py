import importlib

commands = [
    "g-push-rev",
    "g-delete-ref",
    "gl-create-pipeline",
    "gl-trigger-pipeline",
    "gl-cancel-pipeline",
    "gl-attach-job",
    "gl-delete-ref",
]


def get_module(name):
    return importlib.import_module("%s.%s" % (__name__, name))
