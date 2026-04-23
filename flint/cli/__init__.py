import click


@click.group()
def main() -> None:
    """Deploy LLMs to Kubernetes."""
