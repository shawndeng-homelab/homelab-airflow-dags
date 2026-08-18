"""Minimal manual DAG for validating the local Airflow installation."""

import pendulum
from airflow.decorators import dag
from airflow.decorators import task


@dag(
    dag_id="example_hello_world",
    schedule=None,
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["example", "smoke-test"],
    description="A dependency-free DAG for validating Airflow deployment.",
)
def example_hello_world():
    """Run a small two-step smoke test without external services."""

    @task
    def say_hello() -> str:
        """Return a message and make it available through XCom."""
        message = "Hello from homelab Airflow"
        print(message)
        return message

    @task
    def confirm_message(message: str) -> None:
        """Confirm that the upstream task produced the expected message."""
        if message != "Hello from homelab Airflow":
            raise ValueError(f"Unexpected message: {message!r}")
        print("Example DAG smoke test passed")

    confirm_message(say_hello())


example_hello_world()
