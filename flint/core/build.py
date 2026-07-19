"""Image registry pull and push operations.

Flint v0.1 does NOT build container images. This module handles only
pull and push of pre-built runtime images. The default image for each
runtime is owned by that runtime's adapter (see ``flint/runtimes/``).

Architecture note (from FLINT_ARCHITECTURE.md):
    "Flint does not build container images in v0.1. Custom model-baked
    images are a v0.2+ feature."

Ported from monolith: modelpush (1214), modelpull (1255),
trainer_serverpush (3669), trainer_serverpull (3646).
"""

from __future__ import annotations

import logging
import subprocess

from flint.core.errors import BuildError

logger = logging.getLogger(__name__)


def push_image(image_ref: str) -> None:
    """Push a container image to its registry.

    Ported from monolith `modelpush` (lines 1214-1252) and
    `trainer_serverpush` (lines 3669-3689).

    Args:
        image_ref: Full image reference, e.g. ``"docker.io/org/model:v1"``.

    Raises:
        BuildError: If the push fails.
    """
    logger.debug("Pushing image: %s", image_ref)
    result = subprocess.run(
        f"docker push {image_ref}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(
            f"docker push failed for {image_ref!r}:\n{result.stderr.strip()}"
        )


def pull_image(image_ref: str) -> None:
    """Pull a container image from its registry.

    Ported from monolith `modelpull` (lines 1255-1275) and
    `trainer_serverpull` (lines 3646-3666).

    Args:
        image_ref: Full image reference, e.g. ``"docker.io/org/model:v1"``.

    Raises:
        BuildError: If the pull fails.
    """
    logger.debug("Pulling image: %s", image_ref)
    result = subprocess.run(
        f"docker pull {image_ref}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(
            f"docker pull failed for {image_ref!r}:\n{result.stderr.strip()}"
        )
