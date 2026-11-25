"""Configure Hypothesis profiles for local runs and CI."""

import os

from hypothesis import settings

settings.register_profile("dev", parent=settings.get_profile("default"))
settings.register_profile(
    "ci", parent=settings.get_profile("dev"), derandomize=True, deadline=None, print_blob=True
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
