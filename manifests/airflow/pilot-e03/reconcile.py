from contextlib import closing
from datetime import UTC, datetime
from os import environ

from airflow.sdk import LoopDecision, dag, task, task_group


@dag(
    dag_id="pilot_reconcile",
    schedule=None,
    start_date=datetime(2025, 1, 1, tzinfo=UTC),
    catchup=False,
    is_paused_upon_creation=False,
    render_template_as_native_obj=True,
    tags=["pilot", "loop"],
)
def reconcile():
    image = environ.get("PILOT_DOCKER_TASK_IMAGE")

    def workload(function):
        if not image:
            return task(function)
        return task.docker(
            function,
            image=image,
            docker_url="unix:///var/run/docker.sock",
            mount_tmp_dir=False,
            expect_airflow=False,
            auto_remove="force",
            labels={"org.jyje.airflow.loop-task": function.__name__},
        )

    def load_backlog() -> int:
        return 23

    @task_group
    def reconcile_batch(initial_backlog: int):
        def reserve_batch(remaining: int) -> dict[str, int]:
            return {"pending": remaining, "reserved": min(8, remaining)}

        def apply_batch(batch: dict[str, int]) -> int:
            return batch["reserved"]

        def measure(batch: dict[str, int], applied: int) -> dict[str, int]:
            return {"remaining": batch["pending"] - applied, "applied": applied}

        batch = workload(reserve_batch)(
            "{{ ti.xcom_pull(task_ids='load_backlog', map_indexes=none) "
            "if loop.index == 1 else loop.previous['remaining'] }}"
        )
        initial_backlog >> batch
        workload(measure)(batch, workload(apply_batch)(batch))

    def backlog_empty(*, loop):
        remaining = loop.result["remaining"]
        stop = remaining == 0
        if image:
            import docker

            with closing(docker.from_env()) as client:
                result = client.containers.run(
                    image,
                    ["python", "-c", "import sys; print(int(sys.argv[1]) == 0)", str(remaining)],
                    labels={"org.jyje.airflow.loop-task": "backlog_empty"},
                    remove=True,
                )
            stop = result.strip() == b"True"
        return LoopDecision(stop=stop, reason=f"{remaining} records pending")

    def summarize(results: list[dict[str, int]]) -> dict[str, int | list[int]]:
        return {
            "remaining_history": [item["remaining"] for item in results],
            "processed": sum(item["applied"] for item in results),
        }

    loop = reconcile_batch.partial(initial_backlog=workload(load_backlog)()).loop(
        max_iterations=4, until=backlog_empty
    )
    result = workload(summarize)("{{ ti.xcom_pull(task_ids='reconcile_batch.measure') | list }}")
    loop["measure"].output >> result


reconcile()
