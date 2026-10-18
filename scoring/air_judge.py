"""Public AIR entry point, preserving the tc3_judge implementation."""

if __package__:
    from .tc3_judge import *  # noqa: F401,F403
else:
    from tc3_judge import *  # noqa: F401,F403

if __name__ == "__main__":
    raise SystemExit(main())
