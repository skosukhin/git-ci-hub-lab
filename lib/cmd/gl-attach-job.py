import sys
import time

from common import (
    JOB_FINAL_STATUSES,
    JOB_SUCCESS,
    PIPELINE_FINAL_STATUSES,
    GHCLAssertionError,
    info,
)

description = (
    "attaches to a GitLab job in the CI pipeline and redirects its trace"
)


def setup_parser(parser):
    parser.add_argument("--server-url", required=True, help="GitLab server URL")
    parser.add_argument(
        "--project-name", required=True, help="GitLab project name"
    )
    parser.add_argument("--token", required=True, help="GitLab access token")
    parser.add_argument(
        "--pipeline-id", required=True, help="ID of the pipeline"
    )
    parser.add_argument(
        "--job-name", required=True, help="name of the job to attach to"
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=10,
        help="job status poll timeout in seconds (default: `%(default)s`)",
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
    pipeline = project.pipelines.get(args.pipeline_id, lazy=True)

    requested_job = None
    reported_trace_len = 0

    poll_timeout = 0 if args.poll_timeout < 0 else args.poll_timeout

    while True:
        if requested_job is None:
            pipeline.refresh()
            for job in pipeline.jobs.list():
                if job.name == args.job_name:
                    if requested_job is None:
                        requested_job = project.jobs.get(job.id)
                        info(
                            "Attaching to job `{0}` ({1})".format(
                                requested_job.name, requested_job.web_url
                            )
                        )
                    else:
                        raise GHCLAssertionError(
                            "ambiguous job name: more than one job in the "
                            "pipeline has name `{0}`".format(args.job_name)
                        )
        else:
            requested_job.refresh()
        if requested_job is None:
            if pipeline.status in PIPELINE_FINAL_STATUSES:
                break
        else:
            poll_trace_len = 0
            for chunk in requested_job.trace(streamed=True, iterator=True):
                chunk = chunk.decode()
                chunk_len = len(chunk)
                unreported_subchunk_start = reported_trace_len - poll_trace_len
                poll_trace_len += chunk_len
                if chunk_len > unreported_subchunk_start:
                    print(
                        chunk[unreported_subchunk_start:],
                        end="",
                        file=sys.stdout,
                    )
                    reported_trace_len = poll_trace_len
            sys.stdout.flush()
            if requested_job.status in JOB_FINAL_STATUSES:
                break

        time.sleep(poll_timeout)

    if requested_job is None:
        raise GHCLAssertionError(
            "job `{0}` is not found in pipeline for SHA `{1}` ({2})".format(
                args.job_name, pipeline.sha[:8], pipeline.web_url
            )
        )

    exit(requested_job.status != JOB_SUCCESS)
