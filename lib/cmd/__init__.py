import importlib

commands = [
    "g-push-rev",
    "gl-create-pipeline",
    "gl-trigger-pipeline",
    "gl-attach-job",
    "gl-delete-ref",
]


def get_module(name):
    return importlib.import_module("%s.%s" % (__name__, name))
